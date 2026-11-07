"""Adaptive alliance scenarios: communities that learn, ask neighbours for help, build trust and share
quarries and trackways along the whole supply chain (config.yaml -> alliance).

  mpirun -n 8 python model.py config.yaml --alliance NAME|all [--seeds 1-100] [--sites ...]

Agent = a community (one per site), a repast4py core.Agent in a SharedContext. One schedule tick = one building
season of season_days working days. The island is coupled (help, trust, tracks, imitation), so each MPI rank
simulates the WHOLE island for its own seeds (MPI.COMM_SELF), as in the `high` scenario: results do not depend
on the rank count.

Labour model. Inside a community everyone cooperates exactly as in `webster`/`full`. In every one of the
716,700 webster site-runs the builders were never idle, so a tower's labour is exactly
    transport (sum over blocks of crew x trip time)  +  quarry + dressing + walling + lifting (Webster stages)
and its duration is that labour divided by the workforce. This module therefore represents each tower as a
chain of stage TASKS (quarry -> dress -> [track] -> transport (relay leg 1 -> leg 2) -> build/lift), each with
a performer and a labour total. Each day every community spends B x hours_per_day on its tasks; a task may not
run ahead of the task upstream of it (the delivered-stone cap of the ABM, generalised to the chain).
See METHODS.md section 9 for the equations, sources and FREE parameters.
"""
import hashlib
import json
import math
import os
import time

import numpy as np
import pandas as pd
from mpi4py import MPI
from numba import njit
from repast4py import context as ctx
from repast4py import core, schedule

import lit
import phasing

CODE_VERSION = lit.CODE_VERSION     # bump whenever a code change alters results: part of every run signature
#   (code_v16_final: "2026-11-05-v16_final", set in lit.py so model.run_signature hashes the same string; was
#   "2026-10-29-bugfix" in every code from 29 Oct to code_v16_flags, so those signatures never covered code changes)
TECH_VERSION = "2026-10-30-fix1030"   # tech_rules code path only (MOST_REALISTIC); hashed only when tech_rules is set
#   (was "2026-10-29-merged-1"; bumped 30 Oct for NEW-1 lift/hoist per piece + the sea payload split)
SEA_VERSION = "2026-10-30-payload"    # S9 sea faces: 2,000 kg craft payload split (30 Oct); hashed only when sea_kn is set
# 1 Nov 2026 scenario gaps (S10-S14, NEW_SCENARIOS_1101.md): hashed only when one of these keys is set, so every
# earlier scenario keeps its signature and its code path (identity test: outputs/identity/)
GAPS_VERSION = "2026-11-01-gaps-1"
GAPS_KEYS = ("phase_order", "type_cost", "food_cap", "extra_units", "maintenance")
# 1 Nov 2026 (b) wider-literature scenarios (C1-C3, M1-M4; WIDER_LIT_1101.md): hashed only when one of these keys is
# set (or phase_order.rule == emulation), so every earlier scenario keeps its signature and code path
WL_VERSION = "2026-11-01-widerlit-2"
V11_VERSION = "2026-11-02-v11"         # Webster man-day hours by source (lit.md_hours); hashed only when the fix is on   # -2: M4 walk choice per hauled leg
WL_KEYS = ("haul_profile", "stage_rates", "carry", "masons")
# 2 Nov 2026 (v12) census scenarios (census/TESTABLE_PLAN.md; code/CENSUS_V12.md): each is OFF unless its key is set in
# the scenario; hashed only when one of these keys is set, so every earlier scenario keeps its signature and its code
# path (identity test: outputs/identity/IDENTITY.txt)
CENSUS_VERSION = "2026-11-02-census-1"
CENSUS_KEYS = ("lift_graded", "lintel", "found", "fill", "vault_dress", "demog", "lift_ramp", "mortar", "rifascio",
               "bichrome", "levy", "mason_regions", "feast_attract", "mudbrick", "clearance", "carts", "size_draw",
               "lift_override")
# 2 Nov 2026 (v13) social mechanisms (ODD 7.15, CODE_PROVENANCE.md): reputation (indirect reciprocity with
# standing, third-party shunning), partner choice (assortment), imitation along help ties; social_log = bookkeeping only.
# Each is OFF unless its key is set in the scenario. They make no random draws of their own. Hashed (with
# cfg['scenarios'] minus its list, whose split_cost_mh acts on every alliance run) only when one of these keys is set, so
# every earlier scenario keeps its signature and its code path (identity test: ODD 7.15, CODE_PROVENANCE.md). CODE_VERSION is
# deliberately NOT bumped: with the keys off the outputs are identical to the frozen v12 code (tested), and a bump would move every
# existing scenario's cache folder.
SOCIAL_VERSION = "2026-11-02-v13-social-2"   # -2: partner order = exchange partners first (both directions)
SOCIAL_KEYS = ("reputation", "partner_choice", "tie_imitation", "social_log", "trusted_nodist")   # v13kd: end of file
# v14 (5 Nov 2026, specified by the authors; CHANGES_V14_NEARFACE.md): config
# key quarry.near_site_fixed_face_m. A site whose dry-ground (mu 0.38) route (haul table mu0.38, haul_m) is <= this
# many metres always quarries from face 0: no epsilon draw, no Q choice, no imitation of the face (the draws are
# skipped, not drawn and discarded). Off (absent / none / 0) = the v12 code path; hashed only when on, so every run
# with the key off keeps its signature (identity test: v14_nearface/identity/).
NEARFACE_VERSION = "2026-11-05-nearface-1"
# v16 (5 Nov 2026; addendum 4 of the specification; CHANGES_V16.md). Always hashed: v16 also
# changes reporting (S1 relay_made in the strategy parts) and the S3 ceiling basis, so no v16 run reuses v15b parts.
# The addendum-4 rules L1-L4 sit behind config flags add4.* (code_v16_final defaults: L2, L3 ON; L1, L4 OFF; lit.py).
# code_v16_final: their effective settings are ALWAYS hashed (code_v16_flags hashed them only when one was on).
V16_VERSION = "2026-11-05-v16-flags-2"   # -2: relay leg-1 nearer-than-owner filter removed (-1 = the test runs)
# code_v16_final (CHANGES_V16_FINAL.md): D3 no dress work = no dress task traffic, D6 join parties at their own skill,
# D11 the site's stone = the class of its gated face 0. Always on (no flag); covered by CODE_VERSION.
ADD4_VERSION = "2026-11-05-add4-1"


def near_face_m(cfg):
    """quarry.near_site_fixed_face_m as a float, or None when the rule is off (absent, none/null, 0)."""
    v = (cfg.get("quarry") or {}).get("near_site_fixed_face_m")
    if v is None or (isinstance(v, str) and v.strip().lower() in ("none", "null", "off", "")):
        return None
    v = float(v)
    return v if v > 0 else None

STAGES = ["quarry", "dress", "track", "leg1", "transport", "build"]   # chain order (task rank)
PAIR_STAGE = {"quarry": "quarry", "dress": "dress", "track": "track", "leg1": "transport", "transport": "transport",
              "build": "build"}                                      # stage columns of the pair files
PAIR_STAGES = ["quarry", "dress", "transport", "build", "track"]
SKILL_STAGES = ["quarry", "dress", "build"]                          # stages with a learning curve
DIMS = ["quarry_face", "req_quarry", "req_dress", "req_build", "relay", "track"]


# ----------------------------------------------------------------------------------- numba day loop
@njit(cache=True)
def run_days(ndays, order, perf, total, done, up, final, cap, capleft, finish_day, day0, up2):
    """Advance up to ndays working days. Stops at the end of a day in which a tower's final task completed.
    Returns the number of days consumed."""
    for d in range(ndays):
        for i in range(order.size):
            capleft[perf[order[i]]] = cap[perf[order[i]]]
        event = False
        for i in range(order.size):
            t = order[i]
            if done[t] >= total[t]:
                continue
            p = perf[t]
            if capleft[p] <= 0.0:
                continue
            u = up[t]
            if u >= 0:
                frac = 1.0 if total[u] <= 0.0 else done[u] / total[u]
                u2 = up2[t]                      # join mode: a stage split between owner and helper has 2 parts
                if u2 >= 0:
                    frac2 = 1.0 if total[u2] <= 0.0 else done[u2] / total[u2]
                    if frac2 < frac:
                        frac = frac2
                allowed = frac * total[t] - done[t]
            else:
                allowed = total[t] - done[t]
            if allowed <= 0.0:
                continue
            take = allowed if allowed < capleft[p] else capleft[p]
            done[t] += take
            capleft[p] -= take
            if total[t] - done[t] <= 1e-9 * total[t] + 1e-12:
                done[t] = total[t]
                finish_day[t] = day0 + d
                if final[t]:
                    event = True
        if event:
            return d + 1
    return ndays


def sigmoid(x):
    if x < -700.0:   # exp(-x) would overflow (a Nurnet collaborator's fix); the true value is < 1e-304
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


# ----------------------------------------------------------------------------------- static data
class Static:
    """Everything that does not depend on the seed: sites, neighbours, k-best quarry routes."""

    def __init__(self, cfg, haul, R_m=None, sea_kn=None, tech=None):
        A = cfg["alliance"]
        self.cfg = cfg
        self.sea_kn = sea_kn
        self.travel = None
        self.tech = None
        self.A = A
        self.haul = haul.reset_index(drop=True)
        self.N = len(haul)
        kb = np.load(os.path.join(cfg["paths"]["cache_dir"], "alliance", "kbest.npz"))
        meta = pd.DataFrame(kb["meta"])
        self.W = int(kb["W"]); self.H = int(kb["H"])
        self.T = kb["transform"]
        self.ptr, self.mv_cell = kb["ptr"], kb["mv_cell"]
        self.mv_c03 = kb["mv_c03"].astype(np.float64); self.mv_c01 = kb["mv_c01"].astype(np.float64)
        self.mv_len = kb["mv_len"].astype(np.float64)
        # map haul rows (possibly a subset) to kbest gids via UID order of sites_haul.csv
        full = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
        gid_of_uid = {u: i for i, u in enumerate(full.UID)}
        self.faces = []                                   # per site: list of dicts
        fr = list(A["relay_fractions"])
        meta["route"] = np.arange(len(meta))              # row order == path order in kbest.npz
        by_gid = {g: d.sort_values("q") for g, d in meta.groupby("gid")}
        for i, row in self.haul.iterrows():
            g = gid_of_uid[row.UID]
            fl = []
            for m in (by_gid[g].itertuples() if g in by_gid else []):
                j = int(m.route)
                a, b = int(self.ptr[j]), int(self.ptr[j + 1])
                C, L = float(m.cost03), float(m.len_m)
                if m.q == 0:                              # face 0 == baseline (equal-cost ties: keep baseline length)
                    L = float(row.haul_m)
                cum = np.cumsum(self.mv_c03[a:b])
                ho = {}
                for f in fr:
                    if C > 0:
                        h = int(np.searchsorted(cum, f * C))          # first move whose cum cost reaches f*C
                        ho[f] = min(h + 1, b - a)                      # number of moves in leg 1
                fl.append({"route": j, "a": a, "b": b, "region": int(m.region), "C": C, "L": L,
                           "qx": self.T[2] + (m.qcol + 0.5) * self.T[0], "qy": self.T[5] + (m.qrow + 0.5) * self.T[4],
                           "handoff": ho})
            if not fl:                                    # no allowed outcrop reachable: local stone (baseline rule)
                fl.append({"route": -1, "a": 0, "b": 0, "region": -1 - i, "C": float(row.haul_flatm),
                           "L": float(row.haul_m), "qx": row.x, "qy": row.y, "handoff": {}})
            self.faces.append(fl)
        if sea_kn:                                        # S9: one extra face per site whose sea route beats the land route
            import sea as seamod
            sh = seamod.load_haul(self.haul, cfg, sea_kn)
            self.uid = self.haul.UID.to_numpy()
            self.travel = seamod.Travel(cfg, sea_kn, self.haul.UID)
            for i, row in enumerate(sh.to_dict("records")):
                if row["mode"] == "sea":
                    self.faces[i].append({"route": -2, "a": 0, "b": 0, "region": int(row["quarry_region"]),
                                          "C": float(row["haul_flatm"]), "L": float(row["haul_m"]),
                                          "qx": float(row["quarry_x"]), "qy": float(row["quarry_y"]), "handoff": {},
                                          "sea": True, "trip_h": seamod.trip_h(row, cfg, sea_kn),
                                          "land_h": seamod.trip_h(row, cfg, 1e300),   # trip without the boat leg
                                          "hoist_ph": seamod.hoist_ph_per_block(row, cfg)})
        self.near = None                                  # v14: per site, True = always face 0 (rule off: None)
        nf = near_face_m(cfg)
        if nf is not None:
            t38 = pd.read_csv(lit.haul_csv(cfg, {"haul": "mu0.38"}), usecols=["UID", "haul_m"]).set_index("UID")
            h38 = t38.haul_m.reindex(self.haul.UID.to_numpy()).to_numpy(np.float64)
            self.near = np.isfinite(h38) & (h38 <= nf)   # no dry-ground row: not near (keeps the face choice)
            self.near_haul_m = h38
        if tech:                                          # MOST_REALISTIC: per-site literature rules (tech_rules)
            self._init_tech(cfg, tech)
        from scipy.spatial import cKDTree
        xy = self.haul[["x", "y"]].to_numpy()
        self.xy = xy
        tree = cKDTree(xy)
        self.R = float(A["R_m"] if R_m is None else R_m)
        self.nb = []
        for i, nb in enumerate(tree.query_ball_point(xy, r=self.R)):
            nb = np.array(sorted(j for j in nb if j != i), np.int64)
            d = np.hypot(*(xy[nb] - xy[i]).T) if nb.size else np.zeros(0)
            o = np.lexsort((nb, d))
            self.nb.append((nb[o], d[o]))


    def _init_tech(self, cfg, tech):
        """Per-site technical rules of a mixed literature scenario (lit_scenarios.list[tech], e.g. REALISTIC):
        stage hours (S1, S2, S4, S6 hardness), S6 density, per-site friction (sledge on dry ground mu 0.38, or
        tallowed rails mu 0.1 where the sledge route > long_min_haul_m) and S8. MOST_REALISTIC_NOTES.md."""
        L = lit.scenario(cfg, tech)
        assert L.get("mixed"), f"tech_rules needs a mixed literature scenario, got {tech}"

        def load(path):                                   # that table's rows of this run's sites, in this order
            t = pd.read_csv(path).set_index("UID")
            h = t.reindex(self.haul.UID.to_numpy()).reset_index()
            h["uid_int"] = self.haul.uid_int.to_numpy()
            return h
        F = lit.add4(cfg)
        self.add4 = F
        k38 = np.load(os.path.join(cfg["paths"]["cache_dir"], "alliance", "kbest_mu038.npz"))
        self.mv_c038 = k38["mv_c038"].astype(np.float64)
        use_long = None
        if F["rails_cost_choice"]:                        # v16 L1: rails vs dry ground by total cost, per site
            use_long = self._l1_choice(cfg, L, load, F)
        mh = lit.mixed_haul(cfg, L, load, use_long=use_long)
        assert mh.on_outcrop.notna().all(), "tech_rules: a site is missing from the short-haul table"
        # code_v16_final D11: the site's stone (S6 density -> block mass, hardness -> quarry / dress) is the class of
        # the face it hauls from: face 0 of the gated mu 0.3 table (self.haul = cache sites_haul.csv, the table whose
        # rows are face 0 of kbest.npz; stone rule = the set actually quarried incl. fallback). The mixed table's own
        # quarry_stone came from separate least-cost searches on the mu 0.38 / mu 0.1 rasters and could name another
        # outcrop class (bug D11, CHANGES_V16_FINAL.md). The mixed table still decides friction (lit_haul_rule, PM:22).
        mh["quarry_stone_mixed"] = mh.quarry_stone.to_numpy()
        mh["quarry_stone"] = self._face0_stone(mh)
        self.tech = {"lit": L, "rule": mh.lit_haul_rule.to_numpy(), "stone": mh.quarry_stone.to_numpy(),
                     "site": [lit.resolve_site(cfg, L, r) for r in mh[["TWR_N", "on_outcrop", "lit_haul_rule",
                                                                       "lit_type"]].to_dict("records")],
                     "table": mh[["UID", "on_outcrop", "lit_haul_rule", "lit_type", "quarry_stone"]]}
        if self.sea_kn:                                   # sea faces: split the trip into land legs and boat
            for fl in self.faces:
                for fc in fl:
                    if fc.get("sea"):
                        boat = fc["trip_h"] - fc["land_h"]
                        fc["boat_h"] = boat
        self.tech["n_long"] = int((self.tech["rule"] == "long").sum())
        self.lay_len = None                               # v16 L1: rail-laying length (m) of face 0, rails sites
        if F["rails_cost_choice"]:
            self.lay_len = np.where(self.tech["rule"] == "long", self.l1_len, 0.0)
        if self.sea_kn and F["sea_priced_as_charged"]:    # v16 L4: sea faces chosen on the charged cost
            self._l4_sea_faces(cfg, F)
        self.info = {"n_rails_sites": self.tech["n_long"], "n_sites": int(self.N),
                     "n_sea_faces": int(sum(any(fc.get("sea") for fc in fl) for fl in self.faces)),
                     "add4": {k: F[k] for k in lit.ADD4_FLAGS}, "rail_lay_mh_per_m": F["rail_lay_mh_per_m"],
                     "load_ph_per_t": F["load_ph_per_t"]}
        if getattr(self, "l4_info", None):
            self.info.update(self.l4_info)

    def _face0_stone(self, tab):
        """code_v16_final D11: per row of `tab` (UID column, this run's sites in order), the quarry_stone of the gated
        face-0 table self.haul (the class of the outcrop the site's face 0 starts at)."""
        st = self.haul.set_index("UID").quarry_stone.reindex(tab.UID.to_numpy())
        assert st.notna().all(), "D11: a site has no face-0 stone in sites_haul.csv"
        return st.to_numpy()

    # ------------------------------------------------------------------ v16 addendum-4 static choices (L1, L4)
    def _face0_costs(self, i):
        """Face-0 (cheapest land face) drag costs exactly as _leg_mh_tech0 charges a whole route: (C on dry ground
        mu 0.38 moves, C on rails mu 0.1 moves, L real length)."""
        f = self.faces[i][0]
        if f["route"] < 0 or f["a"] == f["b"]:
            return f["C"], f["C"], f["L"]
        return float(self.mv_c038[f["a"]:f["b"]].sum()), float(self.mv_c01[f["a"]:f["b"]].sum()), f["L"]

    def _l1_choice(self, cfg, L, load, F):
        """v16 L1 (addendum 4): every site takes the cheaper of dry ground (mu 0.38 crews and moves) and rails (mu 0.1
        crews and moves + rail_lay_mh_per_m x real route length, paid once per site) for ALL its towers on face 0,
        computed once before the run: crews = expected crews per tonne of the block draw (lit.crews_per_tonne, S6
        density of that rule's stone) x the site's tonnes; trip = the model's whole-route trip (min haul floor), with
        the per-crew loading (load_unload_h) or, under L3, load_ph_per_t x tonnes (equal in both, kept for clarity).
        Returns use_long per site (lit.mixed_haul); sets self.l1_len (laying length, m) and self.l1_cost."""
        m = L["mixed"]
        tp = cfg["transport"]
        short = load(lit.haul_csv(cfg, {"haul": m["short"]["haul"]}))
        lng = load(lit.haul_csv(cfg, {"haul": m["long"]["haul"]}))
        ok = lng.haul_flatm.notna().to_numpy()
        fl, v, vb = float(tp["min_haul_flatm"]), float(tp["drag_speed_ms"]), float(tp["return_walk_ms"])
        L3 = F["load_per_tonne"]
        p_s = lit.transport(cfg, dict(L, **m["short"]))[0]
        p_l = lit.transport(cfg, dict(L, **m["long"]))[0]
        tpt = float(cfg["stone"]["tonnes_per_tower"])
        tw = self.haul.TWR_N.to_numpy().astype(np.float64)
        st0 = self._face0_stone(short)                    # code_v16_final D11: one stone per site, face 0's class
        use = np.zeros(self.N, bool)
        self.l1_len = np.zeros(self.N)
        self.l1_cost = np.zeros((self.N, 2))
        for i in range(self.N):
            c38, c01, Lr = self._face0_costs(i)
            out = []
            for C, pull, st in ((c38, p_s, st0[i]), (c01, p_l, st0[i])):
                mf = lit.mass_factor(cfg, L, st if isinstance(st, str) else "")
                cpt = lit.crews_per_tonne(cfg, pull, mf)[0]
                tn = tpt * tw[i] * mf
                trip = max(C, fl) / v / 3600.0 + max(Lr, fl) / vb / 3600.0 + (0.0 if L3 else float(tp["load_unload_h"]))
                out.append(cpt * tn * trip + (F["load_ph_per_t"] * tn if L3 else 0.0))
            self.l1_len[i] = max(Lr, fl)
            out[1] += F["rail_lay_mh_per_m"] * self.l1_len[i]
            self.l1_cost[i] = out
            use[i] = bool(ok[i]) and out[1] < out[0]
        return use

    def _l4_sea_faces(self, cfg, F):
        """v16 L4 (addendum 4): the choice between land and sea is made on the cost the model charges. Every sea route
        the v16 table builder found (r_* columns) is a candidate; per site, before the run, with expected crews per
        tonne (lit.crews_per_tonne): land legs at the site's own rule (L1 on: each leg takes rails or dry ground by its
        own cost incl. laying x leg length; L1 off: the site's rule, rails if 'long'), loading per crew at each landing
        (sea.transfer_h) or, under L3, load_ph_per_t x tonnes per land leg; boat crews at 100 kg/person x boat time
        (as S9); hoist per block. The site gets the sea face iff that cost per tonne is below its charged face-0 land
        cost per tonne. Replaces the S9 sea faces of the table's 'mode' column."""
        import sea as seamod
        L = self.tech["lit"]
        tp = cfg["transport"]
        fl, v, vb = float(tp["min_haul_flatm"]), float(tp["drag_speed_ms"]), float(tp["return_walk_ms"])
        L1, L3 = F["rails_cost_choice"], F["load_per_tonne"]
        lay, lp = F["rail_lay_mh_per_m"], F["load_ph_per_t"]
        trf = seamod.params(cfg)["transfer_h"]
        hoist_m = seamod.params(cfg)["hoist_ph_per_block_m"]
        pS = lit.transport(cfg, dict(L, **L["mixed"]["short"]))[0]
        pL = lit.transport(cfg, dict(L, **L["mixed"]["long"]))[0]
        p03 = float(tp["pull_kg_per_person"])
        tpt = float(cfg["stone"]["tonnes_per_tower"])
        rt = seamod.load_routes(self.haul, cfg, self.sea_kn)
        n_old = sum(any(fc.get("sea") for fc in fl_) for fl_ in self.faces)
        for fl_ in self.faces:                            # drop the S9 (table 'mode') sea faces
            fl_[:] = [fc for fc in fl_ if not fc.get("sea")]
        n_cand = n_new = n_leg_rails = 0
        for i, r in enumerate(rt.to_dict("records")):
            if not r["r_found"]:
                continue
            n_cand += 1
            long_i = self.tech["rule"][i] == "long"
            mf = lit.mass_factor(cfg, L, self.tech["stone"][i] if isinstance(self.tech["stone"][i], str) else "")
            cS, mblk = lit.crews_per_tonne(cfg, pS, mf)
            cL = lit.crews_per_tonne(cfg, pL, mf)[0]
            c03 = lit.crews_per_tonne(cfg, p03, mf)[0]
            tn_site = tpt * float(self.haul.TWR_N.iat[i]) * mf
            c_site = cL if long_i else cS
            # land face 0 at the site's rule, per tonne
            c38, c01, Lr = self._face0_costs(i)
            land = c_site * (max(c01 if long_i else c38, fl) / v + max(Lr, fl) / vb) / 3600.0 + \
                (lp if L3 else c_site * float(tp["load_unload_h"]))
            if L1 and long_i:
                land += lay * max(Lr, fl) / tn_site
            # sea chain per tonne
            sea_ = 0.0
            legs, rails = [], []
            for hf, hm in ((r["r_hf1"], r["r_hm1"]), (r["r_hf2"], r["r_hm2"])):
                t_k = (max(hf, fl) / v + max(hm, fl) / vb) / 3600.0
                dry_k = cS * (t_k + (0.0 if L3 else trf))
                rl_k = cL * (t_k + (0.0 if L3 else trf)) + (lay * max(hm, fl) / tn_site if L1 else 0.0)
                rk = (rl_k < dry_k) if L1 else bool(long_i)
                sea_ += rl_k if rk else dry_k
                legs.append((float(hf), float(hm)))
                rails.append(bool(rk))
            bh = seamod.boat_h(r["r_sea_km"], cfg, self.sea_kn)
            sea_ += (2.0 * lp if L3 else 0.0) + c03 * bh + hoist_m * float(r["r_hoist_m"]) / mblk
            if not sea_ < land:
                continue
            n_new += 1
            n_leg_rails += sum(rails)
            self.faces[i].append({"route": -2, "a": 0, "b": 0, "region": int(r["r_quarry_region"]),
                                  "C": float(r["r_hf1"] + r["r_hf2"]), "L": float(r["r_hm1"] + r["r_hm2"]),
                                  "qx": float(r["r_quarry_x"]), "qy": float(r["r_quarry_y"]), "handoff": {},
                                  "sea": True, "boat_h": bh, "hoist_ph": hoist_m * float(r["r_hoist_m"]),
                                  "legs": legs, "leg_rails": rails, "l4_cost_pt": (land, sea_)})
        self.l4_info = {"l4_sea_candidates": n_cand, "l4_sea_faces_old": int(n_old), "l4_sea_faces_new": n_new,
                        "l4_sea_land_legs_rails": n_leg_rails}


