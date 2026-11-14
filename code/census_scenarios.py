"""v12 (2 Nov 2026) census scenarios: the TESTABLE NOW ideas of census/TESTABLE_PLAN.md as switches on MOST_REALISTIC.

Every switch is a key of the scenario dict (config.yaml -> alliance_census) and is OFF unless set; alliance.py creates
a Census object only when at least one of alliance.CENSUS_KEYS is set, so with every switch off the original code path
runs unchanged (identity test: outputs/identity/IDENTITY.txt). Shared rates live in config.yaml -> census_v12 (hashed
into the run signature only when a census switch is on). Sources, pages and ASSUMPTION labels: code/CENSUS_V12.md.

  lift_graded   S4_graded (D07, F02): lever / stair lift per piece x (piece mass / 450 kg); 'rate' = pieces fill the
                courses in draw order, 'order' = heaviest pieces in the lowest courses
  lintel        S20_lintels (D08): one unsplittable lintel per tower; crew = ceil(mass / pull); own party, or helpers
                asked until the hands suffice, or wait (retry each season); after N seasons the own party moves it
  found         S15_found (F01): soil stripping before the first tower, footprint x depth x (dig + carry)
  fill          S17_fill (M03): share f of the tower mass is a rubble core (no sledge blocks): rubble collection,
                basket carrying, rubble setting; facing blocks only are drawn as sledge pieces
  vault_dress   S2c_vault (D02): dressing of the inner vault courses (share v of the stone) at Boswinkel's rate
  demog         S22_demog (W13): site starts follow N(t) = N exp(r (t - T)), no cohorts (unphased run)
  lift_ramp     S4d_spiral (L03) / S4e_laner_hybrid (L02): earth ramp to h, stair rule above h (tholos towers)
  mortar        S16_mud (M02): mud mortar = share m of the wall volume
  rifascio      S13_rifascio (P06): casing wall around the bastion of a share of complexes >= 4 towers
  bichrome      S23_bichrome (G05): share b of the facing blocks hauled from the nearest contrasting stone class
  levy          S21_levy (W07, W08): complexes levy communities within R (accepted, no trust), D days a year
  mason_regions M2_regional (W10): master-mason pools per region (with `masons`)
  feast_attract S12b_feast_attract (E02): acceptance logit + beta4 x the host's annual surplus (t)
  mudbrick      S19_mudbrick (M04): top h m of every tower in mudbrick
  clearance     S18_clearance (Q05): field-clearance stone budget per catchment used before quarrying
  carts         S24_carts (T06): ox wagons for complexes on routes > 1 km
  size_draw     S25_size (G07): single-tower volume / height by a drawn floor count
  lift_override X_nurtime (R06): one lift technique for every tower (single-site predictions)
"""
import math
import os

import numpy as np
import pandas as pd

import lit


def cone_cum(L, z):
    """Integral of r(z)^2 from 0 to z for the model's truncated-cone tower (lit.cone_course_weights)."""
    g = L["geometry"]
    Hh, R0, R1 = g["tower_height_m"], g["base_diam_m"] / 2, g["top_diam_m"] / 2
    a, b = R0, (R1 - R0) / Hh
    return a * a * z + a * b * z * z + b * b * z ** 3 / 3


class Census:
    def __init__(self, m, S, sc, seed):
        self.m, self.S, self.sc, self.seed = m, S, sc, int(seed)
        cfg = m.cfg
        self.cfg = cfg
        self.P = cfg["census_v12"]
        self.L = cfg["lit_scenarios"]
        N = S.N
        self.N = N
        self.tw = S.haul.TWR_N.to_numpy().astype(np.int64)
        self.uid_int = S.haul.uid_int.to_numpy()
        self.vol_tower = cfg["stone"]["tonnes_per_tower"] * 1000.0 / self.L["webster_density_kg_m3"]   # 565.8 m3
        self.fill_f = float((sc.get("fill") or {}).get("f", 0.0))
        mb = sc.get("mudbrick")
        self.mud_share = self.top_share(float(mb["h_m"])) if mb else 0.0
        self.tpt_full = np.zeros(N)
        self.q_tower = None
        self.mix = None
        self.levy = None
        self.levy_cur = -1
        self.feast = None
        self.demog = None
        self.mreg = None
        self.lintel = sc.get("lintel")
        self.carts = sc.get("carts")
        self.cart_site = np.zeros(N, bool)
        self.lintel_crew = np.zeros(N, np.int64)
        self.wait = {}
        self.clear_t = np.zeros(N)
        self.contrast_m = np.full(N, np.nan)
        self.brick_m3 = np.zeros(N)
        self._mp = None
        if sc.get("clearance") or sc.get("bichrome"):
            self.mix = [None] * N
        if sc.get("clearance"):
            self.q_tower = [None] * N
            self.clear_budget = self._clearance_budget(sc["clearance"])
        if sc.get("bichrome"):
            self._bichrome_init()
        if sc.get("levy"):
            self._levy_init(sc["levy"])
        if sc.get("feast_attract"):
            self.feast = self._feast_init(sc["feast_attract"])
        if sc.get("demog"):
            dm = sc["demog"]
            assert not m.phase_frac, "demog replaces the cohorts: run it without a _P suffix"
            self.demog = (float(dm["r"]), int(dm["span_seasons"]))

    # ------------------------------------------------------------------ geometry helpers
    def top_share(self, h):
        """Share of a tower's stone in its top h metres (truncated cone)."""
        Hh = self.L["geometry"]["tower_height_m"]
        return (cone_cum(self.L, Hh) - cone_cum(self.L, max(0.0, Hh - h))) / cone_cum(self.L, Hh)

    def keep_share(self):
        """Share of the tower stone drawn as sledge blocks (S17 rubble core and S19 mudbrick are not)."""
        return (1.0 - self.fill_f) * (1.0 - self.mud_share)

    def fill_tonnes(self, i):
        return self.fill_f * self.tpt_full[i] / 1000.0

    def size_factors(self):
        """S25: single towers get a floor count 1/2/3 with the given shares (own stream [seed, uid, 2501]) and
        volume / height factors per floor count (ASSUMPTION); complexes keep 1.0."""
        z = self.sc["size_draw"]
        p = np.asarray(z["floor_shares"], float)
        vf, hf = np.ones(self.N), np.ones(self.N)
        self.floors = np.zeros(self.N, np.int64)
        for i in np.flatnonzero(self.tw == 1):
            k = int(np.random.default_rng([self.seed, int(self.uid_int[i]), 2501]).choice(len(p), p=p / p.sum()))
            vf[i], hf[i] = float(z["volume"][k]), float(z["height"][k])
            self.floors[i] = k + 1
        return vf, hf

    # ------------------------------------------------------------------ per-site stages (sum over the site's towers)
    def site_stages(self, i, st, d, tw, mp, tp_, npc, pull_i, pull38):
        sc, L, P, cfg = self.sc, self.L, self.P, self.cfg
        st = dict(st)
        self._mp, self._tp = mp, tp_
        stone = self.S.tech["stone"][i]
        hard = L["hardness"].get(stone, 1.0) if d.get("density") else 1.0
        vol = self.vol_tower * tw
        g = L["geometry"]
        ch = g["course_height_m"]
        w = lit.cone_course_weights(L)
        nc = w.size
        lg = sc.get("lift_graded")
        if lg and d["lift"] in ("lever", "stair"):           # S4_graded: per piece x mass / 450 kg
            cw = np.cumsum(w)
            ref = float(P["lift_ref_kg"])
            lift = 0.0
            for t in range(tw):
                mt = mp[tp_ == t]
                if lg["mode"] == "order":                     # heaviest pieces in the lowest courses
                    mt = np.sort(mt)[::-1]
                frac = (np.cumsum(mt) - mt) / mt.sum()        # mass share laid before each piece
                crs = np.minimum(nc - 1, np.searchsorted(cw, frac, side="right"))
                if d["lift"] == "lever":
                    lift += float(np.sum(mt / ref * crs)) * L["lever_ph_per_block_course"]
                else:
                    lift += float(np.sum(mt[crs >= 1] / ref)) * L["lever_ph_per_block_course"] * (L["stair_lever_last_m"] / ch)
            st["lift"] = lift
        lr = sc.get("lift_ramp")
        if lr and d["lift"] == "stair":                      # S4d / S4e: earth ramp to h, stair rule above
            r = L["ramp"]
            h = float(lr["h_m"])
            rho = r["earth_density_kg_m3"]
            per_m3 = (r["dig_ph_m3"] + rho / r["compact_kg_per_ph"] + rho / r["carry_load_kg"] * r["carry_dist_m"] *
                      r["carry_h_per_m"]) * r["build_remove_factor"]
            if lr["kind"] == "spiral":                       # leaning on the tower, width w0 -> w1, slope s
                s_, w0, w1 = float(lr["slope"]), float(lr["width0_m"]), float(lr["width1_m"])
                Lr = h / s_
                V = s_ * Lr * Lr * (w0 / 2.0 + (w1 - w0) / 3.0)
            else:                                            # straight wedge (S4b geometry) to h
                s_, W = float(lr["slope"]), float(lr["width_m"])
                V = 0.5 * (h / s_) * h * W
            above = np.arange(nc) * ch >= h - 1e-9            # courses whose bed is at or above the ramp top
            stair = mp.size * float(w[above].sum()) * L["lever_ph_per_block_course"] * (L["stair_lever_last_m"] / ch)
            st["lift"] = V * per_m3 * tw + stair
            self.ramp_m3 = V
        vd = sc.get("vault_dress")
        if vd:                                               # S2c: inner vault courses dressed at Boswinkel's rate
            x = float(vd["v"]) * vol * float(P["vault_dress_ph_m3"]) * hard
            st["dress"] = x if d["dress"] == "none" else max(st["dress"], x)
        mo = sc.get("mortar")
        if mo:                                               # S16: mud mortar, share m of the wall volume
            st["build"] += float(mo["m"]) * vol * float(P["mortar_ph_m3"])
        if self.fill_f > 0.0:                                # S17: rubble core f of the mass
            f = self.fill_f
            st["quarry"] = (1.0 - f) * st["quarry"] + f * vol * float(P["rubble_ph_m3"])
            if d["dress"] == "fine" and tw >= L["fine_min_towers"]:
                web = L["webster_md_per_tower"]["dress"] * lit.md_hours(cfg, "dress") * tw * hard
                st["dress"] = web * (1.0 - f) + (st["dress"] - web)
            else:
                st["dress"] *= (1.0 - f)
            st["build"] = (1.0 - f) * st["build"] + f * vol * float(P["rubble_set_ph_m3"])
        if self.mud_share > 0.0:                             # S19: top of the tower in mudbrick
            sb = self.mud_share
            st["quarry"] *= (1.0 - sb)
            st["dress"] *= (1.0 - sb)
            self.brick_m3[i] = vol * sb
            st["build"] += vol * sb * float(P["mudbrick_ph_m3"])   # walling of the same volume stays in build
        return st

    # ------------------------------------------------------------------ per-tower haul mixes, lintels, carts
    def site_towers(self, i, d, tw, pull_i, pull38):
        m, S, sc, P = self.m, self.S, self.sc, self.P
        mp, tp_ = self._mp, self._tp
        f0 = S.faces[i][0]
        if self.lintel:
            self.lintel_crew[i] = int(math.ceil(float(self.lintel["kg"]) / pull_i))
        if self.carts:
            self.cart_site[i] = (self.tw[i] >= int(self.carts["min_towers"])) and S.tech["rule"][i] == "long"
        mix = None
        if sc.get("clearance"):                              # S18: clearance stone first (scree rate, min_haul_flatm haul)
            rem = float(self.clear_budget[i])
            qt, mix = [], []
            L3 = bool(getattr(m, "L3", False))               # v16 L3 on the clearance haul too (fix 6 Nov, docking F7)
            tmin = m.trip(0.0, 0.0, "whole", float(m.tp["drag_speed_ms"]), 0.0) if L3 else m.trip(0.0, 0.0, "whole")
            for t in range(tw):
                tn = float(m.towers[i][t][0])
                s_t = 0.0 if tn <= 0 else min(1.0, max(0.0, rem / tn))
                rem -= s_t * tn
                self.clear_t[i] += s_t * tn
                q0 = m.site_stage[i]["quarry"]
                qt.append(q0 * (1.0 - s_t) + s_t * self.vol_tower * float(self.L["quarry_ph_m3"]["scree"]))
                mix.append((1.0 - s_t, s_t * float(m.tower_tech[i][t][1]) * tmin + (s_t * tn * m.lp if L3 else 0.0)))
            self.q_tower[i] = qt
        if sc.get("bichrome"):                               # S23: share b of the facing blocks from the contrast stone
            b = float(sc["bichrome"]["b"])
            stone = S.tech["stone"][i]
            tgt = P["bichrome_pairs"].get(stone)
            mix = mix or [(1.0, 0.0)] * tw
            if tgt is not None:
                dc = float(self.bdist[tgt][i])
                if np.isfinite(dc):
                    g = self.L["geometry"]
                    R0, R1, Hh = g["base_diam_m"] / 2, g["top_diam_m"] / 2, g["tower_height_m"]
                    area = math.pi * (R0 + R1) * math.sqrt(Hh ** 2 + (R0 - R1) ** 2)
                    phi = min(1.0, area * self.L["facing_thickness_m"] / self.vol_tower)
                    share = b * phi
                    Lc = max(float(m.tp["min_haul_flatm"]), dc * float(P["bichrome_detour"]))
                    ratio = min(3.0, max(1.0, f0["C"] / f0["L"])) if f0["L"] > 0 else 1.0
                    rails = Lc > float(self.L["list"]["REALISTIC"]["mixed"]["long_min_haul_m"])
                    pull_c = float(self.L["f_person_kgf"]) / (0.1 if rails else 0.38)
                    L3 = bool(getattr(m, "L3", False))       # v16 L3 on the contrast haul too (fix 6 Nov, docking F5)
                    trip = m.trip(Lc * ratio, Lc, "whole", float(m.tp["drag_speed_ms"]), 0.0) if L3 else \
                        m.trip(Lc * ratio, Lc, "whole")
                    out = []
                    for t in range(tw):
                        crews = float(np.ceil(mp[tp_ == t] / pull_c).sum())
                        sh, ex = mix[t]
                        ld = share * float(m.towers[i][t][0]) * m.lp if L3 else 0.0
                        out.append((sh - share, ex + share * crews * trip + ld))
                    mix = out
                    self.contrast_m[i] = Lc
        if mix is not None:
            self.mix[i] = mix

    def leg_mh(self, i, face, a, b, S03, part, nblk):
        m = self.m
        o = m.cur_owner
        t = int(m.tower_idx[o])
        if self.carts and self.cart_site[o]:                 # S24: ox wagons (Boswinkel 2021 costings)
            k = self.carts
            tn = float(m.towers[o][t][0])
            if face["route"] < 0 or a == b:
                Ll = face["L"] if part == "whole" else 0.0
            else:
                Ll = face["L"] if (part == "whole" and a == face["a"] and b == face["b"]) else float(m.S.mv_len[a:b].sum())
            if part == "whole":
                Ll = max(Ll, float(m.tp["min_haul_flatm"]))
            trips = math.ceil(tn / float(k["payload_t"]))
            mh = trips * float(k["men_per_wagon"]) * (Ll / float(k["loaded_ms"]) + Ll / float(k["empty_ms"])) / 3600.0 \
                + tn * float(k["load_ph_per_t"]) * (1.0 if part == "whole" else 0.5)
            return mh, 0
        mh, _ = m._leg_mh_tech0(i, face, a, b, S03, part, nblk)
        mx = self.mix[o] if self.mix is not None else None
        if mx is not None:
            sh, ex = mx[t]
            mh = mh * sh + (ex if (part == "whole" or b == face["b"]) else 0.0)
        return mh, 0

    # ------------------------------------------------------------------ S15, S17, S20 tasks at tower start
    def found_ph(self, i):
        fd = self.sc.get("found")
        if not fd:
            return 0.0
        return float(self.P["footprint_m2"]) * float(self.tw[i]) * float(fd["depth_m"]) * float(self.P["soil_ph_m3"])

    def init_acc(self):
        A, N = self.m.acc, self.N
        if self.sc.get("found"):
            A["mh_found"] = np.zeros(N)
        if self.fill_f > 0.0:
            A["mh_fillcarry"] = np.zeros(N)
        if self.lintel:
            A["mh_lintel"] = np.zeros(N)
        if self.levy is not None:
            A["mh_levy_given"] = np.zeros(N)
            A["mh_levy_received"] = np.zeros(N)

    def init_performers(self, H):
        m = self.m
        if self.lintel:                                      # one performer with no capacity: a waiting lintel
            m.cap = np.concatenate([m.cap, [0.0]])
            self.clock = m.cap.size - 1
            self.l_wait = np.zeros(self.N)
            self.l_help = np.zeros(self.N)
            self.l_fall = np.zeros(self.N)
            self.l_own = np.zeros(self.N)

    def _lintel_mh(self, i):
        """Crew x whole trip on the site's baseline land face (the site rule's friction)."""
        m, S = self.m, self.S
        f0 = S.faces[i][0]
        if f0["route"] >= 0 and f0["b"] > f0["a"]:
            mv = S.mv_c01 if S.tech["rule"][i] == "long" else S.mv_c038
            C, L = float(mv[f0["a"]:f0["b"]].sum()), f0["L"]
        else:
            C, L = f0["C"], f0["L"]
        if getattr(m, "L3", False):                          # v16 L3 on the lintel haul too (fix 6 Nov)
            return float(self.lintel_crew[i]) * m.trip(C, L, "whole", float(m.tp["drag_speed_ms"]), 0.0) + \
                float(self.lintel["kg"]) / 1000.0 * m.lp
        return float(self.lintel_crew[i]) * m.trip(C, L, "whole")

    def _lintel_helpers(self, i):
        """Ask neighbours one by one (request(): trust rules as for any help) until the hands suffice."""
        m = self.m
        need = int(self.lintel_crew[i]) - int(m.B[i])
        got, hands = [], 0
        cands = m.candidates(i, "transport")
        for c in cands[: int(self.lintel["max_asks"])]:
            j = m.request(i, "transport", None, [c])
            m._broker = None
            if j >= 0:
                got.append(j)
                hands += int(m.B[j])
                if hands >= need:
                    return got
        return None

    def _lintel_tasks(self, i, helpers, gate=None, up=-1):
        """Owner part (+ helper parts with their walk), proportional to the hands; returns the owner part's id."""
        m = self.m
        mh = self._lintel_mh(i)
        f0 = self.S.faces[i][0]
        tot = float(m.B[i]) + sum(float(m.B[j]) for j in helpers)
        own = mh * float(m.B[i]) / tot if helpers else mh
        if gate is None:
            to = m.add_task(i, own, "transport", up)
        else:                                                # the waiting gate becomes the owner's lintel task
            to = gate
            m.t_perf[to] = i
            m.t_total[to] = own
            m.t_done[to] = 0.0
        m.charge(i, i, own, "transport")
        m.acc["mh_lintel"][i] += own
        for j in helpers:
            walk = m.B[j] * m.wdist(j, (f0["qx"], f0["qy"])) / m.tp["return_walk_ms"] / 3600.0
            x = mh * float(m.B[j]) / tot
            m.add_task(j, x + walk, "transport", m.t_up[to])
            m.charge(i, j, x + walk, "transport", walk)
            m.acc["mh_lintel"][i] += x + walk
        self.l_help[i] += len(helpers)
        m._order_dirty = True
        return to

    def after_transport(self, i, t_i, face, ttr):
        m = self.m
        real = m.n_real is None or t_i < m.n_real[i]
        if self.fill_f > 0.0 and real:                       # S17: rubble core carried in baskets from the quarry
            P = self.P
            f0 = face if not face.get("sea") else self.S.faces[i][0]
            mh = self.fill_tonnes(i) * 1000.0 / float(P["basket_kg"]) * max(f0["L"], float(m.tp["min_haul_flatm"])) * \
                float(self.L["ramp"]["carry_h_per_m"])
            t = m.add_task(i, mh, "transport", ttr)
            m.charge(i, i, mh, "transport")
            m.acc["mh_fillcarry"][i] += mh
            ttr = t
        if self.lintel and real:                             # S20: one unsplittable lintel per tower
            if self.lintel_crew[i] <= m.B[i]:
                self.l_own[i] += 1
                return self._lintel_tasks(i, [], up=ttr)
            h = self._lintel_helpers(i)
            if h is not None:
                return self._lintel_tasks(i, h, up=ttr)
            g = m.add_task(self.clock, 1.0, "transport", ttr)    # never progresses: the build waits for the lintel
            self.wait[i] = {"gate": g, "seasons": 0}
            return g
        return ttr

    # ------------------------------------------------------------------ season start: levy budgets, lintel retries
    def season_start(self):
        if self.levy is not None:
            # v16 S2 (addendum 4): the levied days per community per year may not exceed `days`; the work booked in a
            # season beyond the budget (days x share x party x hours) carries to the next season (v15b: reset to 0)
            lv, H = self.levy, float(self.m.Hh)
            budget = float(lv["days"]) * float(lv["share"]) * self.m.B.astype(np.float64) * H
            self.levy_used_s[:] = np.maximum(0.0, self.levy_used_s - budget)
        if self.lintel and self.wait:
            for i in sorted(self.wait):
                w = self.wait[i]
                w["seasons"] += 1
                h = self._lintel_helpers(i)
                if h is None and w["seasons"] < int(self.lintel["fallback_seasons"]):
                    continue
                if h is None:                                # fallback: the own party moves it (lever-walking)
                    h = []
                    self.l_fall[i] += 1
                self.l_wait[i] += w["seasons"]
                self._lintel_tasks(i, h, gate=w["gate"])
                del self.wait[i]

    # ------------------------------------------------------------------ S22 calendar
    def demog_target(self, season):
        r, T = self.demog
        t = season - 1
        if t >= T:
            return self.N
        return min(self.N, int(math.floor(self.N * math.exp(r * (t - T)) + 1e-9)))

    # ------------------------------------------------------------------ S18 clearance budget
    def _clearance_budget(self, c):
        """Y t/ha x the catchment area (pi R^2) shared by the sites within R of the site (incl. itself)."""
        from scipy.spatial import cKDTree
        R = float(c["R_m"])
        n = np.array([len(x) for x in cKDTree(self.S.xy).query_ball_point(self.S.xy, r=R)], float)
        ha = math.pi * R * R / 10000.0
        self.clear_n = n
        return float(c["Y_t_ha"]) * ha / n

    # ------------------------------------------------------------------ S23 contrast distances
    def _bichrome_init(self):
        t = pd.read_csv(os.path.join(self.cfg["paths"]["cache_dir"], "census", "bichrome_dist.csv")).set_index("UID")
        t = t.reindex(self.S.haul.UID.to_numpy())
        self.bdist = {"basalt": t["dist_basalt_m"].to_numpy(), "limestone/marble": t["dist_limestone_m"].to_numpy()}

    # ------------------------------------------------------------------ S21 levy
    def _levy_init(self, lv):
        from scipy.spatial import cKDTree
        S = self.S
        self.levy = lv
        seat = self.tw >= int(lv["min_towers"])
        self.seat = seat
        tree = cKDTree(S.xy)
        self.levy_nb = [None] * self.N
        for i in np.flatnonzero(seat):
            nb = np.array([j for j in tree.query_ball_point(S.xy[i], r=float(lv["R_m"])) if j != i and not seat[j]],
                          np.int64)
            if nb.size:
                dd = np.hypot(*(S.xy[nb] - S.xy[i]).T)
                nb = nb[np.lexsort((nb, dd))]
            self.levy_nb[i] = nb
        self.levy_used_s = np.zeros(self.N)

    def levy_helper(self, i):
        if not self.seat[i] or self.levy_nb[i] is None:
            return -1
        m, lv = self.m, self.levy
        H = float(m.Hh)
        for j in self.levy_nb[i]:
            j = int(j)
            if m.defector[j] or (m.help_only_started and not m.help_ok[j]):   # help_only_if_started
                continue
            if self.levy_used_s[j] < float(lv["days"]) * float(lv["share"]) * float(m.B[j]) * H:
                return j
        return -1

    def levy_hands(self, j):
        return float(self.levy["share"]) * float(self.m.B[j])

    def levy_used(self, i, j, mh):
        self.levy_used_s[j] += mh
        self.m.acc["mh_levy_given"][j] += mh
        self.m.acc["mh_levy_received"][i] += mh

    # ------------------------------------------------------------------ S12b feast attraction
    def _feast_init(self, fa):
        fc = fa
        t = pd.read_csv(os.path.join(self.cfg["paths"]["cache_dir"], fc["catchment_file"])).set_index("UID")
        t = t.reindex(self.S.haul.UID.to_numpy())
        assert t.notna().all().all(), "feast_attract: a site is missing from the catchment file"
        cls = [c[len("ha_"):] for c in t.columns if c.startswith("ha_")]
        P = np.zeros(self.N)
        for c in cls:
            ha = t["ha_" + c].to_numpy()
            P += ha * float(fc["arable_share"][c]) * float(fc["cropped_share"]) * float(fc["net_yield_kg_ha"])
            if c != "water":
                P += ha * (1.0 - float(fc["arable_share"][c])) * float(fc["pasture_kg_ha"])
        self.surplus_t = float(fc["surplus_share"]) * P / 1000.0
        return float(fa["beta4"]) * self.surplus_t

    # ------------------------------------------------------------------ M2_regional
    def init_masons_regional(self, tw, need, H):
        m, S, sc = self.m, self.S, self.sc
        M = sc["masons"]
        kind = sc["mason_regions"]
        cache = getattr(S, "_cz_regions", None)
        if cache is None:
            cache = S._cz_regions = {}
        if kind not in cache:
            if kind == "tribes":
                import pre_networks
                cache[kind] = np.asarray(pre_networks.groups(self.cfg, S.haul, "G133_tribe"), np.int64)
            elif kind == "regions8":
                from scipy.cluster.vq import kmeans2
                _, lab = kmeans2(S.xy / 1000.0, 8, seed=int(self.cfg["pre_networks"]["generator_seed"]), minit="++",
                                 iter=30)
                cache[kind] = np.asarray(lab, np.int64)
            else:
                raise KeyError(kind)
        reg = cache[kind]
        self.site_reg = reg
        regs = np.unique(reg)
        nneed = float(need.sum())
        slot_reg, active = [], []
        for r in regs:
            nr = need & (reg == r)
            if not nr.any():
                continue
            p0 = max(1, int(round(float(M["pool0"]) * float(nr.sum()) / nneed)))
            mx = p0 + int(tw[nr].sum()) // int(M["per_new"]) + 1
            slot_reg += [int(r)] * mx
            active += [True] * p0 + [False] * (mx - p0)
        self.mreg = np.array(slot_reg, np.int64)
        self.m_active = np.array(active, bool)
        self.vault_r = {}
        m.m_max = int(self.mreg.size)
        m.cap = np.concatenate([m.cap[:S.N], np.full(m.m_max, H)])
        m.m_n = int(self.m_active.sum())
        m.m_busy = np.zeros(m.m_max, bool)
        m.m_loc = np.full((m.m_max, 2), np.nan)
        self.n_regions = int(len(set(slot_reg)))

    def assign_masons_regional(self):
        m = self.m
        keep = []
        for i in m.m_queue:
            free = np.flatnonzero(self.m_active & ~m.m_busy & (self.mreg == self.site_reg[i]))
            if free.size == 0:
                keep.append(i)
                continue
            cur = m.current[i]
            xy = m.S.xy[i]
            lc = m.m_loc[free]
            d = np.where(np.isnan(lc[:, 0]), 0.0, np.hypot(lc[:, 0] - xy[0], lc[:, 1] - xy[1]))
            j = int(np.argmin(d))
            k, dist = int(free[j]), float(d[j])
            m.m_busy[k] = True
            cur["master"] = k
            m.m_wait[i] += max(0, m.day - 1 - int(cur["qday"]))
            hrs = dist / float(m.tp["return_walk_ms"]) / 3600.0
            if hrs > 0:
                cur["final_task"] = m.add_task(m.N + k, hrs, "build", -1, True)
                cur["mphase"] = "travel"
                m.m_travel_h[i] += hrs
            else:
                cur["final_task"] = cur["vault_fn"]()
                cur["mphase"] = "vault"
            m._order_dirty = True
        m.m_queue = keep

    def release_master_regional(self, i, k):
        m = self.m
        m.m_busy[k] = False
        m.m_loc[k] = m.S.xy[i]
        m.m_vaults += 1
        m.m_nvault[i] += 1
        r = int(self.mreg[k])
        self.vault_r[r] = self.vault_r.get(r, 0) + 1
        if self.vault_r[r] % int(m.masons["per_new"]) == 0:
            idle = np.flatnonzero((self.mreg == r) & ~self.m_active)
            if idle.size:
                n = int(idle[0])
                self.m_active[n] = True
                m.m_loc[n] = m.S.xy[i]
                m.m_n += 1

    # ------------------------------------------------------------------ S13_rifascio
    def rifascio_units(self, i, tw):
        rf = self.sc["rifascio"]
        if tw < int(rf["min_towers"]):
            return []
        if np.random.default_rng([self.seed, int(self.uid_int[i]), 1306]).random() >= float(rf["share"]):
            return []
        return [("rifascio", float(rf["perimeter_m"]) * float(rf["height_m"]) * float(rf["thickness_m"]) *
                 float(rf["fill"]), float(rf["height_m"]))]

    # ------------------------------------------------------------------ results
    def result_cols(self, rows):
        m = self.m
        if not m.phase_frac:
            rows["start_day"] = m.start_day
            rows["finish_day"] = m.finish_day
        if self.lintel:
            rows["lintel_crew"] = self.lintel_crew
            rows["lintel_wait_seasons"] = self.l_wait
            rows["lintel_helpers"] = self.l_help
            rows["lintel_fallback"] = self.l_fall
            rows["lintel_own"] = self.l_own
        if self.sc.get("clearance"):
            rows["clear_tonnes"] = self.clear_t
        if self.sc.get("bichrome"):
            rows["contrast_haul_m"] = self.contrast_m
        if self.carts:
            rows["cart_site"] = self.cart_site.astype(int)
        if self.mud_share > 0.0:
            rows["brick_m3"] = self.brick_m3
        if self.fill_f > 0.0:
            rows["fill_tonnes"] = self.fill_f * self.tpt_full / 1000.0 * self.tw
        if self.sc.get("size_draw"):
            rows["floors"] = self.floors
            rows["vol_f"] = m.vol_f
        if self.sc.get("feast_attract"):
            rows["surplus_t"] = self.surplus_t
        return rows