# ----------------------------------------------------------------------------------- agents
class Community(core.Agent):
    TYPE = 0

    def __init__(self, gid, rank):
        super().__init__(id=gid, type=Community.TYPE, rank=rank)
        self.gid = gid


class AllianceModel:
    def __init__(self, S, sc, seed, comm=MPI.COMM_SELF):
        self.S, self.sc, self.seed = S, sc, seed
        cfg, A = S.cfg, S.A
        self.cfg, self.A = cfg, A
        H = float(cfg["hours_per_day"])
        self.Hh = H
        self.context = ctx.SharedContext(comm)
        self.runner = schedule.init_schedule_runner(comm)
        N = S.N
        self.N = N
        tp = cfg["transport"]
        self.tp = tp
        Ls = cfg["lit_scenarios"]
        self.pull03 = tp["pull_kg_per_person"]
        self.pull01 = Ls["f_person_kgf"] / float(A["track_mu"])
        # v16 addendum-4 flags (tech rules only; lit.add4): None / False = the v15b code paths
        self.F = getattr(S, "add4", None) if S.tech is not None else None
        self.L3 = bool(self.F and self.F["load_per_tonne"])
        self.L4 = bool(self.F and self.F["sea_priced_as_charged"] and S.sea_kn)
        self.lp = float(self.F["load_ph_per_t"]) if self.F else 0.0
        self.tw_n = S.haul.TWR_N.to_numpy().astype(np.float64)
        self.c01 = [None] * N if self.L4 else None       # v16 L4: rails crews per tower (land legs of sea faces)
        st = lit.stage_hours(cfg, lit.scenario(cfg, "webster"), 1, "", 0)      # Webster stages per tower
        self.base_stage = {"quarry": st["quarry"], "dress": st["dress"], "build": st["build"] + st["lift"]}
        self.lift_share = st["lift"] / (st["build"] + st["lift"])
        self.b = float(sc["b"])
        self.expo = math.log2(self.b)
        # ---- per-site seeded draws: builders + blocks exactly as model.Site (webster), then towers
        b, s = cfg["builders"], cfg["stone"]
        self.B = np.zeros(N, np.int64)
        # S10 / S11 (1 Nov): ordered build units instead of random site cohorts (phase_order; off -> None)
        self.phase_frac = sc.get("phase_frac")
        self.units = None
        if sc.get("phase_order"):
            assert self.phase_frac, "phase_order needs a phased scenario (_P10 / _P20)"
            self.units, self.staged = self._unit_cohorts(S, sc, seed)
        pre_B = self._population_ceiling(S, sc, seed) if sc.get("population_ceiling") else None
        # S12 (1 Nov): food-limited crews (work feasts): per-site cap on the hands working a stage (food_cap)
        self.food_cap = self._food_caps(S, sc) if sc.get("food_cap") else None
        # S11 (1 Nov): per-type volume / height factors (type_cost), e.g. protonuraghi
        tc = sc.get("type_cost")
        if tc:
            assert S.tech, "type_cost needs tech_rules"
            ttypes = S.tech["table"].lit_type.to_numpy()
            self.vol_f = np.array([float(tc.get(t, {}).get("volume", 1.0)) for t in ttypes])
            self.hgt_f = np.array([float(tc.get(t, {}).get("height", 1.0)) for t in ttypes])
        # v12 census switches (census_v12.py); self.cz is None when every census key is off (original code path)
        self.cz = None
        if any(sc.get(k) for k in CENSUS_KEYS):
            assert S.tech, "census switches need tech_rules"
            import census_v12
            self.cz = census_v12.Census(self, S, sc, seed)
            if sc.get("size_draw"):                       # S25: per-site volume / height factors drawn by floors
                self.vol_f, self.hgt_f = self.cz.size_factors()
                tc = True
        # S10 smaller crew for the additions (later generation), S13 extra units: per-tower overrides (None = off)
        self.unit_stage = None                 # per site: None or per-tower stage dict {quarry, dress, build}
        self.unit_ls = {}                      # (site, tower) -> lift share of the build stage (accounting only)
        self.n_real = None                     # per site: number of real towers (S13: extra units come after)
        self.add_B = None                      # S10: work party of the additions (later generation), per site
        xu = sc.get("extra_units") or sc.get("rifascio")      # v12 S13_rifascio: an extra unit too
        if xu or (self.units is not None and float(sc["phase_order"].get("addition_crew_factor", 1.0)) != 1.0):
            assert S.tech, "extra_units / addition_crew_factor need tech_rules"
            self.unit_stage = [None] * N
            self.n_real = S.haul.TWR_N.to_numpy().astype(np.int64).copy()
            if self.units is not None and float(sc["phase_order"].get("addition_crew_factor", 1.0)) != 1.0:
                self.add_B = np.zeros(N, np.int64)            # filled per staged site in _gaps_units
        self.towers = []                     # per site: list of (tonnes, S03, S01)
        self.tower_nblk = []                 # per site: pieces per tower (= blocks unless split; S9 hoist, join hands cap)
        # S9 sea faces (30 Oct): blocks carried by boat are split to the craft payload as in model.py. Per site: None
        # (no sea face, or no block above the payload) or per tower {S03, S01, nblk, split_mh, tech, xlift}, used
        # only when the tower's chosen face is a sea face
        self.tower_sea = []
        self.cur_owner, self.cur_sea = -1, False
        cap_sea = float(cfg["sea"]["payload_kg"]) if S.sea_kn else math.inf
        scm = float(cfg["scenarios"]["split_cost_mh"])
        tech = S.tech
        # 1 Nov (b) wider literature: haul profiles (C1 / M3 / M4), stage rates (C2 / C3), carrying (C2), masons (M2)
        hp = sc.get("haul_profile")
        self.hp_site = [None] * N if hp else None
        self.walk_info = np.zeros((N, 2)) if (hp and hp.get("walk")) else None   # M4: walked pieces, walked tonnes
        self.wet_site = np.zeros(N, bool) if (hp and hp.get("wet")) else None     # M3: site hauls on wetted ground
        srates = sc.get("stage_rates")
        self.carry = sc.get("carry")
        if hp or srates or self.carry or sc.get("masons"):
            assert tech, "wider-literature switches need tech_rules"
        if tech:                             # MOST_REALISTIC tech rules: per-site stages, crews, S8 (see _init_tech)
            self.tower_tech = []             # per site, per tower: (crews at the site mu, crews at mu 0.38, crews at mu 0.3, split MH)
            self.site_stage = []             # per site: per-tower stage hours (first tower, before learning)
            self.site_lift_share = np.zeros(N)
            self.s8_rate = float(Ls["learning_rate"]) if tech["lit"].get("learning") else 0.0
        for i in range(N):
            rec = S.haul.iloc[i]
            tw = int(rec.TWR_N)
            rng = np.random.default_rng([seed, int(rec.uid_int)])
            base = round(b["base"] + b["per_extra_tower"] * (tw - 1))
            if pre_B is not None:                             # ceiling pre-pass: same single draw consumed
                rng.uniform(0.0, 1.0)
                self.B[i] = pre_B[i]
            elif sc.get("builders_rule"):                     # per-scenario work-party rule (one draw, as below)
                self.B[i] = lit.draw_builders(sc["builders_rule"], tw, rng)
            else:
                fac = rng.uniform(b["rand_min"], b["rand_max"])
                self.B[i] = int(min(b["max"], max(b["min"], round(base * fac))))
            if self.food_cap is not None:                     # S12: the party cannot exceed what the surplus feeds
                self.B[i] = max(1, min(int(self.B[i]), int(self.food_cap[i])))
            mf = 1.0
            if tech:                                          # S6: block volume fixed, mass x density ratio
                mf = lit.mass_factor(cfg, tech["site"][i], tech["stone"][i])
            target = s["tonnes_per_tower"] * 1000.0 * tw * mf
            tpt = s["tonnes_per_tower"] * 1000.0 * mf         # kg of stone per tower (tower split of the blocks)
            if tc:                                            # S11: volume of this building type vs a tholos tower
                target, tpt = target * self.vol_f[i], tpt * self.vol_f[i]
            if self.cz is not None:                           # v12 S17 fill / S19 mudbrick: share drawn as blocks
                kp = self.cz.keep_share()
                if kp != 1.0:
                    self.cz.tpt_full[i] = tpt
                    target, tpt = target * kp, tpt * kp
            mu, sg, lo, hi = np.log(s["block_median_kg"] * mf), s["block_sigma"], s["block_min_kg"] * mf, s["block_max_kg"] * mf
            chunk = int(target / s["block_median_kg"]) + 16
            parts, tot = [], 0.0
            while tot < target:
                m = np.clip(rng.lognormal(mu, sg, chunk), lo, hi)
                parts.append(m); tot += m.sum()
            m = np.concatenate(parts)
            k = int(np.searchsorted(np.cumsum(m), target)) + 1
            m = m[:k]
            before = np.concatenate([[0.0], np.cumsum(m)[:-1]])
            tid = np.minimum(tw - 1, (before // tpt).astype(np.int64))
            tl = []
            for t in range(tw):
                mt = m[tid == t]
                tl.append((mt.sum() / 1000.0, int(np.ceil(mt / self.pull03).sum()), int(np.ceil(mt / self.pull01).sum())))
            if self.cz is not None and self.cz.fill_f > 0.0:  # v12 S17: the rubble core counts in the tower's tonnes
                tl = [(x[0] + self.cz.fill_tonnes(i), x[1], x[2]) for x in tl]
            self.towers.append(tl)
            sea_i = bool(S.sea_kn) and any(fc.get("sea") for fc in S.faces[i])
            if not tech:
                self.tower_nblk.append([int((tid == t).sum()) for t in range(tw)])
                ts = None
                if sea_i and (m > cap_sea).any():             # S9 payload split on a sea face (model.py Eq. 10 + payload)
                    mx = int(self.B[i])
                    kk = np.maximum(np.maximum(1, np.ceil(m / (self.pull03 * mx))), np.ceil(m / cap_sea)).astype(np.int64)
                    while True:
                        bad = (np.ceil(m / kk / self.pull03) > mx) | (m / kk > cap_sea)
                        if not bad.any():
                            break
                        kk[bad] += 1
                    mp, tp_ = np.repeat(m / kk, kk), np.repeat(tid, kk)
                    cuts = np.bincount(tid, weights=(kk - 1).astype(np.float64), minlength=tw)
                    ts = [{"S03": int(np.ceil(mp[tp_ == t] / self.pull03).sum()),
                           "S01": int(np.ceil(mp[tp_ == t] / self.pull01).sum()),
                           "nblk": int((tp_ == t).sum()), "split_mh": scm * float(cuts[t]), "tech": None, "xlift": 0.0}
                          for t in range(tw)]
                self.tower_sea.append(ts)
            if tech:
                d = tech["site"][i]
                if self.cz is not None and sc.get("lift_override"):   # v12 X_nurtime: lift technique forced
                    d = dict(d, lift=sc["lift_override"])
                pull_i = lit.transport(cfg, d)[0]                  # 30 kgf / mu: 78.9 kg (mu 0.38) or 300 kg (mu 0.1)
                pull38 = Ls["f_person_kgf"] / 0.38
                mx = int(self.B[i])
                prof_i = self._haul_profile(i, pull_i) if hp else None
                if prof_i is not None:                         # C1 / M3: the sledge crews that size block splits
                    pull_i = prof_i[0]

                def pieces(cap, m=m, tid=tid, tw=tw, mx=mx):
                    """model.py Eq. 10: a block whose crew exceeds the work party (or, on a sea face, whose mass
                    exceeds the craft payload `cap`) is split at the quarry into the fewest equal pieces that fit
                    (split_cost_mh per cut, added to that tower's quarry task). -> (piece masses, their towers, cuts)"""
                    kk = np.maximum(1, np.ceil(m / (pull_i * mx))).astype(np.int64)
                    if math.isfinite(cap):
                        kk = np.maximum(kk, np.ceil(m / cap).astype(np.int64))
                    while True:
                        bad = (np.ceil(m / kk / pull_i) > mx) | (m / kk > cap)
                        if not bad.any():
                            break
                        kk[bad] += 1
                    return np.repeat(m / kk, kk), np.repeat(tid, kk), \
                        np.bincount(tid, weights=(kk - 1).astype(np.float64), minlength=tw)

                def tech_t(mp, tp_, cuts, t):
                    return (int(np.ceil(mp[tp_ == t] / pull_i).sum()), int(np.ceil(mp[tp_ == t] / pull38).sum()),
                            int(np.ceil(mp[tp_ == t] / self.pull03).sum()), scm * float(cuts[t]))
                mp, tp_, cuts = pieces(math.inf)
                self.tower_tech.append([tech_t(mp, tp_, cuts, t) for t in range(tw)])
                if self.c01 is not None:                       # v16 L4: rails crews of the same pieces
                    self.c01[i] = [int(np.ceil(mp[tp_ == t] / self.pull01).sum()) for t in range(tw)]
                if prof_i is not None:                         # crews per profile and tower; hands = their sum
                    self._profile_crews(i, prof_i[1], mp, tp_, tw)
                npc = np.bincount(tp_, minlength=tw)
                self.tower_nblk.append([int(x) for x in npc])      # NEW-1: pieces per tower (hoist, hands cap)
                # NEW-1 (30 Oct): lever/stair lift per lifted piece (mp.size = sum of the per-tower piece counts;
                # stage_hours is linear in it, so this equals the sum of per-tower calls); k only fixes the mass
                st_i = lit.stage_hours(cfg, dict(d, learning=False), tw, tech["stone"][i], int(mp.size))   # S8 per tower
                if srates:                                    # C2 / C3: literature stage rates swapped in
                    st_i = self._swap_stage_rates(st_i, d, tw, tech["stone"][i], srates)
                if tc and (self.vol_f[i] != 1.0 or self.hgt_f[i] != 1.0):   # S11: stages scale with the stone volume,
                    st_i = {"quarry": st_i["quarry"] * self.vol_f[i], "dress": st_i["dress"] * self.vol_f[i],
                            "build": st_i["build"] * self.vol_f[i],       # the lift (per piece, already x volume via the
                            "lift": st_i["lift"] * self.hgt_f[i]}         # piece count) with the mean course height
                if self.cz is not None:                       # v12 census stage changes (lift, dressing, mortar, fill...)
                    st_i = self.cz.site_stages(i, st_i, d, tw, mp, tp_, npc, pull_i, pull38)
                self.site_stage.append({"quarry": st_i["quarry"] / tw, "dress": st_i["dress"] / tw,
                                        "build": (st_i["build"] + st_i["lift"]) / tw})
                bl = st_i["build"] + st_i["lift"]
                self.site_lift_share[i] = st_i["lift"] / bl if bl > 0 else 0.0
                ts = None
                if sea_i and (m > cap_sea).any():
                    ms, tps, cs = pieces(cap_sea)
                    nps = np.bincount(tps, minlength=tw)
                    lift_pp = lit.stage_hours(cfg, dict(d, learning=False), tw, tech["stone"][i], 1)["lift"] \
                        if d["lift"] in ("lever", "stair") else 0.0    # per-piece lift (lever/stair only)
                    if tc:
                        lift_pp *= self.hgt_f[i]
                    ts = [{"S03": None, "S01": None, "nblk": int(nps[t]), "split_mh": scm * float(cs[t]),
                           "tech": tech_t(ms, tps, cs, t), "xlift": lift_pp * float(nps[t] - npc[t])} for t in range(tw)]
                    if self.L4:                                # v16 L4: rails crews of the payload-split pieces
                        for t in range(tw):
                            ts[t]["c01"] = int(np.ceil(ms[tps == t] / self.pull01).sum())
                self.tower_sea.append(ts)
                if self.unit_stage is not None:                # S10 smaller addition crews / S13 extra units
                    self._gaps_units(i, seed, rec, tw, m, tid, mf, (mu, sg, lo, hi), d, pieces, tech_t, pull_i,
                                     st_i, mp, npc, sea_i, cap_sea, scm)
                if self.cz is not None:                       # v12 per-tower haul mixes (S18, S23), lintel crews (S20)
                    self.cz.site_towers(i, d, tw, pull_i, pull38)
        self.cap = (self.B * H).astype(np.float64)
        self.masons = sc.get("masons")
        if self.masons:                                    # M2: master masons are extra performers N .. N + M_max - 1
            self._init_masons(S, sc, H)
        if self.cz is not None:                            # v12: lintel wait clock (a performer with no capacity)
            self.cz.init_performers(H)
        if self.add_B is not None:
            self.add_B = np.where(self.add_B > 0, self.add_B, self.B)
            self.B0 = self.B.copy()                        # S10: the keep's party (B changes when the additions start)
        # decision RNG streams: one per community, separate from the block streams
        self.rng = [np.random.default_rng([seed, int(S.haul.uid_int[i]), 7]) for i in range(N)]
        run_rng = np.random.default_rng([seed, 99991])
        self.start_order = run_rng.permutation(N)
        # phased construction (phasing.py; off unless sc['phase_frac']): cohort starts replace start_rate.
        # Own RNG stream, so the run_rng draws (start order, defectors) are untouched.
        self.phase_frac = sc.get("phase_frac")
        if self.phase_frac and self.units is None:
            self.cohorts = phasing.cohorts(N, self.phase_frac, seed)
            self.phase = np.full(N, -1, np.int64)
            for k, c in enumerate(self.cohorts):
                self.phase[c] = k
            self.cur_phase = -1
        elif self.phase_frac:                              # S10 / S11 unit cohorts
            self.cohorts = self.units
            self.phase = np.full(N, -1, np.int64)          # cohort of the site's first unit
            self.phase_add = np.full(N, -1, np.int64)      # S10: cohort of a staged site's additions
            for k, c in enumerate(self.units):
                for (i, t0, t1) in c:
                    if t0 == 0:
                        self.phase[i] = k
                    else:
                        self.phase_add[i] = k
            self.stop_at = np.zeros(N, np.int64)
            self.pause_day = np.full(N, -1, np.int64)      # S10: day the keep was finished (staged sites)
            self.cur_phase = -1
        nd = int(round(float(sc.get("defector_frac", 0.0)) * N))
        self.defector = np.zeros(N, bool)
        if nd:
            self.defector[run_rng.choice(N, nd, replace=False)] = True
        # ---- learning state
        self.Q = [{d: {} for d in DIMS} for _ in range(N)]
        self.cum = np.zeros((N, len(SKILL_STAGES)))           # tower-equivalents of output per skill stage
        self.last_strategy = [None] * N                        # (strategy dict, cost per tonne)
        self.trust = {}                                       # (a, b) -> a's trust in b
        self.received_from = set()                            # (b, a): b has received help from a
        self.help_mh = {}                                     # (helper, owner) -> man-hours
        self.help_stage = {}                                  # (helper, owner, pair-stage) -> [man-hours, tasks]
        self.asks = {}                                        # (asker, asked) -> [asked, refused] (a Nurnet collaborator; bookkeeping only)
        self.asks_stage = {}                                  # (asker, asked, pair-stage) -> [asked, refused]
        self.help_log = {}                                    # (season, helper, owner) -> man-hours (a Nurnet collaborator; bookkeeping)
        self.soc = None                                       # v13 social mechanisms: None when every SOCIAL_KEYS key is off
        if any(sc.get(k) for k in SOCIAL_KEYS):
            self._init_social(sc, N)
        # pre-existing ties (pre_networks.py): adjacency per stage set, copied so tie loss (D8) stays within a run
        tz = sc.get("_ties")
        if tz is None:
            self.ties = None
        elif sc.get("tie_loss_refusals"):                   # D8 removes ties during a run: private mutable copy
            self.ties = {k: [set(int(j) for j in x) for x in v] for k, v in tz.items()}
        else:                                               # read-only sorted arrays, shared (memory: dense tie sets)
            self.ties = tz
        self.tie_refusals = {}
        self._broker = None
        PN = cfg.get("pre_networks", {})
        self.P_tie = float(sc.get("p_tie", PN.get("p_tie", 0.9)))
        self.broker_people = float(sc.get("broker_people", PN.get("broker_people", 1)))
        self.allied_season = {}                               # (a, b), a < b -> first season the pair is allied
        self.open_faces = {}                                  # region -> set of communities that quarried it
        self.track_owner = {}                                 # cell -> owner community
        self.track_use = {}                                   # cell -> use count
        self.handoff_use = {}                                 # (x, y) -> count
        self.strategy_log = []
        self.relay_made = []                                  # v16 S1: per logged tower, 1 = relay hand-off executed
        # ---- tasks (grow as needed)
        self.nt = 0
        cap0 = 4096
        self.t_perf = np.zeros(cap0, np.int64); self.t_total = np.zeros(cap0); self.t_done = np.zeros(cap0)
        self.t_up = np.full(cap0, -1, np.int64); self.t_final = np.zeros(cap0, np.bool_)
        self.t_up2 = np.full(cap0, -1, np.int64)            # join mode: second upstream (the helper's part); -1 = none
        self.join_part = {}                                  # join mode: owner's task id -> helper's task id (same stage)
        self.t_finish = np.full(cap0, -1, np.int64); self.t_stage = np.zeros(cap0, np.int64)
        self.capleft = np.zeros(self.cap.size)
        self.active_tasks = []
        # ---- per-site accounting
        z = lambda: np.zeros(N)
        self.acc = {k: z() for k in ["mh_total", "mh_own", "mh_received", "mh_given", "mh_quarry", "mh_dress",
                                     "mh_transport", "mh_build", "mh_lift", "mh_setup", "mh_track", "mh_walk"]}
        if self.cz is not None:                               # v12 census accounting columns (only when a switch is on)
            self.cz.init_acc()
        self.maint = sc.get("maintenance")                    # S14 (1 Nov): collapses and repairs during the build
        if self.maint:
            self.acc["mh_repair"] = np.zeros(N)              # repair labour, NOT in mh_total (construction)
            self.m_rng = np.random.default_rng([seed, 1401])  # own stream: every other draw is untouched
            self.tower_mh = np.zeros(N)                      # sum of the site's finished towers' man-hours
            self.n_collapse = np.zeros(N, np.int64)
        self.given_stage = np.zeros((N, len(STAGES)))
        self.tower_idx = np.zeros(N, np.int64)
        self.start_day = np.full(N, -1, np.int64); self.finish_day = np.full(N, -1, np.int64)
        self.start_season = np.full(N, -1, np.int64); self.finish_season = np.full(N, -1, np.int64)
        self._order_dirty = True
        self.order = np.zeros(0, np.int64)
        self.current = [None] * N                              # current tower: dict
        self.n_started = 0
        self.start_acc = 0.0
        self.season = 0
        self.day = 0
        self.agents = []
        for i in range(N):
            a = Community(i, comm.Get_rank())
            self.context.add(a)
            self.agents.append(a)
        self.runner.schedule_repeating_event(1, 1, self.season_step)
        self.runner.schedule_stop(int(sc.get("max_seasons", A["max_seasons"])) + 1)

    def _population_ceiling(self, S, sc, seed):
        """Island population ceiling (MOST_REALISTIC; Calo et al. 2008: 41, <= 300,000 inhabitants, second-hand via
        Day 1988; a CEILING, not a baseline). Residents are drawn per site exactly as draw_builders does (the site
        stream's first uniform). The residents of the communities ACTIVE at the same time (P100 / native schedule:
        all sites; P10 / P20: each cohort) must sum to <= the ceiling; otherwise this seed's residents are redrawn from
        default_rng([seed, 31337, k]), k = 1, 2, ... (deterministic; the site streams, hence the blocks, are untouched),
        and after 100 redraws scaled down proportionally. Returns the builders; self.pop_info is written per seed."""
        rule = sc["builders_rule"]
        ceil_ = float(sc["population_ceiling"])
        N = S.N
        tws = S.haul.TWR_N.to_numpy().astype(int)
        res = np.array([lit.draw_residents(rule, int(tws[i]), np.random.default_rng([seed, int(S.haul.uid_int[i])]))
                        for i in range(N)])
        # v16 S3 (addendum 4): the ceiling is checked against all residents of the communities that exist at that time,
        # started or waiting, i.e. every community of the run (was: the active cohort only; v15b code below for the
        # record). The redraw rule is unchanged.
        #   frac = sc.get("phase_frac"); groups = phasing.cohorts(N, frac, seed) if frac else [np.arange(N)]
        #   (S10 / S11: groups = the sites with a unit in each cohort)
        groups = [np.arange(N)]
        peak = lambda r: max(float(r[g].sum()) for g in groups)
        k, scaled = 0, 1.0
        while peak(res) > ceil_ and k < 100:
            k += 1
            rr = np.random.default_rng([seed, 31337, k])
            res = np.array([rr.uniform(*lit.residents_range(rule, int(t))) for t in tws])
        if peak(res) > ceil_:
            scaled = ceil_ / peak(res)
            res = res * scaled
        self.residents = res
        self.pop_info = {"seed": int(seed), "total_residents": float(res.sum()), "active_peak_residents": peak(res),
                         "ceiling": ceil_, "binding": bool(k > 0 or scaled < 1.0), "redraws": k, "scale": scaled,
                         "ceiling_binding": bool(k > 0 or scaled < 1.0), "ceiling_basis": "all_communities_v16_S3"}
        return np.array([lit.builders_of(rule, r) for r in res], np.int64)

    # ------------------------------------------------------------------ 1 Nov 2026 scenario gaps (S10-S14)
    def _unit_cohorts(self, S, sc, seed):
        """S10 / S11: phased construction over ordered BUILD UNITS (site, first tower, stop tower) instead of random
        site cohorts. The base order is phasing.cohorts' own permutation (default_rng([seed, 4242])), so with nothing
        to reorder the cohorts are exactly phasing.cohorts. Units are cut into n_phases equal cohorts (by unit count);
        a cohort starts once every unit of the previous one is built.
          rule types_first (S11): sites whose TYPE is in `types` first (base order inside each group), then the rest.
          rule staged (S10): a complex (TWR_N >= 2) is STAGED with probability staged_share (own stream
              default_rng([seed, 4242, 10])): its keep (tower 1) is a unit in the first group, its additions (towers
              2..k) one later unit; every first-group unit (keeps, single towers, unitary complexes, base order) comes
              before every addition unit (order default_rng([seed, 4242, 11])). A site with both units in one cohort
              builds them as one unit.
        Returns (cohorts: list of lists of (site, t0, t1), staged: bool array)."""
        N = S.N
        po = sc["phase_order"]
        k = phasing.n_phases(self.phase_frac)
        base = np.random.default_rng([int(seed), phasing.PHASE_STREAM]).permutation(N)
        tw = S.haul.TWR_N.to_numpy().astype(np.int64)
        staged = np.zeros(N, bool)
        if po["rule"] == "types_first":
            typ = S.tech["table"].lit_type.to_numpy() if S.tech else \
                np.array([lit.site_types(self.cfg, "TYPE").get(u, "") for u in S.haul.UID])
            first = np.isin(typ, list(po["types"]))
            order = base[np.argsort((~first[base]).astype(np.int64), kind="stable")]
            units = [(int(i), 0, int(tw[i])) for i in order]
        elif po["rule"] == "staged":
            u = np.random.default_rng([int(seed), phasing.PHASE_STREAM, 10]).random(N)
            staged = (tw >= 2) & (u < float(po["staged_share"]))
            units = [(int(i), 0, 1 if staged[i] else int(tw[i])) for i in base]
            add = np.random.default_rng([int(seed), phasing.PHASE_STREAM, 11]).permutation(N)
            units += [(int(i), 1, int(tw[i])) for i in add if staged[i]]
        elif po["rule"] == "emulation":
            # M1 peer-polity emulation (Renfrew & Cherry 1986): cohort 1 = the MR_P10 first cohort; each later cohort is
            # drawn (without replacement, own stream default_rng([seed, 4242, 20])) with weight 1 + strength x (towers
            # of the nuraghi already built within R_m). A cohort starts only when every earlier one is built, so the
            # finished towers at its start are exactly those of the earlier cohorts: the order is fixed at set-up.
            import scipy.sparse as sps
            from scipy.spatial import cKDTree
            sizes = np.diff((np.arange(k + 1) * N) // k)
            pr = cKDTree(S.xy).query_pairs(float(po["R_m"]), output_type="ndarray")
            adj = sps.coo_matrix((np.ones(2 * len(pr)), (np.r_[pr[:, 0], pr[:, 1]], np.r_[pr[:, 1], pr[:, 0]])),
                                 shape=(N, N)).tocsr()
            rr = np.random.default_rng([int(seed), phasing.PHASE_STREAM, 20])
            built = np.zeros(N, bool)
            order = [int(x) for x in base[:sizes[0]]]
            built[base[:sizes[0]]] = True
            for j in range(1, k):
                T = adj @ (tw * built)
                rem = np.flatnonzero(~built)
                w = 1.0 + float(po["strength"]) * T[rem]
                pick = rr.choice(rem, size=int(sizes[j]), replace=False, p=w / w.sum())
                order += [int(x) for x in pick]
                built[pick] = True
            units = [(i, 0, int(tw[i])) for i in order]
        else:
            raise KeyError(po["rule"])
        n = len(units)
        bnd = (np.arange(k + 1) * n) // k
        cohorts = []
        for j in range(k):
            cj = {}
            for (i, t0, t1) in units[bnd[j]:bnd[j + 1]]:
                if i in cj:                                  # keep + additions in one cohort: one unit
                    cj[i] = (i, min(cj[i][1], t0), max(cj[i][2], t1))
                else:
                    cj[i] = (i, t0, t1)
            cohorts.append([cj[i] for i in sorted(cj)])       # gid order, as phasing.cohorts
        return cohorts, staged

    def _food_caps(self, S, sc):
        """S12 work feasts: hands a community can feed on its nuraghe during a season. Per site (tools/food_capacity.py,
        cache file food_cap.catchment_file): cereal-equivalent production P (kg/yr) of its catchment = sum over land-capability
        classes of area x arable share x cropped share x net yield, + pasture area x pasture yield (grain equivalent).
        cap = surplus_share x P / (ration_kg x season_days); at least min_hands. Parameters: food_cap in the scenario."""
        fc = sc["food_cap"]
        t = pd.read_csv(os.path.join(self.cfg["paths"]["cache_dir"], fc["catchment_file"])).set_index("UID")
        t = t.reindex(S.haul.UID.to_numpy())
        assert t.notna().all().all(), "food_cap: a site is missing from the catchment file"
        cls = [c[len("ha_"):] for c in t.columns if c.startswith("ha_")]
        P = np.zeros(S.N)
        for c in cls:
            ha = t["ha_" + c].to_numpy()
            P += ha * float(fc["arable_share"][c]) * float(fc["cropped_share"]) * float(fc["net_yield_kg_ha"])
            if c != "water":                              # pasture on the non-arable land (not on water)
                P += ha * (1.0 - float(fc["arable_share"][c])) * float(fc["pasture_kg_ha"])
        days = float(self.A["season_days"])
        cap = float(fc["surplus_share"]) * P / (float(fc["ration_kg"]) * days)
        self.food_P = P
        return np.maximum(int(fc.get("min_hands", 1)), np.floor(cap)).astype(np.int64)

    def _extra_spec(self, i):
        """S13: extra stone units of site i (antemurale, village huts): list of (name, m3 of masonry, wall height m).
        Masonry volume = length x height x thickness x fill (fill = stone share of the wall volume)."""
        xu = self.sc.get("extra_units") or {}
        tw = int(self.S.haul.TWR_N.iloc[i])
        out = []
        w = xu.get("wall")
        if w and tw >= int(w["min_towers"]):
            per = float(w["perimeter_by_towers"][min(tw, len(w["perimeter_by_towers"])) - 1])
            out.append(("wall", per * float(w["height_m"]) * float(w["thickness_m"]) * float(w["fill"]),
                        float(w["height_m"])))
        v = xu.get("village")
        if v and tw >= int(v["min_towers"]):
            nh = float(v["huts_by_towers"][min(tw, len(v["huts_by_towers"])) - 1])
            circ = math.pi * (float(v["hut_diam_m"]) + float(v["wall_thick_m"]))     # centre line of the hut wall
            out.append(("village", nh * circ * float(v["wall_height_m"]) * float(v["wall_thick_m"]) * float(v["fill"]),
                        float(v["wall_height_m"])))
        if self.cz is not None and self.sc.get("rifascio"):     # v12 S13_rifascio: casing wall around the bastion
            out += self.cz.rifascio_units(i, tw)
        return [u for u in out if u[1] > 0]

    def _gaps_units(self, i, seed, rec, tw, m, tid, mf, bp, d, pieces, tech_t, pull_i, st_i, mp, npc, sea_i, cap_sea,
                    scm):
        """Per-tower stage hours and pieces for S10 (smaller addition party) and S13 (extra units after the towers).
        Real towers keep the site's even per-tower stages (as without the switch) unless their party changes."""
        cfg, sc, S = self.cfg, self.sc, self.S
        L = cfg["lit_scenarios"]
        H = float(cfg["hours_per_day"])
        tech = S.tech
        lift_pp = lit.stage_hours(cfg, dict(d, learning=False), tw, tech["stone"][i], 1)["lift"] \
            if d["lift"] in ("lever", "stair") else 0.0
        if sc.get("type_cost"):
            lift_pp *= self.hgt_f[i]
        per = [dict(self.site_stage[i]) for _ in range(tw)]
        ts = self.tower_sea[i]
        po = sc.get("phase_order") or {}
        fac = float(po.get("addition_crew_factor", 1.0))
        if self.units is not None and fac != 1.0 and self.staged[i]:
            # S10 variant: the additions are built by a later, smaller party: round(fac x B), pieces fit that party
            mx2 = max(1, int(math.floor(fac * float(self.B[i]) + 0.5)))
            self.add_B[i] = mx2
            mp2, tp2, c2 = pieces(math.inf, mx=mx2)
            npc2 = np.bincount(tp2, minlength=tw)
            nl = {"quarry": st_i["quarry"] / tw, "dress": st_i["dress"] / tw, "build": st_i["build"] / tw}
            for t in range(tw):
                n_t = int(npc[t]) if t == 0 else int(npc2[t])
                if t >= 1:
                    self.tower_tech[i][t] = tech_t(mp2, tp2, c2, t)
                    self.tower_nblk[i][t] = n_t
                lf = lift_pp * n_t
                per[t] = {"quarry": nl["quarry"], "dress": nl["dress"], "build": nl["build"] + lf}
                self.unit_ls[(i, t)] = lf / (nl["build"] + lf) if nl["build"] + lf > 0 else 0.0
            if ts is not None:
                ms, tps, cs = pieces(cap_sea, mx=mx2)
                nps = np.bincount(tps, minlength=tw)
                for t in range(1, tw):
                    ts[t] = {"S03": None, "S01": None, "nblk": int(nps[t]), "split_mh": scm * float(cs[t]),
                             "tech": tech_t(ms, tps, cs, t), "xlift": lift_pp * float(nps[t] - npc2[t])}
        if sc.get("extra_units") or sc.get("rifascio"):
            s = cfg["stone"]
            md = L["webster_md_per_tower"]
            share = L["lift_share_of_build"]
            c_h = L["geometry"]["course_height_m"]
            mu, sg, lo, hi = bp
            for k, (nm, m3, h_x) in enumerate(self._extra_spec(i)):
                t_web = m3 * L["webster_density_kg_m3"] / 1000.0          # tonnes at Webster's density
                target = t_web * 1000.0 * mf                              # S6: this site's stone density
                rx = np.random.default_rng([int(seed), int(rec.uid_int), 1301, k])   # own stream: tower blocks untouched
                chunk = int(target / s["block_median_kg"]) + 16
                parts, tot = [], 0.0
                while tot < target:
                    mm = np.clip(rx.lognormal(mu, sg, chunk), lo, hi)
                    parts.append(mm); tot += mm.sum()
                mm = np.concatenate(parts)
                mm = mm[:int(np.searchsorted(np.cumsum(mm), target)) + 1]
                t0 = np.zeros(mm.size, np.int64)
                mpx, tpx, cx = pieces(math.inf, m=mm, tid=t0, tw=1)
                self.towers[i].append((mm.sum() / 1000.0, int(np.ceil(mm / self.pull03).sum()),
                                       int(np.ceil(mm / self.pull01).sum())))
                self.tower_tech[i].append(tech_t(mpx, tpx, cx, 0))
                n_x = int(mpx.size)
                self.tower_nblk[i].append(n_x)
                # stages: S1 quarry rule of the site per m3 (x S6 hardness), no dressing (rough masonry: ASSUMPTION),
                # walling at Webster's build rate per tonne, lift by lever per piece to the mean course of a wall of
                # height h_x (uniform section: mean course index (n_c - 1) / 2)
                q = (L["quarry_ph_m3"][d["quarry"]] * m3) if d["quarry"] != "webster" else \
                    md["quarry"] * lit.md_hours(cfg, "quarry") * t_web / s["tonnes_per_tower"]
                if d.get("density"):
                    q *= L["hardness"].get(tech["stone"][i], 1.0)
                bnl = md["build"] * lit.md_hours(cfg, "build") * (t_web / s["tonnes_per_tower"]) * (1.0 - share)
                n_c = int(math.ceil(h_x / c_h - 1e-9))
                lf = n_x * L["lever_ph_per_block_course"] * (n_c - 1) / 2.0
                idx = len(self.towers[i]) - 1
                per.append({"quarry": q, "dress": 0.0, "build": bnl + lf})
                self.unit_ls[(i, idx)] = lf / (bnl + lf) if bnl + lf > 0 else 0.0
                if sea_i and (ts is not None or (mm > cap_sea).any()):
                    if ts is None:                                     # equivalent entries for the real towers
                        ts = [{"S03": None, "S01": None, "nblk": int(self.tower_nblk[i][t]),
                               "split_mh": float(self.tower_tech[i][t][3]), "tech": self.tower_tech[i][t], "xlift": 0.0}
                              for t in range(idx)]
                        self.tower_sea[i] = ts
                    ms, tps, cs = pieces(cap_sea, m=mm, tid=t0, tw=1)
                    ts.append({"S03": None, "S01": None, "nblk": int(ms.size), "split_mh": scm * float(cs[0]),
                               "tech": tech_t(ms, tps, cs, 0),
                               "xlift": L["lever_ph_per_block_course"] * (n_c - 1) / 2.0 * float(ms.size - n_x)})
        self.unit_stage[i] = per

    # ------------------------------------------------------------------ 1 Nov (b) wider-literature scenarios
    def _wl(self, key):
        """One array of kbest_wl.npz (tools/wl_inputs.py: extra move costs, stream / sand shares), loaded once per Static
        and only if a scenario uses it (memory: 6 ranks). Move costs stay int32 (sums are exact integers)."""
        S = self.S
        if getattr(S, "wl", None) is None:
            S.wl = {}
            full = pd.read_csv(os.path.join(self.cfg["paths"]["cache_dir"], "sites_haul.csv"), usecols=["UID"])
            pos = {u: k for k, u in enumerate(full.UID)}
            S.wl_row = np.array([pos[u] for u in S.haul.UID], np.int64)
        if key not in S.wl:
            with np.load(os.path.join(self.cfg["paths"]["cache_dir"], "alliance", "kbest_wl.npz")) as z:
                S.wl[key] = z[key]
        return S.wl[key]

    def _haul_profile(self, i, pull_i):
        """C1 / C3 loading / M3 / M4: land-haul profiles of site i -> (pull that sizes block splits, profiles).
        A profile = {w: weight of its labour, pull: kg per person, speed: drag m/s, load: loading h per crew member and
        trip, load_ph_t: loading person-hours per tonne (C3), mv: move costs (None = the site's rule: mu 0.38 sledge or
        mu 0.1 rails), sel: all / sledge / walk (M4), hands: counts in the hands cap}. Sea faces are unchanged."""
        hp = self.sc["haul_profile"]
        S, tp, Ls = self.S, self.tp, self.cfg["lit_scenarios"]
        rule = S.tech["rule"][i]
        base = {"w": 1.0, "pull": float(pull_i), "speed": float(tp["drag_speed_ms"]), "load": float(tp["load_unload_h"]),
                "load_ph_t": 0.0, "mv": None, "sel": "all", "hands": True}
        o = hp.get(rule)
        if o:
            if "pull_kg" in o:
                base["pull"] = float(o["pull_kg"])
            if "speed_ms" in o:
                base["speed"] = float(o["speed_ms"])
            if "moves" in o:                               # c03 = the stored mu 0.3 costs of kbest.npz
                base["mv"] = S.mv_c03 if o["moves"] == "c03" else self._wl("mv_" + o["moves"])
            if "load_ph_per_t" in o:                       # C3: lever loading per tonne replaces the crew's 0.25 h
                base["load"], base["load_ph_t"] = 0.0, float(o["load_ph_per_t"])
        if self.L3 and base["load_ph_t"] <= 0.0:          # v16 L3 also on the profile path (fix 6 Nov, GLM docking
            base["load"], base["load_ph_t"] = 0.0, self.lp # F3/F4): rows without their own loading rate get per-tonne
        profs, split = [base], base["pull"]
        w = hp.get("wet")
        if w and rule == "short":                          # M3: sledge on wetted ground (rails are not wetted)
            wet = dict(base, pull=float(Ls["f_person_kgf"]) / float(w["mu"]), mv=self._wl("mv_" + w["moves"]))
            if w["mode"] == "all":                         # upper bound: every dry-ground haul wetted
                profs, split = [wet], wet["pull"]
                self.wet_site[i] = True
            elif w["mode"] == "stream":
                f0 = S.faces[i][0]
                D = int(w["dist_m"])
                if f0["route"] >= 0 and f0["b"] > f0["a"]:
                    ok = bool(self._wl(f"route_wet{D}")[f0["route"]] >= float(w["min_share"]))
                else:
                    ok = bool(self._wl("site_dstream")[S.wl_row[i]] <= D)
                if ok:
                    profs, split = [wet], wet["pull"]
                    self.wet_site[i] = True
            else:                                          # share of the hauling on wetted ground: fixed, or the
                if w["mode"] == "route_share":             # baseline route's length share on wettable ground
                    f0 = S.faces[i][0]
                    if f0["route"] >= 0 and f0["b"] > f0["a"]:
                        f = float(self._wl("route_" + w["key"])[f0["route"]])
                    else:
                        f = float(self._wl("site_" + w["key"])[S.wl_row[i]])
                else:
                    f = float(w["share"])
                profs = [dict(base, w=1.0 - f), dict(wet, w=f, hands=False)]
                self.wet_site[i] = f > 0.0
        if hp.get("walk"):                                 # M4: walked blocks (crews / choice in _profile_crews)
            k = hp["walk"]
            profs = [dict(profs[0], sel="sledge"),
                     {"w": 1.0, "pull": None, "speed": float(k["speed_ms"]), "load": float(k["load_h"]), "load_ph_t": 0.0,
                      "mv": profs[0]["mv"], "sel": "walk", "hands": True, "s_speed": profs[0]["speed"],
                      "s_load": profs[0]["load"]}]
        return split, profs

    def _profile_crews(self, i, profs, mp, tp_, tw):
        """Crews per profile and tower (sum over the tower's pieces). M4: a piece is ELIGIBLE for walking if its mass is
        >= min_kg and its walking crew fits the work party; eligible pieces are grouped per tower by (sledge crew, walking
        crew) and each is walked or sledged, whichever costs less on the leg actually hauled (_leg_mh_tech). Hands cap:
        the sledge crews of all pieces. walk_info: pieces / tonnes walked on the site's baseline route (whole trip)."""
        S = self.S
        k = (self.sc["haul_profile"] or {}).get("walk")
        elig = np.zeros(mp.size, bool)
        if k:
            sl = profs[0]
            cw = np.maximum(float(k["min_crew"]), np.ceil(mp / float(k["kg_per_person"])))
            cs = np.ceil(mp / sl["pull"])
            elig = (mp >= float(k["min_kg"])) & (cw <= float(self.B[i]))
            f0 = S.faces[i][0]
            if f0["route"] >= 0 and f0["b"] > f0["a"]:
                mv = sl["mv"] if sl["mv"] is not None else (S.mv_c01 if S.tech["rule"][i] == "long" else S.mv_c038)
                C, L = float(mv[f0["a"]:f0["b"]].sum()), f0["L"]
            else:
                C, L = f0["C"], f0["L"]
            ts = self.trip(C, L, "whole", sl["speed"], sl["load"])
            tw_ = self.trip(C, L, "whole", float(k["speed_ms"]), float(k["load_h"]))
            wk = elig & (cw * tw_ < cs * ts)
            self.walk_info[i] = (float(wk.sum()), float(mp[wk].sum()) / 1000.0)
        hands = np.zeros(tw)
        for p in profs:
            if p["sel"] == "walk":
                p["crews"] = [0] * tw
                p["pairs"] = []
                for t in range(tw):
                    sel = elig & (tp_ == t)
                    if sel.any():
                        u, cnt = np.unique(np.stack([cs[sel], cw[sel]], 1), axis=0, return_counts=True)
                        p["pairs"].append((u[:, 0].astype(np.float64), u[:, 1].astype(np.float64), cnt.astype(np.float64)))
                    else:
                        p["pairs"].append((np.zeros(0), np.zeros(0), np.zeros(0)))
                continue
            c = np.ceil(mp / p["pull"])
            sel = ~elig if p["sel"] == "sledge" else np.ones(mp.size, bool)
            p["crews"] = [int(c[sel & (tp_ == t)].sum()) for t in range(tw)]
            if p["hands"]:
                hands += np.array([c[tp_ == t].sum() for t in range(tw)]) if p["sel"] == "sledge" else \
                    np.array(p["crews"], np.float64)
        self.tower_tech[i] = [(int(hands[t]),) + tuple(tt[1:]) for t, tt in enumerate(self.tower_tech[i])]
        self.hp_site[i] = profs

    def _swap_stage_rates(self, st, d, tw, stone, R):
        """C2 / C3: replace stage person-hours of one site by literature rates per m3 of stone (tower volume held as in
        S6: tonnes_per_tower / Webster's density = 566 m3 per tower). quarry_ph_m3 {S1 rule: rate} (x S6 hardness);
        build_ph_m3: walling (lift unchanged); facade_dress_ph_m3: dressing of the facing of fine-dressed complexes
        (Webster dressing + facing m3 x rate, x hardness)."""
        cfg = self.cfg
        L = cfg["lit_scenarios"]
        H = float(cfg["hours_per_day"])
        vol = cfg["stone"]["tonnes_per_tower"] * 1000.0 / L["webster_density_kg_m3"] * tw
        h = L["hardness"].get(stone, 1.0) if d.get("density") else 1.0
        st = dict(st)
        q = R.get("quarry_ph_m3") or {}
        if d["quarry"] in q:
            st["quarry"] = float(q[d["quarry"]]) * vol * h
        if "build_ph_m3" in R:
            st["build"] = float(R["build_ph_m3"]) * vol
        wdh = R.get("webster_dress_hours")                 # C2: Webster's man-days read as 5-h (Erasmus) days
        Hd = lit.md_hours(cfg, "dress")                    # v11: Webster's dressing man-day (Abrams, 8 h); H when off
        if wdh and d["dress"] == "webster":
            st["dress"] *= float(wdh) / Hd
        elif wdh and d["dress"] == "fine" and tw >= L["fine_min_towers"]:
            st["dress"] -= L["webster_md_per_tower"]["dress"] * (Hd - float(wdh)) * tw * h
        if "facade_dress_ph_m3" in R and d["dress"] == "fine" and tw >= L["fine_min_towers"]:
            g = L["geometry"]
            R0, R1, Hh = g["base_diam_m"] / 2, g["top_diam_m"] / 2, g["tower_height_m"]
            area = math.pi * (R0 + R1) * math.sqrt(Hh ** 2 + (R0 - R1) ** 2)
            facing = area * L["facing_thickness_m"] * tw
            st["dress"] = (L["webster_md_per_tower"]["dress"] * Hd * tw + facing * float(R["facade_dress_ph_m3"])) * h
        return st

    def _init_masons(self, S, sc, H):
        """M2 mobile master masons (Bevan & Bloxam 2016): an island-wide pool; a tower that needs one (need: tholos =
        every non-corridor nuraghe, complex = towers of complexes only) builds its lower courses, then waits for a free
        master (first come first served, the nearest free master goes), who walks there (straight line / walking
        speed, his own 8-h days) before the vault share of the build stage can start; the master is released when the
        tower is finished. Apprenticeship: one new master (at that site) after every per_new vaults completed."""
        M = self.masons
        tw = S.haul.TWR_N.to_numpy().astype(np.int64)
        typ = S.tech["table"].lit_type.to_numpy()
        need = ~np.isin(typ, list(M.get("exempt_types", [])))
        if M.get("need", "tholos") == "complex":
            need &= tw >= 2
        self.m_need = need
        self.m_max = int(M["pool0"]) + int(tw[need].sum()) // int(M["per_new"]) + 1
        self.cap = np.concatenate([self.cap, np.full(self.m_max, H)])
        self.m_n = int(M["pool0"])
        self.m_busy = np.zeros(self.m_max, bool)
        self.m_loc = np.full((self.m_max, 2), np.nan)          # unknown start: the first job needs no walk
        self.m_queue = []
        self.m_vaults = 0
        self.m_wait = np.zeros(S.N); self.m_travel_h = np.zeros(S.N); self.m_nvault = np.zeros(S.N, np.int64)
        if self.cz is not None and sc.get("mason_regions"):   # v12 M2_regional: pools confined to regions
            self.cz.init_masons_regional(tw, need, H)

    def _mason_event(self, i, day):
        cur = self.current[i]
        if cur["mphase"] == "lower":                     # lower courses done: queue for a master
            cur["mphase"] = "wait"
            cur["qday"] = day
            self.m_queue.append(i)
        else:                                             # master arrived: the vault task(s)
            cur["final_task"] = cur["vault_fn"]()
            cur["mphase"] = "vault"
        self._order_dirty = True

    def _assign_masons(self):
        if self.cz is not None and self.cz.mreg is not None:
            return self.cz.assign_masons_regional()
        while self.m_queue:
            free = np.flatnonzero(~self.m_busy[:self.m_n])
            if free.size == 0:
                return
            i = self.m_queue.pop(0)
            cur = self.current[i]
            xy = self.S.xy[i]
            lc = self.m_loc[free]
            d = np.where(np.isnan(lc[:, 0]), 0.0, np.hypot(lc[:, 0] - xy[0], lc[:, 1] - xy[1]))
            j = int(np.argmin(d))
            k, dist = int(free[j]), float(d[j])
            self.m_busy[k] = True
            cur["master"] = k
            self.m_wait[i] += max(0, self.day - 1 - int(cur["qday"]))
            hrs = dist / float(self.tp["return_walk_ms"]) / 3600.0
            if hrs > 0:
                cur["final_task"] = self.add_task(self.N + k, hrs, "build", -1, True)
                cur["mphase"] = "travel"
                self.m_travel_h[i] += hrs
            else:
                cur["final_task"] = cur["vault_fn"]()
                cur["mphase"] = "vault"
            self._order_dirty = True

    def _release_master(self, i, k):
        if self.cz is not None and self.cz.mreg is not None:
            return self.cz.release_master_regional(i, k)
        self.m_busy[k] = False
        self.m_loc[k] = self.S.xy[i]
        self.m_vaults += 1
        self.m_nvault[i] += 1
        if self.m_vaults % int(self.masons["per_new"]) == 0 and self.m_n < self.m_max:
            self.m_loc[self.m_n] = self.S.xy[i]          # apprenticeship: a new master trained at this site
            self.m_n += 1

    # ------------------------------------------------------------------ v13 social mechanisms (ODD 7.15, CODE_PROVENANCE.md)
    def _init_social(self, sc, N):
        """State of the v13 switches. reputation: per community, the log of its acts as an ASKED community, (requester,
        good) in time order; an observer k sees the act iff k is the requester or within R of it (R = the run's
        interaction radius, S.R). partner_choice: `cheated` = {(a, b): b refused a after having received help from a,
        and has not helped a since}. tie_imitation / social_log: help adjacency (help actually given or received,
        mh > 0) and the imitated source per tower start."""
        self.soc = {"rep": bool(sc.get("reputation")), "pc": bool(sc.get("partner_choice")),
                    "tie": bool(sc.get("tie_imitation")),
                    "log": [[] for _ in range(N)], "cheated": set(), "adj": [set() for _ in range(N)],
                    "strat": [], "src": -1, "linked": 0,
                    "n_shunned": np.zeros(N, np.int64), "n_shun_given": np.zeros(N, np.int64),
                    "n_bad": np.zeros(N, np.int64), "n_good": np.zeros(N, np.int64),
                    "n_pc_refused": np.zeros(N, np.int64), "n_pc_refuse_given": np.zeros(N, np.int64),
                    "n_cheat": np.zeros(N, np.int64)}
        self.soc["R"], self.soc["gentle"] = float(self.S.R), reputation_rule(sc) == "gentle"; _init_kd(self, sc)   # v13g, v13kd (end of file)

    def _bad(self, k, i):
        """Reputation: does observer k see community i in bad standing? i's most recent act (as an asked community) that
        k observed decides: a help -> good, an unjustified refusal -> bad; none observed -> good (Nowak & Sigmund 2005;
        Panchanathan & Boyd 2004: justified refusals are not logged, see _social_gate)."""
        xy, R = self.S.xy, self.soc["R"]
        for r, good in reversed(self.soc["log"][i]):
            if r == k or math.hypot(xy[r, 0] - xy[k, 0], xy[r, 1] - xy[k, 1]) <= R:
                return not good
        return False

    def _social_gate(self, i, j, ok):
        """v13: j has been asked by i and its decision `ok` is drawn (the draw is always made, so the random streams stay
        aligned with the switches off). Partner choice: j declines a requester that cheated it (refused j after receiving
        j's help). Reputation: a non-defector j declines a requester it sees in bad standing (third-party shunning). Such
        refusals are JUSTIFIED: they give j no bad standing and do not count as cheating. Returns the decision."""
        so = self.soc
        just = False
        if so["pc"] and (j, i) in so["cheated"]:
            if ok:
                so["n_pc_refused"][i] += 1; so["n_pc_refuse_given"][j] += 1
            ok, just = False, True
        if so["rep"] and not self.defector[j] and self._bad(j, i):
            if ok:
                so["n_shunned"][i] += 1; so["n_shun_given"][j] += 1
            ok, just = False, True
        if so["rep"]:
            if ok:
                so["log"][j].append((i, True)); so["n_good"][j] += 1
            elif not just and (not so["gentle"] or self.defector[j] or (j, i) in self.received_from):   # v13g
                so["log"][j].append((i, False)); so["n_bad"][j] += 1
        if so["pc"]:
            if ok:
                so["cheated"].discard((i, j))                 # j has now helped i: forgiven
            elif not just and (j, i) in self.received_from:   # j refuses after having received help from i
                so["cheated"].add((i, j)); so["n_cheat"][j] += 1
        return ok

    def _partner_order(self, i, cands):
        """Partner choice: stable reordering of i's candidate list into 3 groups: exchange partners first (j has helped
        i, or i has helped j and j has not cheated i: a partner that owes i a return), then the rest, then the
        communities that cheated i; the existing order (skill, trust, distance, id / tie hops) is kept inside each group."""
        rf, ch = self.received_from, self.soc["cheated"]

        def g(c):
            j = c[0]
            if (i, j) in ch:
                return 2
            return 0 if ((i, j) in rf or (j, i) in rf) else 1
        return sorted(cands, key=g)

    def _imit_pool(self, i):
        """Imitation models of i. tie_imitation: the communities linked to i by help given or received (mh > 0), ordered
        by distance then id like S.nb; a community with no such tie falls back to its neighbours within R (S.nb)."""
        adj = self.soc["adj"][i]
        if not self.soc["tie"] or not adj:
            return self.S.nb[i][0]
        xy = self.S.xy
        v = np.fromiter(adj, np.int64, len(adj))
        d = np.hypot(xy[v, 0] - xy[i, 0], xy[v, 1] - xy[i, 1])
        return v[np.lexsort((v, d))]

    # ------------------------------------------------------------------ helpers
    def wdist(self, p, loc, tgt=None):
        """Walking distance of community p's people to loc. S9: min(straight line, sea travel time x walk speed);
        tgt = the site index when loc is a nuraghe."""
        S = self.S
        d = math.hypot(S.xy[p, 0] - loc[0], S.xy[p, 1] - loc[1])
        if S.travel is None:
            return d
        return S.travel.point_dist(S.uid[p], loc[0], loc[1], d, self.tp["return_walk_ms"],
                                   None if tgt is None else S.uid[tgt])

    def _stage(self, i, name):
        """Per-tower labour of a skill stage before skill / learning: Webster island-wide, or the site's own
        (tech rules)."""
        if self.unit_stage is not None and self.unit_stage[i] is not None:      # S10 / S13 per-tower stages
            return self.unit_stage[i][int(self.tower_idx[i])][name]
        if self.cz is not None and self.cz.q_tower is not None and name == "quarry" and self.cz.q_tower[i] is not None:
            return self.cz.q_tower[i][int(self.tower_idx[i])]        # v12 S18: per-tower quarry (clearance stone first)
        return self.base_stage[name] if self.S.tech is None else self.site_stage[i][name]

    def T(self, a, b):
        return self.trust.get((a, b), float(self.A["trust0"]))

    def allied(self, a, b):
        th = float(self.A["alliance_threshold"])
        return a == b or (self.T(a, b) >= th and self.T(b, a) >= th)

    def skill(self, j, stage):
        if stage not in SKILL_STAGES or self.b == 1.0:
            return 1.0
        return (1.0 + self.cum[j, SKILL_STAGES.index(stage)]) ** self.expo

    def backlog_days(self, j):
        rem = 0.0
        for t in self.active_tasks:
            if self.t_perf[t] == j:
                rem += self.t_total[t] - self.t_done[t]
        return rem / self.cap[j]

    def add_task(self, perf, total, stage, up=-1, final=False):
        if self.nt == self.t_perf.size:
            n = self.t_perf.size * 2
            for name, fill in (("t_perf", 0), ("t_total", 0.0), ("t_done", 0.0), ("t_up", -1), ("t_up2", -1), ("t_final", False),
                               ("t_finish", -1), ("t_stage", 0)):
                a = getattr(self, name)
                b = np.full(n, fill, a.dtype); b[:a.size] = a; setattr(self, name, b)
        t = self.nt
        self.nt += 1
        self.t_perf[t] = perf; self.t_total[t] = total; self.t_done[t] = 0.0; self.t_up[t] = up
        self.t_up2[t] = self.join_part.get(up, -1) if self.join_part else -1
        self.t_final[t] = final; self.t_finish[t] = -1; self.t_stage[t] = STAGES.index(stage)
        self.active_tasks.append(t)
        return t

    def charge(self, owner, perf, mh, stage, walk=0.0):
        """Labour mh (incl. walk) by perf, spent on owner's nuraghe."""
        A = self.acc
        A["mh_total"][owner] += mh
        A["mh_walk"][owner] += walk
        if perf == owner:
            A["mh_own"][owner] += mh
        else:
            A["mh_received"][owner] += mh
            A["mh_given"][perf] += mh
            self.given_stage[perf, STAGES.index(stage)] += mh
            self.help_mh[(perf, owner)] = self.help_mh.get((perf, owner), 0.0) + mh
            hs = self.help_stage.setdefault((perf, owner, PAIR_STAGE[stage]), [0.0, 0])
            hs[0] += mh; hs[1] += 1
            k = (self.season, perf, owner)
            self.help_log[k] = self.help_log.get(k, 0.0) + mh
            if self.soc is not None and mh > 0.0:              # v13: help ties (imitation along ties, logging)
                self.soc["adj"][perf].add(owner); self.soc["adj"][owner].add(perf)
        w = mh - walk
        if stage == "build":
            ls = self.lift_share if self.S.tech is None else self.site_lift_share[owner]
            if self.unit_ls:                                  # S10 / S13 per-tower lift share (accounting only)
                ls = self.unit_ls.get((owner, int(self.tower_idx[owner])), ls)
            A["mh_build"][owner] += w * (1.0 - ls); A["mh_lift"][owner] += w * ls
        elif stage in ("leg1", "transport"):
            A["mh_transport"][owner] += w
        elif stage == "track":
            A["mh_track"][owner] += w
        else:
            A["mh_" + stage][owner] += w

    # ------------------------------------------------------------------ requests and trust
    def charge_brokers(self, i, stage):
        """Brokers' walking (reach > 1): each broker walks to the next community on the path and back."""
        if not self._broker:
            return
        for b, nxt, d in self._broker:
            if self.S.travel is not None:                 # S9: brokers may go by sea
                d = self.S.travel.site_dist(self.S.uid[b], self.S.uid[nxt], d, self.tp["return_walk_ms"])
            mh = self.broker_people * 2.0 * d / self.tp["return_walk_ms"] / 3600.0
            self.charge(i, b, mh, stage, mh)
        self._broker = None

    def request(self, i, stage, loc_xy, cands):
        """i asks candidates (ordered) to perform a stage task; returns helper or -1. Updates trust."""
        A = self.A
        fixed = self.sc.get("accept_fixed")
        self._broker = None
        for j, dij, mode, hops, legs in cands[: int(A["max_asks"])]:
            if self.defector[j]:
                ok = False
            elif mode == "tie":
                ok = self.rng[j].random() < float(self.P_tie)
            elif fixed is not None:
                ok = self.rng[j].random() < float(fixed)
            else:
                x = (A["beta0"] + A["beta1"] * self.T(j, i) - A["beta2"] * self.backlog_days(j)
                     - (0.0 if self.soc is not None and self.soc["kd"] and _kd_pair(self, i, j) else A["beta3"] * dij / 1000.0))   # v13kd
                if self.cz is not None and self.cz.feast is not None:   # v12 S12b: the host's surplus attracts help
                    x += self.cz.feast[i]
                ok = self.rng[j].random() < sigmoid(x)
            if self.soc is not None:                     # v13 partner choice / reputation (no random draws)
                ok = self._social_gate(i, j, ok)
            # ask/refusal counters (a Nurnet collaborator's patch, all decision branches; no random draws)
            ak = self.asks.setdefault((i, j), [0, 0]); ak[0] += 1
            ks = self.asks_stage.setdefault((i, j, PAIR_STAGE[stage]), [0, 0]); ks[0] += 1
            if not ok:
                ak[1] += 1; ks[1] += 1
            if mode == "tie" and not ok and self.sc.get("tie_loss_refusals"):
                self.tie_refusals[(i, j)] = self.tie_refusals.get((i, j), 0) + 1
                if self.tie_refusals[(i, j)] >= int(self.sc["tie_loss_refusals"]):       # D8: the tie is lost
                    for adj in self.ties.values():
                        adj[i].discard(j); adj[j].discard(i)
            if self.sc.get("trust", False) and mode != "tie":
                if ok:                                   # j reciprocates / helps i: i trusts j more
                    self.trust[(i, j)] = min(1.0, self.T(i, j) + float(A["delta_up"]))
                elif (j, i) in self.received_from:       # j refuses after having received help from i
                    self.trust[(i, j)] = max(0.0, self.T(i, j) - float(A["delta_down"]))
                pk = (min(i, j), max(i, j))
                if pk not in self.allied_season and self.allied(i, j):
                    self.allied_season[pk] = self.season
            if ok:
                self.received_from.add((i, j))
                if hops > 1:
                    self._broker = legs[1:]                         # each broker passes the request on: its leg onward
                return j
        return -1

    def tie_candidates(self, i, stage, quarry_xy=None, nearer_than=None):
        """Communities reachable along the stage's ties within `reach` hops, ordered by (hops, distance, id):
        (j, distance, 'tie', hops, broker legs). Only the first max_asks are returned (only they can be asked)."""
        key = "stone" if stage in ("quarry", "dress") else ("move" if stage in ("leg1", "transport") else "build")
        adj = self.ties[key]
        h = int(self.sc.get("reach", 1))
        xy = self.S.xy
        if len(adj[i]) == 0:
            return []
        if h == 1:
            v = np.fromiter(adj[i], np.int64, len(adj[i]))
            hop = np.ones(v.size, np.int64)
            seen = None
        else:
            seen = {i: None}
            frontier = [i]
            vv, hh = [], []
            for hp in range(1, h + 1):
                nxt = []
                for u in frontier:
                    for w in sorted(int(x) for x in adj[u]):
                        if w not in seen:
                            seen[w] = u
                            nxt.append(w); vv.append(w); hh.append(hp)
                frontier = nxt
            v = np.array(vv, np.int64); hop = np.array(hh, np.int64)
        d = np.hypot(xy[v, 0] - xy[i, 0], xy[v, 1] - xy[i, 1])
        if nearer_than is not None:
            keep = np.hypot(xy[v, 0] - quarry_xy[0], xy[v, 1] - quarry_xy[1]) < nearer_than
            v, hop, d = v[keep], hop[keep], d[keep]
        o = np.lexsort((v, d, hop))[: int(self.A["max_asks"])]
        out = []
        for k in o:
            j = int(v[k])
            legs = ()
            if hop[k] > 1:
                path = [j]
                while seen[path[-1]] is not None:
                    path.append(seen[path[-1]])
                path = path[::-1]
                legs = tuple((path[q], path[q + 1], math.hypot(*(xy[path[q + 1]] - xy[path[q]]))) for q in range(len(path) - 1))
            out.append((j, float(d[k]), "tie", int(hop[k]), legs))
        return out

    def candidates(self, i, stage, quarry_xy=None, nearer_than=None):
        if self.soc is not None and self.soc["pc"]:     # v13 partner choice: reorder the existing list
            return self._partner_order(i, self._candidates(i, stage, quarry_xy, nearer_than))
        return self._candidates(i, stage, quarry_xy, nearer_than)

    def _candidates(self, i, stage, quarry_xy=None, nearer_than=None):
        if self.ties is not None:
            out = self.tie_candidates(i, stage, quarry_xy, nearer_than)
            if not self.sc.get("trust", False):
                return out
            tied = {c[0] for c in out}
            rest = [c for c in self._candidates_R(i, stage, quarry_xy, nearer_than) if c[0] not in tied]
            return out + rest
        return self._candidates_R(i, stage, quarry_xy, nearer_than)

    def _candidates_R(self, i, stage, quarry_xy=None, nearer_than=None):
        nb, d = self.S.nb[i]
        out = []
        for j, dij in zip(nb, d):
            j = int(j)
            if nearer_than is not None:
                dq = math.hypot(self.S.xy[j, 0] - quarry_xy[0], self.S.xy[j, 1] - quarry_xy[1])
                if dq >= nearer_than:
                    continue
            out.append((j, float(dij)))
        sk = self.sc.get("specialisation", False)
        out.sort(key=lambda c: ((self.skill(c[0], stage) if sk else 1.0), -self.T(i, c[0]), c[1], c[0]))
        return [(j, dij, "R", 0, ()) for j, dij in out]

    # ------------------------------------------------------------------ decisions
    def choose(self, i, dims_values):
        """Factored epsilon-greedy over each action dimension, with social imitation."""
        A = self.A
        rng = self.rng[i]
        strat, imit = {}, False
        near = self.S.near is not None and bool(self.S.near[i])   # v14: near site -> face 0, no face draw
        if self.sc.get("imitation", True) and rng.random() < float(A["p_imit"]):
            own = self.last_strategy[i][1] if self.last_strategy[i] else math.inf
            best = None
            src = -1
            for j in (self.S.nb[i][0] if self.soc is None else self._imit_pool(i)):   # v13: help ties (tie_imitation)
                ls = self.last_strategy[int(j)]
                if ls and ls[1] < own and (best is None or ls[1] < best[1]):
                    best = ls
                    src = int(j)
            if self.soc is not None:                      # v13 bookkeeping: imitated source, and is it a help tie?
                self.soc["src"] = src if best is not None else -1
                self.soc["linked"] = int(best is not None and src in self.soc["adj"][i])
            if best is not None:
                imit = True
                for dname, vals in dims_values.items():
                    if dname == "quarry_face":
                        if near:                          # v14: the face is never imitated by a near site
                            continue
                        regs = [f["region"] for f in self.S.faces[i]]
                        if best[0].get("quarry_region") in regs:
                            strat[dname] = regs.index(best[0]["quarry_region"])
                    elif best[0].get(dname) in vals:
                        strat[dname] = best[0][dname]
        for dname, vals in dims_values.items():
            if dname in strat:
                continue
            if self.sc.get("fixed_actions") and dname in self.sc["fixed_actions"]:
                strat[dname] = self.sc["fixed_actions"][dname]
                continue
            if near and dname == "quarry_face":           # v14: face 0, no epsilon draw, no Q choice (draw skipped)
                strat[dname] = 0
                continue
            q = self.Q[i][dname]
            if rng.random() < float(A["epsilon"]):
                strat[dname] = vals[int(rng.integers(len(vals)))]
            else:
                vq = [q.get(v, 0.0) for v in vals]             # untried actions start at 0 (optimistic)
                m = max(vq)
                best = [v for v, x in zip(vals, vq) if x == m]
                strat[dname] = best[int(rng.integers(len(best)))]
        return strat, imit

    def route_costs(self, i, face, a, b):
        """Leg cost for moves a..b of a face route given tracks usable by i: (C for mu0.3 crews, C for mu0.1 crews,
        tracked share of the mu0.3 cost, length)."""
        S = self.S
        c03 = S.mv_c03[a:b]; c01 = S.mv_c01[a:b]; ln = S.mv_len[a:b]
        if not self.track_owner:
            return float(c03.sum()), math.inf, 0.0, float(ln.sum())
        cells = S.mv_cell[a:b]
        acc = np.array([(c in self.track_owner) and self.allied(i, self.track_owner[c]) for c in cells], bool)
        if not acc.any():
            return float(c03.sum()), math.inf, 0.0, float(ln.sum())
        ca = np.where(acc, np.maximum(0.5 * ln, c01 * (self.A["track_mu"] / 0.3)), c03)   # mu0.3 crew on track
        cb = np.where(acc, c01, np.maximum(0.5 * ln, c03 * (0.3 / self.A["track_mu"])))   # mu0.1 crew off track
        return float(ca.sum()), float(cb.sum()), float(c03[acc].sum() / max(c03.sum(), 1e-9)), float(ln.sum())

    def trip(self, C, L, part, v=None, ld=None):
        tp = self.tp
        if v is not None:                                  # wider-lit haul profiles: own drag speed / loading time
            if part == "whole":
                return max(C, tp["min_haul_flatm"]) / v / 3600.0 + \
                    max(L, tp["min_haul_flatm"]) / tp["return_walk_ms"] / 3600.0 + ld
            return C / v / 3600.0 + L / tp["return_walk_ms"] / 3600.0 + ld / 2.0
        if part == "whole":
            return max(C, tp["min_haul_flatm"]) / tp["drag_speed_ms"] / 3600.0 + \
                max(L, tp["min_haul_flatm"]) / tp["return_walk_ms"] / 3600.0 + tp["load_unload_h"]
        return C / tp["drag_speed_ms"] / 3600.0 + L / tp["return_walk_ms"] / 3600.0 + tp["load_unload_h"] / 2.0

    def leg_mh(self, i, face, a, b, S03, S01, part, use_track=True, nblk=0):
        if self.S.tech is not None:
            return self._leg_mh_tech(i, face, a, b, S03, part, nblk)
        if face.get("sea"):                               # S9: whole sea chain, no tracks / relays on it
            sv = self._sea_variant()
            if sv is not None:                            # payload split: the pieces' crews and hoists (30 Oct)
                S03, nblk = sv["S03"], sv["nblk"]
            return S03 * face["trip_h"] + nblk * face["hoist_ph"], 0
        if face["route"] < 0 or a == b:
            C, L = (face["C"], face["L"]) if part == "whole" else (0.0, 0.0)
            return S03 * self.trip(C, L, part), 0
        Ca, Cb, share, L = self.route_costs(i, face, a, b) if use_track else \
            (float(self.S.mv_c03[a:b].sum()), math.inf, 0.0, float(self.S.mv_len[a:b].sum()))
        if part == "whole" and face["route"] >= 0 and a == face["a"] and b == face["b"] and share == 0.0:
            Ca, L = face["C"], face["L"]                  # untracked whole route: exactly the baseline haul
        ma = S03 * self.trip(Ca, L, part)
        mb = S01 * self.trip(Cb, L, part) if math.isfinite(Cb) else math.inf
        return (ma, 0) if ma <= mb else (mb, 1)

    def _leg_mh_tech(self, i, face, a, b, S03, part, nblk):
        if self.cz is None or face.get("sea"):
            return self._leg_mh_tech0(i, face, a, b, S03, part, nblk)
        return self.cz.leg_mh(i, face, a, b, S03, part, nblk)        # v12: carts (S24), haul mixes (S18, S23)

    def _leg_mh_tech0(self, i, face, a, b, S03, part, nblk):
        """Tech rules: the site's own friction on every land face (rails mu 0.1 = kbest mu0.1 move costs and
        300 kg/person crews; dry ground mu 0.38 = kbest_mu038 move costs and 78.9 kg/person crews). Sea faces:
        land legs as dry-ground sledges (S038 crews x the sea table's land legs), boat leg as in S9 (S03 crews x
        boat time; the boat factor is defined per 100 kg/person). The owner's (i's) rule applies to the face,
        whoever performs the leg (a relay helper hauls the same blocks on the same prepared route)."""
        S = self.S
        o = self.cur_owner
        Ssite, S038, S03p, _ = self.tower_tech[o][int(self.tower_idx[o])]
        if face.get("sea"):
            sv = self._sea_variant()
            c01 = None
            if sv is not None:                            # payload split: the pieces' crews and hoists (30 Oct)
                (Ssite, S038, S03p, _), nblk = sv["tech"], sv["nblk"]
                c01 = sv.get("c01")
            if "legs" in face:                            # v16 L4: land legs at the site's rule, loading per L3
                return self._sea_l4_mh(o, face, Ssite, S038, S03p, nblk, c01), 0
            return S038 * face["land_h"] + S03p * face["boat_h"] + nblk * face["hoist_ph"], 0
        if self.carry is not None and part == "whole" and face["L"] <= float(self.carry["max_m"]):
            # C2 (Erasmus 1965): short hauls at a literature rate per tonne (flat up to max_m) or per tonne-metre
            tn = self.towers[o][int(self.tower_idx[o])][0]
            if "ph_per_t" in self.carry:
                return tn * float(self.carry["ph_per_t"]), 0
            return tn * max(face["L"], float(self.tp["min_haul_flatm"])) * float(self.carry["ph_per_t_m"]), 0
        prof = self.hp_site[o] if self.hp_site is not None else None
        if prof is not None:                              # C1 / M3 / M4 haul profiles (crews, speed, friction)
            t_o = int(self.tower_idx[o])
            mh = 0.0
            for p in prof:
                n = p["crews"][t_o]
                if p["sel"] == "walk":                    # M4: each eligible piece walked or sledged, whichever is
                    cs_, cw_, cn_ = p["pairs"][t_o]       # cheaper on THIS leg (pieces grouped by crew sizes)
                    if cn_.size == 0:
                        continue
                    n = 1
                if n <= 0 and p["sel"] == "sledge" and p["load_ph_t"] > 0.0 and p["w"] > 0.0:
                    tn = self._load_t(o, t_o)             # M4 + L3: loading per tonne of the tower is booked on the sledge
                    mh += p["w"] * tn * p["load_ph_t"] * (1.0 if part == "whole" else 0.5)   # profile even if every
                    continue                              # piece is eligible for walking (fix 6 Nov)
                if n <= 0 or p["w"] <= 0.0:
                    continue
                if face["route"] < 0 or a == b:
                    C, L = (face["C"], face["L"]) if part == "whole" else (0.0, 0.0)
                else:
                    mv = p["mv"] if p["mv"] is not None else (S.mv_c01 if S.tech["rule"][o] == "long" else S.mv_c038)
                    C = float(mv[a:b].sum())
                    L = face["L"] if (part == "whole" and a == face["a"] and b == face["b"]) else float(S.mv_len[a:b].sum())
                if p["sel"] == "walk":
                    ts = self.trip(C, L, part, p["s_speed"], p["s_load"])
                    tw = self.trip(C, L, part, p["speed"], p["load"])
                    mh += p["w"] * float((cn_ * np.minimum(cs_ * ts, cw_ * tw)).sum())
                    continue
                mh += p["w"] * n * self.trip(C, L, part, p["speed"], p["load"])
                if p["load_ph_t"] > 0.0:                  # C3: lever loading + unloading per tonne (half per relay leg)
                    tn = self._load_t(o, t_o)
                    mh += p["w"] * tn * p["load_ph_t"] * (1.0 if part == "whole" else 0.5)
            return mh, 0
        if face["route"] < 0 or a == b:
            C, L = (face["C"], face["L"]) if part == "whole" else (0.0, 0.0)
            return self._crew_trip_mh(Ssite, C, L, part, o), 0
        mv = S.mv_c01 if S.tech["rule"][o] == "long" else S.mv_c038
        C = float(mv[a:b].sum())
        L = face["L"] if (part == "whole" and a == face["a"] and b == face["b"]) else float(S.mv_len[a:b].sum())
        return self._crew_trip_mh(Ssite, C, L, part, o), 0

    def _load_t(self, o, t):
        """Tonnes of tower t of site o that are loaded on sledges (L3, C3, M4, sea legs): the tower's tonnes minus
        the S17 rubble core, which goes by basket with no loading term (spec 14.7, addendum 8b; fix 7 Nov, Opus
        docking R013)."""
        tn = float(self.towers[o][t][0])
        if self.cz is not None and self.cz.fill_f > 0.0:
            tn -= self.cz.fill_tonnes(o)
        return tn

    def _crew_trip_mh(self, crews, C, L, part, o):
        """Man-hours of a land trip (whole route or relay leg) for `crews` person-trips. v15b: crews x trip, the trip
        including load_unload_h per crew member (half per relay leg). v16 L3 (add4.load_per_tonne): crews x (drag +
        walk) + load_ph_per_t x tonnes of the tower (half per relay leg), independent of crew size and friction."""
        if not self.L3:
            return crews * self.trip(C, L, part)
        tn = self._load_t(o, int(self.tower_idx[o]))
        return crews * self.trip(C, L, part, float(self.tp["drag_speed_ms"]), 0.0) + \
            tn * self.lp * (1.0 if part == "whole" else 0.5)

    def _lay_share(self, i, face):
        """v16 L1: the site's rail-laying cost (rail_lay_mh_per_m x face-0 real route length, paid once per site) in
        equal parts per tower; land faces of rails sites only (sea faces carry their own legs' laying, L4). 0 when off."""
        S = self.S
        if S.tech is None or S.lay_len is None or face.get("sea"):
            return 0.0
        return self.F["rail_lay_mh_per_m"] * float(S.lay_len[i]) / self.tw_n[i]

    def _sea_l4_mh(self, o, face, Ssite, S038, S03p, nblk, c01):
        """v16 L4: man-hours of a sea face: each land leg by its static rule (Static._l4_sea_faces: rails or dry
        ground) with its crews (rails = the site's crews if the site is on rails, else the rails crews of the same
        pieces; dry = S038), drag + walk with the min-haul floor per leg, loading per crew per landing (sea.transfer_h)
        or under L3 load_ph_per_t x tonnes per land leg, rail laying per rails leg (L1: x leg length / towers); boat
        and hoist as S9."""
        F, tp = self.F, self.tp
        t = int(self.tower_idx[o])
        if c01 is None:
            c01 = self.c01[o][t]
        crews_r = Ssite if self.S.tech["rule"][o] == "long" else c01
        fl, v, vb = float(tp["min_haul_flatm"]), float(tp["drag_speed_ms"]), float(tp["return_walk_ms"])
        trf = float(self.cfg["sea"].get("transfer_h", tp["load_unload_h"]))
        mh = 0.0
        for (hf, hm), rk in zip(face["legs"], face["leg_rails"]):
            cr = crews_r if rk else S038
            mh += cr * ((max(hf, fl) / v + max(hm, fl) / vb) / 3600.0 + (0.0 if self.L3 else trf))
            if rk and F["rails_cost_choice"]:
                mh += F["rail_lay_mh_per_m"] * max(hm, fl) / self.tw_n[o]
        if self.L3:
            mh += 2.0 * self._load_t(o, t) * self.lp
        return mh + S03p * face["boat_h"] + nblk * face["hoist_ph"]

    def _sea_variant(self):
        """Sea-face (payload-split) values of the current owner's current tower, or None (nothing to split)."""
        o = self.cur_owner
        ts = self.tower_sea[o]
        return None if ts is None else ts[int(self.tower_idx[o])]

    # ------------------------------------------------------------------ join mode (help_mode: join)
    def _hands_cap(self, i, stage, nblk):
        """Most hands that can work a stage of one tower at once (physics): blocks x useful hands per block.
        Transport: every block's own crew (sum over the tower's blocks = crews at the site's mu); build/lift: only the
        blocks of one course at a time; quarry/dress: hands per block (sc join_hands_per_block, FREE)."""
        hp = self.sc.get("join_hands_per_block", {"quarry": 4, "dress": 2, "build": 6})
        if stage in ("leg1", "transport"):
            o = int(self.tower_idx[i])
            if self.cur_sea and self.tower_sea[i] is not None:    # sea face: the payload-split pieces' crews
                sv = self.tower_sea[i][o]
                return float(sv["tech"][0]) if self.S.tech is not None else float(sv["S03"])
            return float(self.tower_tech[i][o][0]) if self.S.tech is not None else float(self.towers[i][o][1])
        if stage == "build":
            n_courses = int(math.ceil(self.cfg["lit_scenarios"]["geometry"]["tower_height_m"] /
                                      self.cfg["lit_scenarios"]["geometry"]["course_height_m"] - 1e-9))
            return float(hp["build"]) * max(1.0, nblk / n_courses)
        return float(hp[stage]) * max(1, nblk)

    def _join_split(self, i, helper, stage, nblk):
        """Helper share f of the stage's man-hours: the parties work it together, so its duration is
        MH / (B_owner + B_helper_eff) with B_helper_eff = min(B_helper, hands cap - B_owner) >= 0."""
        cap = self._hands_cap(i, stage, nblk)
        bh = float(self.B[helper])
        if self.cz is not None and self.cz.levy_cur == helper:   # v12 S21: a levied community sends levy_share of its party
            bh = self.cz.levy_hands(helper)
        h_eff = max(0.0, min(bh, cap - float(self.B[i])))
        if self.food_cap is not None:                     # S12: the owner feeds every hand on its stage
            h_eff = max(0.0, min(h_eff, float(self.food_cap[i]) - float(self.B[i])))
        return h_eff / (float(self.B[i]) + h_eff) if h_eff > 0 else 0.0

    def _join_task(self, i, helper, stage, mh, loc, up, final, nblk, parts=None):
        """Owner part (owner) + helper part (helper, + its walk), both downstream of `up`; the next task waits for
        both (t_up2). Returns the owner part's id. parts=None: the stage's man-hours mh split by the hands share f
        (relay leg 1); parts=(f, owner mh, helper mh): already priced per party (code_v16_final D6, skill stages)."""
        if parts is None:
            f = self._join_split(i, helper, stage, nblk)
            mo, mhp = mh * (1.0 - f), mh * f
        else:
            f, mo, mhp = parts
        to = self.add_task(i, mo, stage, up, final)
        self.charge(i, i, mo, stage)
        if f > 0:
            walk = self.B[helper] * self.wdist(helper, loc, i if stage == "build" else None) / \
                self.tp["return_walk_ms"] / 3600.0
            th = self.add_task(helper, mhp + walk, stage, up, final)
            self.charge(i, helper, mhp + walk, stage, walk)
            self.join_part[to] = th
        return to

    def _owner_skill(self, i, stage, t_i):
        """Owner's factor on its own skill-stage work: its A3 skill, or under tech rules the larger discount of that
        and S8 within-site learning (1 - s8_rate)^t_i (never both; PM:23)."""
        sk = self.skill(i, stage)
        if self.S.tech is not None and self.s8_rate > 0:
            sk = min(sk, (1.0 - self.s8_rate) ** t_i)
        return sk

    def _perform_join(self, i, helper, stage, loc, up, final, base, extra, t_i, nblk, cur, credit=True):
        """Join mode for a skill stage. code_v16_final D6 (PM:23 "A helper uses its own skill"): each party's share of
        the stage is priced at that party's own factor: the owner's share (1 - f) at _owner_skill (min of A3 skill and
        S8), the helper's share f at the helper's A3 skill (was: the main performer's factor for the whole stage).
        `extra` (setup, cuts, soil) is not skill-discounted and is split by f as before. The learning credit is
        unchanged: the main performer (the party contributing more hands, f > 0.5 = helper) gets it (specialisation
        rule as in handover)."""
        f = self._join_split(i, helper, stage, nblk)
        p = helper if f > 0.5 else i
        if base is not None:
            mo = base * (1.0 - f) * self._owner_skill(i, stage, t_i) + extra * (1.0 - f)
            mhp = base * f * self.skill(helper, stage) + extra * f
        else:
            mo, mhp = extra * (1.0 - f), extra * f
        t = self._join_task(i, helper, stage, mo + mhp, loc, up, final, nblk, parts=(f, mo, mhp))
        if credit and base is not None and stage in SKILL_STAGES and (p == i or self.sc.get("specialisation", False)):
            self.cum[p, SKILL_STAGES.index(stage)] += 1.0
        cur.setdefault("join_share", {})[stage] = f
        return t

    def _no_work_task(self, i, stage, up, final=False):
        """code_v16_final D3: a stage with no work (PM:20 "Dressing: none for 1 tower"; any skill stage whose labour
        before skill is 0 with no extra) is the owner's 0-man-hour task, kept only so the chain order is unchanged. No
        help is asked (no ask counters, no acceptance draw, no trust change, no alliance), no levy, no helper walk, no
        skill credit (SC:169 counts work performed). The Q-learning dimension (e.g. req_dress) is still drawn (the
        strategy draw is unchanged; the choice has no effect on such a tower); the acceptance draws that the old
        zero-work asks took from the asked communities' streams are no longer made, so later draws shift."""
        return self.add_task(i, 0.0, stage, up, final)

    def start_tower(self, i):
        sc, A, S = self.sc, self.A, self.S
        t_i = int(self.tower_idx[i])
        t_s8 = t_i if (self.n_real is None or t_i < self.n_real[i]) else 0   # S13 extra units: no S8 discount
        mh0 = self.acc["mh_total"][i]
        self.cur_owner = i                                # tech rules: the owner's friction applies to its legs
        self.cur_sea = False                              # set once the face is chosen (sea face + payload split)
        tonnes, S03, S01 = self.towers[i][t_i]
        nblk = self.tower_nblk[i][t_i]
        faces = S.faces[i]
        req = sc.get("requests", False)
        dims = {"quarry_face": list(range(len(faces)))}
        if req and (self.ties is None or sc.get("trust", False)):
            dims.update({"req_quarry": [0, 1], "req_dress": [0, 1], "req_build": [0, 1],
                         "relay": [0.0] + list(A["relay_fractions"])})
        elif req:
            T_ = self.ties
            if len(T_["stone"][i]):
                dims.update({"req_quarry": [0, 1], "req_dress": [0, 1]})
            if len(T_["build"][i]):
                dims["req_build"] = [0, 1]
            if len(T_["move"][i]):
                dims["relay"] = [0.0] + list(A["relay_fractions"])
        if sc.get("tracks", False):
            dims["track"] = [0, 1]
        qd = self.Q[i]["quarry_face"]
        if not qd:                                        # prior: estimated own man-hours per tonne of each face
            pool = sum(self.base_stage.values()) if S.tech is None else sum(self.site_stage[i].values())
            for qi, fc in enumerate(faces):
                m, _ = self.leg_mh(i, fc, fc["a"], fc["b"], S03, S01, "whole", nblk=nblk)
                m += self._lay_share(i, fc)                       # v16 L1: rail laying share (0 when off)
                qd[qi] = -(m + pool + float(sc.get("setup_mh", A["setup_mh"]))) / tonnes
        strat, imit = self.choose(i, dims)
        q = int(strat["quarry_face"])
        face = faces[q]
        sea_x = {"split_mh": 0.0, "xlift": 0.0}
        if face.get("sea") and self.tower_sea[i] is not None:   # S9 payload split applies to this tower (30 Oct)
            self.cur_sea = True
            sea_x = self.tower_sea[i][t_i]
            nblk = sea_x["nblk"]
            if sea_x["S03"] is not None:
                S03, S01 = sea_x["S03"], sea_x["S01"]
        strat["quarry_region"] = face["region"]
        qxy = (face["qx"], face["qy"])
        walk_ms = self.tp["return_walk_ms"]
        cur = {"strategy": strat, "own0": self.acc["mh_own"][i], "tonnes": tonnes, "imit": imit, "helpers": {}}
        self.strategy_log.append((self.season, strat.get("quarry_face"), strat.get("req_quarry", 0),
                                  strat.get("req_dress", 0), strat.get("req_build", 0), strat.get("relay", 0.0),
                                  strat.get("track", 0), int(imit)))
        k_log = len(self.relay_made)
        self.relay_made.append(0)
        if self.soc is not None:                          # v13: who started, imitated source (-1 none), help-tie source
            self.soc["strat"].append((i, self.soc["src"] if imit else -1, self.soc["linked"] if imit else 0))
            self.soc["src"], self.soc["linked"] = -1, 0

        join = sc.get("help_mode") == "join"              # MOST_REALISTIC: helpers add hands, they do not take over

        def perform(stage, want_help, loc, up, final=False, base=None, extra=0.0, credit=True):
            """Create the task; returns task id. base: labour before skill (for skill stages)."""
            if base is not None and base <= 0.0 and extra <= 0.0:   # code_v16_final D3: no work in this stage
                return self._no_work_task(i, stage, up, final)
            helper = -1
            if self.cz is not None and self.cz.levy is not None:   # v12 S21: a seat levies a community of its canton
                helper = self.cz.levy_helper(i)
                if helper >= 0:
                    assert join, "levy needs help_mode join"
                    self.cz.levy_cur = helper
                    g0 = self.acc["mh_given"][helper]
                    t = self._perform_join(i, helper, stage, loc, up, final, base, extra, t_s8, nblk, cur, credit)
                    self.cz.levy_used(i, helper, self.acc["mh_given"][helper] - g0)
                    self.cz.levy_cur = -1
                    cur["helpers"][stage] = helper
                    return t
            if want_help:
                helper = self.request(i, stage, loc, self.candidates(i, stage))
                self.charge_brokers(i, stage)
                cur["helpers"][stage] = helper
            if helper >= 0 and join:
                return self._perform_join(i, helper, stage, loc, up, final, base, extra, t_s8, nblk, cur, credit)
            p = i if helper < 0 else helper
            sk = self.skill(p, stage) if base is not None else 1.0
            if base is not None and S.tech is not None and p == i and self.s8_rate > 0:
                sk = min(sk, (1.0 - self.s8_rate) ** t_s8)   # S8 within-site learning vs A3 skill: the larger discount
            #   (never both: see MOST_REALISTIC_NOTES.md "learning")
            mh = (base * sk if base is not None else 0.0) + extra
            walk = 0.0
            if p != i:
                walk = self.B[p] * self.wdist(p, loc, i if stage == "build" else None) / walk_ms / 3600.0
            t = self.add_task(p, mh + walk, stage, up, final)
            self.charge(i, p, mh + walk, stage, walk)
            if credit and base is not None and stage in SKILL_STAGES and (p == i or sc.get("specialisation", False)):
                self.cum[p, SKILL_STAGES.index(stage)] += 1.0
            return t
        # 1 quarry (+ face setup unless the face is already open for this community)
        opened = self.open_faces.setdefault(face["region"], set())
        if i in opened or (sc.get("shared_quarry", False) and any(self.allied(i, o) for o in opened)):
            setup = 0.0
        else:
            setup = float(sc.get("setup_mh", A["setup_mh"]))
        split_mh = 0.0 if S.tech is None else self.tower_tech[i][t_i][3]     # tech rules: cuts of heavy blocks
        if self.cur_sea:                                  # sea face: cuts of the payload split (incl. any crew cuts)
            split_mh = sea_x["split_mh"]
        found = 0.0
        if self.cz is not None and t_i == 0:              # v12 S15: soil stripping before the first tower
            found = self.cz.found_ph(i)
        tq = perform("quarry", strat.get("req_quarry", 0) == 1, qxy, -1, base=self._stage(i, "quarry"),
                     extra=setup + split_mh + found)
        self.acc["mh_setup"][i] += setup
        self.acc["mh_quarry"][i] -= setup
        if found > 0.0:
            self.acc["mh_found"][i] += found
            self.acc["mh_quarry"][i] -= found
        opened.add(i)                                     # B1: the face is opened for the owner i (who paid the setup)
        # 2 dress (at the quarry, the plan's chain order)
        td = perform("dress", strat.get("req_dress", 0) == 1, qxy, tq, base=self._stage(i, "dress"))
        up = td
        # 3 track along the chosen route (split among the community and its allies within R)
        if strat.get("track", 0) == 1 and face["route"] >= 0:
            new = [c for c in S.mv_cell[face["a"]:face["b"]] if c not in self.track_owner]
            lm = float(S.mv_len[face["a"]:face["b"]][[c not in self.track_owner for c in S.mv_cell[face["a"]:face["b"]]]].sum())
            if new and lm > 0:
                allies = [i] + [int(j) for j in S.nb[i][0] if self.allied(i, int(j)) and not self.defector[int(j)]]
                share = lm * float(sc["track_cost_mh_per_m"]) / len(allies)
                tt = -1
                for j in allies:
                    walk = 0.0 if j == i else self.B[j] * self.wdist(j, qxy) / walk_ms / 3600.0
                    t = self.add_task(j, share + walk, "track", td)
                    self.charge(i, j, share + walk, "track", walk)
                    if j == i:
                        tt = t
                for c in new:
                    self.track_owner[c] = i
                up = tt
        # 4 transport: whole route, or relay leg 1 (a helper from the ordinary candidate list; the v15b "nearer the
        # quarry than the owner" filter is removed, code_v15c / code_v16) + leg 2 (self)
        f = float(strat.get("relay", 0.0))
        a, b = face["a"], face["b"]
        lay = self._lay_share(i, face)                    # v16 L1: rail laying share, booked to the owner's transport
        relay_ok = f > 0 and face["route"] >= 0 and face["C"] >= float(A["relay_min_flatm"]) and f in face["handoff"]
        helper = -1
        if relay_ok:
            # v16 (specified by the authors, 5 Nov 2026): the leg-1 "nearer the quarry than the owner" candidate filter is
            # REMOVED; leg-1 candidates = the ordinary candidate list (as code_v15c_norelayfilter). v15b passed
            # nearer_than=dself. Measured before removal (CHANGES_V16.md).
            helper = self.request(i, "leg1", qxy, self.candidates(i, "leg1", qxy))
            self.charge_brokers(i, "leg1")
            cur["helpers"]["leg1"] = helper
        if helper >= 0 and join:                          # join: helper's hands join the owner on leg 1
            h = a + face["handoff"][f]
            m1, _ = self.leg_mh(i, face, a, h, S03, S01, "leg")
            m2, _ = self.leg_mh(i, face, h, b, S03, S01, "leg")
            m2 += lay
            self.relay_made[k_log] = 1
            t1 = self._join_task(i, helper, "leg1", m1, qxy, up, False, nblk)
            t2 = self.add_task(i, m2, "transport", t1)
            self.charge(i, i, m2, "transport")
            hc = int(S.mv_cell[h]) if h < b else int(S.haul.row[i]) * S.W + int(S.haul.col[i])
            key = (hc % self.S.W, hc // self.S.W)
            self.handoff_use[key] = self.handoff_use.get(key, 0) + 1
            ttr = t2
        elif helper >= 0:
            h = a + face["handoff"][f]
            m1, _ = self.leg_mh(helper, face, a, h, S03, S01, "leg")
            m2, _ = self.leg_mh(i, face, h, b, S03, S01, "leg")
            m2 += lay
            self.relay_made[k_log] = 1
            walk = self.B[helper] * self.wdist(helper, qxy) / walk_ms / 3600.0
            t1 = self.add_task(helper, m1 + walk, "leg1", up)
            self.charge(i, helper, m1 + walk, "leg1", walk)
            t2 = self.add_task(i, m2, "transport", t1)
            self.charge(i, i, m2, "transport")
            # B2: mv_cell holds each move's FROM-cell, so leg 1 ends at the from-cell of move h (the first leg-2 move),
            # or at the site cell when leg 1 is the whole route (S.haul rows are in the same order as i)
            hc = int(S.mv_cell[h]) if h < b else int(S.haul.row[i]) * S.W + int(S.haul.col[i])
            key = (hc % self.S.W, hc // self.S.W)
            self.handoff_use[key] = self.handoff_use.get(key, 0) + 1
            ttr = t2
        else:
            m, _ = self.leg_mh(i, face, a, b, S03, S01, "whole", nblk=nblk)
            m += lay
            ttr = self.add_task(i, m, "transport", up)
            self.charge(i, i, m, "transport")
        if self.cz is not None:                           # v12 S17 fill carrying, S20 lintel (may wait for hands)
            ttr = self.cz.after_transport(i, t_i, face, ttr)
        if self.track_owner and face["route"] >= 0:
            for c in S.mv_cell[a:b]:
                if c in self.track_owner and self.allied(i, self.track_owner[c]):
                    self.track_use[c] = self.track_use.get(c, 0) + 1
        # 5 build and lift (at the site)
        if self.masons and self.m_need[i] and (self.n_real is None or t_i < self.n_real[i]):
            # M2: the upper courses / vault (vault_share of the build stage) wait for a master mason; lower part now,
            # the vault as a second build task once a master has arrived (help asked again, no second skill credit)
            bb = self._stage(i, "build") + sea_x["xlift"]
            v = float(self.masons["vault_share"])
            want_b = strat.get("req_build", 0) == 1
            loc_b = (S.xy[i, 0], S.xy[i, 1])
            tb = perform("build", want_b, loc_b, ttr, final=True, base=(1.0 - v) * bb)
            cur["mphase"] = "lower"
            cur["vault_fn"] = lambda: perform("build", want_b, loc_b, -1, final=True, base=v * bb, credit=False)
        else:
            tb = perform("build", strat.get("req_build", 0) == 1, (S.xy[i, 0], S.xy[i, 1]), ttr, final=True,
                         base=self._stage(i, "build") + sea_x["xlift"])   # xlift: lever/stair lift of the extra sea pieces
        cur["final_task"] = tb
        cur["mh"] = self.acc["mh_total"][i] - mh0             # every charge of this tower is made here (S14 repairs)
        self.current[i] = cur
        self._order_dirty = True

    def _final_day(self, cur):
        """Day the tower's final task finished (-1 if not yet); join mode: the later of the two build parts."""
        if cur.get("mphase") == "wait":                   # M2: waiting for a master mason
            return -1
        t = cur["final_task"]
        d = int(self.t_finish[t])
        t2 = self.join_part.get(t, -1) if self.join_part else -1
        if t2 >= 0:
            d2 = int(self.t_finish[t2])
            return -1 if (d < 0 or d2 < 0) else max(d, d2)
        return d

    def finish_tower(self, i, day):
        cur = self.current[i]
        if self.masons and cur.get("master") is not None:
            self._release_master(i, int(cur["master"]))
        own = self.acc["mh_own"][i] - cur["own0"]
        cpt = own / cur["tonnes"]
        r = -cpt
        alpha = float(self.A["alpha"])
        for dname, v in cur["strategy"].items():
            if dname in DIMS:
                q = self.Q[i][dname]
                q[v] = q.get(v, 0.0) + alpha * (r - q.get(v, 0.0)) if v in q else r
        self.last_strategy[i] = (cur["strategy"], cpt)
        self.tower_idx[i] += 1
        self.current[i] = None
        if self.maint:
            self.tower_mh[i] += cur["mh"]
        if self.tower_idx[i] < len(self.towers[i]) and (self.units is None or self.tower_idx[i] < self.stop_at[i]):
            self.start_tower(i)
        elif self.tower_idx[i] < len(self.towers[i]):     # S10: keep done, additions in a later cohort
            self.pause_day[i] = day
        else:
            self.finish_day[i] = day
            self.finish_season[i] = self.season

    # ------------------------------------------------------------------ season tick
    def season_step(self):
        A, N = self.A, self.N
        self.season += 1
        if self.cz is not None:                            # v12: levy budgets, lintel waits
            self.cz.season_start()
        # new starts this season
        if self.maint:                                     # S14: collapses of finished towers, repaired by the owner
            self._collapses()
        if self.phase_frac and self.units is not None:     # S10 / S11: ordered unit cohorts
            if all(c is None for c in self.current) and self.cur_phase + 1 < len(self.cohorts):
                self.cur_phase += 1
                for (i, t0, t1) in self.cohorts[self.cur_phase]:
                    assert self.tower_idx[i] == t0, "unit order: additions before the keep"
                    if self.start_day[i] < 0:
                        self.n_started += 1
                        self.start_day[i] = self.day
                        self.start_season[i] = self.season
                    if t0 > 0 and self.add_B is not None and self.add_B[i] != self.B[i]:
                        self.B[i] = self.add_B[i]          # S10 variant: the later, smaller party builds the additions
                        self.cap[i] = float(self.B[i]) * self.Hh
                    self.stop_at[i] = t1
                    self.start_tower(i)
        elif self.phase_frac:                              # phased: the next cohort starts once ALL earlier ones are built
            if all(c is None for c in self.current) and self.cur_phase + 1 < len(self.cohorts):
                self.cur_phase += 1
                for i in self.cohorts[self.cur_phase]:          # gid order
                    i = int(i)
                    self.n_started += 1
                    self.start_day[i] = self.day
                    self.start_season[i] = self.season
                    self.start_tower(i)
        else:
            if self.cz is not None and self.cz.demog is not None:   # v12 S22: starts follow population growth
                tgt = self.cz.demog_target(self.season)
            else:
                self.start_acc += float(self.sc.get("start_rate", A["start_rate"])) * N
                tgt = int(self.start_acc + 1e-9)
            while self.n_started < N and self.n_started < tgt:
                i = int(self.start_order[self.n_started])
                self.n_started += 1
                self.start_day[i] = self.day
                self.start_season[i] = self.season
                self.start_tower(i)
        days_left = int(A["season_days"])
        while days_left > 0:
            if getattr(self, "_order_dirty", True):
                self.active_tasks = [t for t in self.active_tasks if self.t_done[t] < self.t_total[t]]
                self.active_tasks.sort(key=lambda t: (self.t_stage[t], t))
                self.order = np.array(self.active_tasks, np.int64)
                self._order_dirty = False
            if self.order.size == 0:
                self.day += days_left
                break
            n = run_days(days_left, self.order, self.t_perf, self.t_total, self.t_done, self.t_up, self.t_final,
                         self.cap, self.capleft, self.t_finish, self.day, self.t_up2)
            self.day += n
            days_left -= n
            fin = [i for i in range(N) if self.current[i] is not None and self._final_day(self.current[i]) >= 0]
            for i in sorted(fin):
                if self.masons and self.current[i].get("mphase") in ("lower", "travel"):
                    self._mason_event(i, self._final_day(self.current[i]))
                else:
                    self.finish_tower(i, self._final_day(self.current[i]))
            if self.masons:
                self._assign_masons()
            self._order_dirty = True
        if self.n_started >= N and all(c is None for c in self.current) and \
                (self.units is None or self.cur_phase + 1 >= len(self.cohorts)):
            self.runner.stop()

    def _collapses(self):
        """S14: each finished tower collapses (in part) with probability p_collapse per season (= year); the owner
        repairs it: repair_frac x the site's mean man-hours per finished tower, one task in the build stage, by the
        owner's own party (no help), competing with its other work. Labour in mh_repair (not in mh_total)."""
        M = self.maint
        n = self.m_rng.binomial(self.tower_idx, float(M["p_collapse"]))
        for i in np.flatnonzero(n):
            i = int(i)
            mh = float(M["repair_frac"]) * self.tower_mh[i] / float(self.tower_idx[i]) * float(n[i])
            self.add_task(i, mh, "build")
            self.acc["mh_repair"][i] += mh
            self.n_collapse[i] += int(n[i])
        if n.any():
            self._order_dirty = True

    def run(self):
        self.runner.execute()
        assert all(c is None for c in self.current), "unfinished towers at max_seasons"

    # ------------------------------------------------------------------ results
    def results(self):
        A = self.acc
        rows = pd.DataFrame({
            "seed": self.seed, "gid": np.arange(self.N), "TWR_N": self.S.haul.TWR_N.to_numpy(),
            **{k: v for k, v in A.items()},
            "builders": self.B, "defector": self.defector.astype(int),
            "start_season": self.start_season, "finish_season": self.finish_season,
            "years": self.finish_season - self.start_season + 1,
            "days": self.finish_day - self.start_day + 1,
            "tonnes": [sum(t[0] for t in tl) for tl in self.towers],
        })
        rows["mh_transport"] = A["mh_transport"]
        if self.phase_frac:                                # phased runs only: cohort and island start/finish day
            rows["phase"] = self.phase
            rows["start_day"] = self.start_day
            rows["finish_day"] = self.finish_day
        if self.units is not None:                         # S10 / S11
            rows["phase_add"] = self.phase_add
            rows["pause_day"] = self.pause_day
            rows["staged"] = self.staged.astype(int)
        if self.add_B is not None:                         # S10 smaller-party variant: keep party and additions party
            rows["builders"] = self.B0
            rows["builders_add"] = self.add_B
        if self.food_cap is not None:                      # S12
            rows["food_cap"] = self.food_cap
            rows["food_P_kg"] = self.food_P
        if self.n_real is not None:                        # S13: stone of the extra units (t)
            rows["tonnes_extra"] = [sum(t[0] for t in tl[int(self.n_real[k]):]) for k, tl in enumerate(self.towers)]
        if self.maint:                                     # S14
            rows["n_collapse"] = self.n_collapse
            rows["tower_mh"] = self.tower_mh
        if self.masons:                                    # M2
            rows["mason_wait_days"] = self.m_wait
            rows["mason_travel_h"] = self.m_travel_h
            rows["n_vault"] = self.m_nvault
            rows["masons_final"] = self.m_n
        if self.wet_site is not None:                      # M3
            rows["wet_haul"] = self.wet_site.astype(int)
        if self.cz is not None:                            # v12 census columns
            rows = self.cz.result_cols(rows)
        if self.walk_info is not None:                     # M4
            rows["walk_pieces"] = self.walk_info[:, 0]
            rows["walk_tonnes"] = self.walk_info[:, 1]
        if self.soc is not None:                           # v13 social counters (appended; only when a switch is on)
            for k in ("n_shunned", "n_shun_given", "n_bad", "n_good", "n_pc_refused", "n_pc_refuse_given", "n_cheat"):
                rows["soc_" + k] = self.soc[k]
            rows["soc_bad_final"] = [int(self.soc["rep"] and bool(self.soc["log"][g]) and not self.soc["log"][g][-1][1])
                                     for g in range(self.N)]    # last logged act an unjustified refusal
            rows["soc_help_ties"] = [len(a) for a in self.soc["adj"]]; _kd_cols(self, rows)   # v13kd: soc_n_kd if on
        pairs = []
        keys = set(self.help_mh) | set(self.trust)
        und = {}
        for (a, b) in keys:
            k = (min(a, b), max(a, b))
            und[k] = 1
        for (a, b) in und:
            pairs.append((self.seed, a, b, self.T(a, b), self.T(b, a), self.help_mh.get((a, b), 0.0),
                          self.help_mh.get((b, a), 0.0), int(self.allied(a, b) and a != b)))
        n_orig = len(pairs)
        extra = sorted({(min(a, b), max(a, b)) for (a, b) in self.asks} - set(und))   # pairs known only from asks
        for (a, b) in extra:
            pairs.append((self.seed, a, b, self.T(a, b), self.T(b, a), 0.0, 0.0, int(self.allied(a, b) and a != b)))
        pairs = pd.DataFrame(pairs, columns=["seed", "a", "b", "trust_ab", "trust_ba", "help_ab", "help_ba", "allied"])
        # per-stage help and task counts per direction (bookkeeping only; appended after the original columns)
        for d, (x, y) in (("ab", ("a", "b")), ("ba", ("b", "a"))):
            for st in PAIR_STAGES:
                v = [self.help_stage.get((p, q, st), (0.0, 0)) for p, q in zip(pairs[x], pairs[y])]
                pairs[f"help_{d}_{st}"] = [t[0] for t in v]
                pairs[f"n_{d}_{st}"] = [int(t[1]) for t in v]
        # asks_ab = a asked b (b decided), refused_ab = b refused a; i.e. they belong to help direction b -> a
        for d, (x, y) in (("ab", ("a", "b")), ("ba", ("b", "a"))):
            v = [self.asks.get((p, q), (0, 0)) for p, q in zip(pairs[x], pairs[y])]
            pairs[f"asks_{d}"] = [int(t[0]) for t in v]; pairs[f"refused_{d}"] = [int(t[1]) for t in v]
        for d, (x, y) in (("ab", ("a", "b")), ("ba", ("b", "a"))):
            for st in ("quarry", "dress", "transport", "build"):
                v = [self.asks_stage.get((p, q, st), (0, 0)) for p, q in zip(pairs[x], pairs[y])]
                pairs[f"asks_{d}_{st}"] = [int(t[0]) for t in v]; pairs[f"refused_{d}_{st}"] = [int(t[1]) for t in v]
        pairs["ask_only"] = [0] * n_orig + [1] * (len(pairs) - n_orig)
        lg = pd.DataFrame(self.strategy_log, columns=["season", "quarry_face", "req_quarry", "req_dress", "req_build",
                                                      "relay", "track", "imitated"])
        lg["seed"] = self.seed
        lg["relay_made"] = np.array(self.relay_made, np.int64)   # v16 S1 (appended column)
        if self.soc is not None:                           # v13: starter, imitated source, source a help tie (0/1)
            ex = np.array(self.soc["strat"], np.int64).reshape(-1, 3)
            lg["gid"], lg["imit_src"], lg["imit_tie"] = ex[:, 0], ex[:, 1], ex[:, 2]
        spec = pd.DataFrame(self.given_stage, columns=["given_" + s for s in STAGES])
        for k, s in enumerate(SKILL_STAGES):
            spec["skill_" + s] = (1.0 + self.cum[:, k]) ** self.expo if self.b != 1.0 else 1.0
            spec["cum_" + s] = self.cum[:, k]
        spec["gid"] = np.arange(self.N); spec["seed"] = self.seed; spec["defector"] = self.defector.astype(int)
        ho = pd.DataFrame([(self.seed, k[0], k[1], v) for k, v in self.handoff_use.items()],
                          columns=["seed", "col", "row", "uses"])
        tr = pd.DataFrame([(self.seed, c % self.S.W, c // self.S.W, self.track_use.get(c, 0), self.track_owner[c])
                           for c in self.track_owner], columns=["seed", "col", "row", "uses", "owner"])
        hl = pd.DataFrame([(k[0], k[1], k[2], v) for k, v in self.help_log.items()],
                          columns=["season", "helper", "owner", "mh"])
        al = pd.DataFrame([(k[0], k[1], v) for k, v in self.allied_season.items()],
                          columns=["a", "b", "season_first_allied"])
        return rows, pairs, lg, spec, ho, tr, hl, al


# ----------------------------------------------------------------------------------- driver
def sensitivity_names(cfg):
    G = cfg["alliance"]["sensitivity"]
    return [f"SENS_R{int(R)}_b{b}_t{t}" for R in G["R_m"] for b in G["b"] for t in G["track_cost_mh_per_m"]]


def sea_name(cfg, name):
    """'X_sea' -> (X, sea.default_kn); 'X_sea4kn' -> (X, 4.0); otherwise (name, None)."""
    import re
    m = re.match(r"^(.*)_sea(?:([0-9.]+)kn)?$", name)
    if not m:
        return name, None
    return m.group(1), float(m.group(2)) if m.group(2) else float(cfg["sea"]["default_kn"])


def scenario(cfg, name):
    """A named scenario from alliance.list or alliance.verify_scenarios, or a sensitivity cell SENS_R.._b.._t.."""
    A = cfg["alliance"]
    base, frac = phasing.split_name(name)
    if frac is not None and name not in A["list"] and name not in A["verify_scenarios"]:
        sc = scenario(cfg, base)                         # NAME_P10 / NAME_P20: phased construction
        sc["phase_frac"] = frac
        sc["name"] = name
        return sc
    base, kn = sea_name(cfg, name)
    if kn is not None:                                            # S9: <scenario>_sea / <scenario>_sea<kn>kn
        sc = scenario(cfg, base)
        sc["sea_kn"] = kn
        sc["name"] = name
        return sc
    sc = dict(A["defaults"])
    if name in A["list"]:
        sc.update(A["list"][name] or {})
    elif name in A["verify_scenarios"]:
        sc.update(A["verify_scenarios"][name] or {})
    elif name in (cfg.get("alliance_extra") or {}) or name in (cfg.get("alliance_gaps") or {}) or \
            name in (cfg.get("alliance_wl") or {}) or name in (cfg.get("alliance_census") or {}):
        # MOST_REALISTIC family (top-level key: not in any hash); 1 Nov S10-S14 in alliance_gaps; 1 Nov (b) alliance_wl;
        # 2 Nov (v12) census scenarios in alliance_census
        sc.update((cfg.get("alliance_extra") or {}).get(name) or (cfg.get("alliance_gaps") or {}).get(name) or
                  (cfg.get("alliance_wl") or {}).get(name) or cfg["alliance_census"][name] or {})
        assert not (sc.get("tech_rules") and sc.get("tracks")), "tech_rules: trackways are not modelled (rails are)"
    elif name.startswith("P_") or name.startswith("PS_"):        # pre-existing networks (pre_networks.py)
        import pre_networks
        spec = pre_networks.scenario_spec(cfg, name)
        sc.update({"requests": True})
        sc.update({k: v for k, v in spec.items() if k not in ("all",) + pre_networks.STAGE_SETS})
        sc["tie_spec"] = {k: v for k, v in spec.items() if k in ("all",) + pre_networks.STAGE_SETS}
    elif name.startswith("SENS_"):
        sc.update(A["list"][A["sensitivity"]["base"]])
        R, b, t = name[5:].split("_")
        sc.update({"R_m": float(R[1:]), "b": float(b[1:]), "track_cost_mh_per_m": float(t[1:])})
    else:
        raise KeyError(name)
    sc["name"] = name
    return sc


def signature(cfg, sc, haul):
    keys = ["hours_per_day", "builders", "stone", "transport"]
    al = {k: v for k, v in cfg["alliance"].items() if k not in ("list", "verify_scenarios", "sensitivity")}
    h = hashlib.sha1(json.dumps({**{k: cfg[k] for k in keys}, "alliance": al}, sort_keys=True, default=str).encode())
    h.update(json.dumps(_sig_sc(sc), sort_keys=True).encode())   # v13g: = sc unless reputation_rule "all" is explicit
    h.update(haul[["UID", "TWR_N", "haul_flatm", "haul_m"]].to_csv(index=False).encode())
    h.update(json.dumps(cfg["lit_scenarios"]["webster_md_per_tower"]).encode())
    h.update(json.dumps(cfg["lit_scenarios"]["lift_share_of_build"]).encode())          # B3: build/lift split
    if (cfg.get("v11") or {}).get("webster_day_fix"):    # v11 (2 Nov 2026): Webster's man-days at source day lengths
        h.update(json.dumps(cfg["v11"], sort_keys=True).encode())
        h.update(V11_VERSION.encode())
    if "tie_spec" in sc:                                 # B3: tie_spec names groups; hash their definitions too
        pn = {k: v for k, v in cfg.get("pre_networks", {}).items() if k not in ("main_grid", "extra", "sensitivity")}
        h.update(json.dumps(pn, sort_keys=True, default=str).encode())
    if sc.get("sea_kn"):                                 # S9: the sea legs and the sea parameters
        import sea as seamod
        h.update(seamod.load_haul(haul.reset_index(drop=True).assign(uid_int=0), cfg, sc["sea_kn"])[seamod.SEA_COLS]
                 .to_csv(index=False).encode())
        h.update(json.dumps(cfg["sea"], sort_keys=True).encode())
    if sc.get("tech_rules"):                             # tech rules: the lit parameters and the per-site rule inputs
        h.update(json.dumps({k: v for k, v in cfg["lit_scenarios"].items() if k != "list"}, sort_keys=True).encode())
        h.update(json.dumps(cfg["lit_scenarios"]["list"][sc["tech_rules"]], sort_keys=True).encode())
        h.update(TECH_VERSION.encode())
    if sc.get("sea_kn"):
        h.update(SEA_VERSION.encode())                   # 30 Oct: payload split on sea faces
    if any(sc.get(k) for k in GAPS_KEYS):                # 1 Nov scenario gaps: their code version and inputs
        h.update(GAPS_VERSION.encode())
        if sc.get("food_cap"):
            h.update(open(os.path.join(cfg["paths"]["cache_dir"], sc["food_cap"]["catchment_file"]), "rb").read())
    po = sc.get("phase_order") or {}
    if any(sc.get(k) for k in WL_KEYS) or po.get("rule") == "emulation":   # 1 Nov (b) wider-literature scenarios
        h.update(WL_VERSION.encode())
        if sc.get("haul_profile"):
            h.update(open(os.path.join(cfg["paths"]["cache_dir"], "alliance", "kbest_wl.npz"), "rb").read())
    if any(sc.get(k) for k in CENSUS_KEYS):              # v12 census scenarios: their code version and inputs
        h.update(CENSUS_VERSION.encode())
        h.update(json.dumps(cfg.get("census_v12") or {}, sort_keys=True, default=str).encode())
        if sc.get("bichrome"):
            h.update(open(os.path.join(cfg["paths"]["cache_dir"], "census", "bichrome_dist.csv"), "rb").read())
    if any(sc.get(k) for k in SOCIAL_KEYS):              # v13 social mechanisms: their code version and cfg['scenarios']
        h.update((SOCIAL_VERSION + _rule_tag(sc)).encode())   # (split_cost_mh acts on every alliance run; was never hashed)
        h.update(json.dumps({k: v for k, v in cfg["scenarios"].items() if k != "list"}, sort_keys=True,
                            default=str).encode())
    nf = near_face_m(cfg)
    if nf is not None:                                   # v14 near-site face rule: hashed only when on
        h.update(NEARFACE_VERSION.encode())
        h.update(json.dumps({"near_site_fixed_face_m": nf}).encode())
    h.update(V16_VERSION.encode())                       # v16: always (S1 parts column, S3 ceiling basis)
    h.update(ADD4_VERSION.encode())                      # code_v16_final: the effective add4 settings, always
    h.update(json.dumps(lit.add4(cfg), sort_keys=True).encode())
    if lit.add4_any(cfg):
        if sc.get("sea_kn") and lit.add4(cfg)["sea_priced_as_charged"]:
            import sea as seamod
            h.update(seamod.load_routes(haul.reset_index(drop=True), cfg, sc["sea_kn"]).to_csv(index=False).encode())
    h.update(CODE_VERSION.encode())                      # stale part files from older code are never reused
    return h.hexdigest()[:12]


def run(a, cfg, haul, names, seeds, out_root=None):
    comm = MPI.COMM_WORLD
    rank, size = comm.Get_rank(), comm.Get_size()
    A = cfg["alliance"]
    statics = {}
    merges = []
    for name in names:
        sc = scenario(cfg, name)
        R = float(sc.get("R_m", A["R_m"]))
        R = R if not (sc.get("sea_kn") or sc.get("tech_rules")) else \
            (R, float(sc["sea_kn"]) if sc.get("sea_kn") else None, sc.get("tech_rules"))   # S9 / tech data live in the Static
        if R not in statics or isinstance(statics[R], _Light):   # keep one full Static in memory (8 GB guard); B4: rebuild a downgraded one
            for k in list(statics):
                if not isinstance(statics[k], _Light):
                    statics[k] = _Light(statics[k])
            import gc
            gc.collect()
            statics[R] = Static(cfg, haul, R) if not isinstance(R, tuple) else Static(cfg, haul, R[0], sea_kn=R[1], tech=R[2])
        S = statics[R]
        run_sc = sc
        if "tie_spec" in sc:
            import pre_networks
            ties, info = pre_networks.build(cfg, haul, sc["tie_spec"])
            run_sc = dict(sc); run_sc["_ties"] = ties
            if rank == 0 and not a.no_merge:            # write the tie files now; keep nothing across scenarios
                import report_alliance
                od = os.path.join(out_root or os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance"), name)
                os.makedirs(od, exist_ok=True)
                report_alliance.write_ties(cfg, haul, info, od, write_shp=not a.no_shapefile)
            del info, ties
        tag = "alliance_" + name
        run_dir = os.path.join(a.parts_dir or os.path.join(cfg["paths"]["cache_dir"], "runs"), tag, signature(cfg, sc, haul))
        if rank == 0:
            os.makedirs(run_dir, exist_ok=True)
            if getattr(S, "info", None):                  # v16: static per-site choices (rails sites, sea faces)
                with open(os.path.join(run_dir, "static_info.json"), "w") as fh:
                    json.dump(S.info, fh, indent=1)
                print(f"[{tag}] v16 static: {json.dumps(S.info)}", flush=True)
            done = set() if a.fresh else {s for s in seeds if os.path.exists(os.path.join(run_dir, f"seed_{s:04d}.done"))}
        else:
            done = None
        done = comm.bcast(done, root=0)
        todo = [s for s in seeds if s not in done]
        nwork = max(1, min(size, int(A["max_ranks"])))
        mine = todo[rank::nwork] if rank < nwork else []
        if rank == 0:
            print(f"[{tag}] {S.N} sites, {len(seeds)} seeds, {len(done)} on disk, {len(todo)} to run on {nwork} ranks "
                  f"(seed-parallel, whole island per rank)", flush=True)
        t0 = time.time()
        for k, seed in enumerate(mine):
            m = AllianceModel(S, run_sc, seed)
            m.run()
            outs = m.results()
            for nm, df in zip(["sites", "pairs", "strategy", "spec", "handoffs", "tracks", "helplog", "allied"], outs):
                fn = os.path.join(run_dir, f"seed_{seed:04d}.{nm}.csv.gz")
                df.to_csv(fn + ".tmp", index=False, compression="gzip")
                os.replace(fn + ".tmp", fn)
            if getattr(m, "pop_info", None):          # population ceiling (MOST_REALISTIC): per-seed check
                with open(os.path.join(run_dir, f"seed_{seed:04d}.population.json"), "w") as fh:
                    json.dump(m.pop_info, fh)
            with open(os.path.join(run_dir, f"seed_{seed:04d}.done"), "w") as fh:
                fh.write(f"{m.season}\n")
            if rank == 0 and (k == 0 or (k + 1) % 5 == 0 or k + 1 == len(mine)):
                print(f"  [{tag}] seed {seed}: {m.season} seasons, {time.time() - t0:.1f} s ({k + 1}/{len(mine)} on rank 0)",
                      flush=True)
            del m
        comm.Barrier()
        if rank == 0:
            print(f"[{tag}] {len(todo)} runs in {time.time() - t0:.1f} s", flush=True)
        merges.append((name, run_dir, R))
        if rank == 0:
            try:
                an = [int(l.split()[1]) for l in open("/sys/fs/cgroup/memory.stat") if l.startswith("anon ")][0]
                rs = int(open("/proc/self/status").read().split("VmRSS:")[1].split()[0]) // 1024
                print(f"  [mem] after {name}: rank-0 RSS {rs} MB; cgroup anon {an // 1048576} MB", flush=True)
            except Exception:
                pass
        run_sc = None
        import gc as _gc
        _gc.collect()
    # merge after all runs: every rank first frees the static data (memory guard for the 8 GB cap)
    light = {R: (S if isinstance(S, _Light) else _Light(S)) for R, S in statics.items()}
    del statics, S
    import gc
    gc.collect()
    comm.Barrier()
    if rank == 0 and not a.no_merge:
        import report_alliance
        for name, run_dir, R in merges:
            out_dir = os.path.join(out_root or os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance"), name)
            report_alliance.write_scenario(cfg, light[R], haul, run_dir, seeds, out_dir, name, write_shp=not a.no_shapefile)
            gc.collect()
    comm.Barrier()


class _Light:
    """The few static fields the merge needs."""

    def __init__(self, S):
        self.xy, self.T, self.H, self.W = S.xy.copy(), S.T.copy(), S.H, S.W


# ------------------------------------------------------------------ v13g reputation rule (2 Nov 2026)
# Appended at the end of the file so that every earlier line keeps its number (the ODD cites them); the three call
# sites are one-line edits: _init_social (soc["gentle"]), _social_gate (which refusals are logged as bad) and
# signature (_sig_sc, _rule_tag). reputation_rule: which refusals count as bad acts in the reputation log.
#   "all" (default) = every unjustified refusal (the rule of the five v13 runs);
#   "gentle" = only a refusal by a defector, or by a community that has received help from the requester
#   (ingratitude: (j, i) in received_from, the same condition as the delta_down trust update and as cheating under
#   partner choice). Other refusals (backlog, distance, capacity, by a community that owes the requester nothing) are
#   not logged, so they cost no standing; helps and justified refusals are treated as before.
# No numeric parameter and no random draws. The key acts only when a SOCIAL_KEYS key is set. The signature changes only
# when the rule is not "all" (REPUTATION_RULE_VERSION and the rule are appended to SOCIAL_VERSION; an explicit "all"
# is dropped from the hashed scenario), so every v13 run keeps its signature.
REPUTATION_RULES = ("all", "gentle")
REPUTATION_RULE_VERSION = "2026-11-02-v13g-gentle-1"


def reputation_rule(sc):
    """The scenario's reputation rule ("all" when the key is absent); any other value is an error."""
    r = sc.get("reputation_rule", "all")
    if r not in REPUTATION_RULES:
        raise ValueError(f"reputation_rule {r!r} not in {REPUTATION_RULES}")
    return r


def _rule_tag(sc):
    """Signature tag of the reputation rule: empty for "all", so the hash of every earlier v13 run is unchanged."""
    r = reputation_rule(sc)
    return ("" if r == "all" else "|" + REPUTATION_RULE_VERSION + ":" + r) + \
        ("|" + TRUSTED_NODIST_VERSION + ":on" if sc.get("trusted_nodist") else "")   # v13kd: empty when off


def _sig_sc(sc):
    """The scenario as hashed: sc itself, minus an explicit default reputation_rule ("all")."""
    return {k: v for k, v in sc.items() if not (k == "reputation_rule" and v == "all")
            and not (k == "trusted_nodist" and not v)}   # v13kd: an explicit false is not hashed


# ------------------------------------------------------------------ v13kd trusted partners: no distance penalty (3 Nov 2026)
# Appended at the end of the file (as v13g) so that every earlier line keeps its number; the call sites are one-line
# edits: SOCIAL_KEYS (line 64), _init_social (line 1027), the acceptance logit in request (line 1201), results (line 1891).
# trusted_nodist: in the asked community's acceptance logit the distance term beta3 * d_km is set to 0 when requester i
# and asked community j form a RECIPROCAL dyad: help has flowed in both directions between them so far in the run
# (help_mh > 0 for (j, i) and for (i, j); help_mh = man-hours charged, the same structure the pairs output and the
# "reciprocated share" measure use). Every other pair keeps beta3 * d. The help radius R (who can be asked) is NOT changed,
# only the acceptance penalty. No numeric parameter, no random draws (the acceptance draw is made as before).
# Form: Kasper & Borgerhoff Mulder 2015, Curr. Anthropol. 56: 709-710 (Fig. 2) and 712: distance does not lower help in
# contingent (reciprocal) dyads; the D x C interaction was not tested statistically (raw-data plot only).
# The key is in SOCIAL_KEYS, so with it on the soc state exists (the other social rules stay off unless set) and the
# signature changes: TRUSTED_NODIST_VERSION is appended to SOCIAL_VERSION via _rule_tag; an explicit false is not hashed.
TRUSTED_NODIST_VERSION = "2026-11-03-v13kd-1"


def _init_kd(m, sc):
    """v13kd state: the switch, and per requester the number of asks in which the distance term was dropped."""
    m.soc["kd"] = bool(sc.get("trusted_nodist"))
    m.soc["n_kd"] = np.zeros(m.N, np.int64)


def _kd_pair(m, i, j):
    """Is (requester i, asked j) a reciprocal dyad (help with mh > 0 both ways so far)? Counts the ask if so."""
    h = m.help_mh
    if h.get((j, i), 0.0) > 0.0 and h.get((i, j), 0.0) > 0.0:
        m.soc["n_kd"][i] += 1
        return True
    return False


def _kd_cols(m, rows):
    """sites column soc_n_kd (asks made by the community with the distance term dropped); only when the switch is on."""
    if m.soc["kd"]:
        rows["soc_n_kd"] = m.soc["n_kd"]
