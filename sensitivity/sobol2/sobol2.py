#!/usr/bin/env python3
"""Sobol sensitivity run 2 (10 Nov 2026; approved by the authors 9 Nov) on the v17 headline
MOST_REALISTIC_AUDITED_LIT_P10 (lift undiscounted, SP-22).

Model code: full_audited/code_variant = copy of code_v17 (CODE_VERSION 2026-11-09-v17) plus ONE config flag,
sobol.lift_learning (default False = code_v17 exactly; True = v16_final lift discount); proofs in checks/.
Config: full_audited/v16_final/configs/config_full_audited.yaml, read-only; every factor value is applied to an
in-memory deep copy (no config or code file is written). Harness = the Morris v16f harness
(the Morris screen's harness, not published: same factor keys, ranges, apply rules, run and outputs), with:
  - 26 factors: the 24 Morris "Candidates for Sobol run 2" (same ranges as its factors.csv), R_m (A1; range of Sobol
    run 1: 5-15 km, scenario R_m -> Static neighbour radius) and lift_learning (2 levels: undiscounted = v17 headline,
    level 0; discounted by learning / skill = v16_final, level 1).
  - FIXED at headline values (not touched): the 8 Morris drop candidates (relay_fractions, delta_up, setup_mh, alpha,
    relay_min_flatm, block_min_kg, transfer_h, delta_down) and A5 alliance_threshold.
  - Design: Saltelli, SALib 1.6.0 sobol.sample(N=512, calc_second_order=False, scramble=True, seed 20261110):
    N (k + 2) = 512 x 28 = 14,336 evaluations; rows in SALib order (per base row j: A, AB_1..AB_k, B).
  - Seeds per evaluation: 1, 2, 3 (common random numbers); the evaluation's output = the mean over the 3 seeds.
  - Outputs (as Morris / Sobol run 1): island years = (max finish_day + 1) / season_days (the run's own),
    island man-hours = sum mh_total, transport share = sum mh_transport / sum mh_total.
  - Level mapping of the uniform sample u in [0, 1): unif lo + u (hi - lo); binary: u < 0.5 -> level 0 (headline),
    else level 1 (threshold at 0.5, SALib practice for discrete factors: equal probability); int: equal-probability
    bins, lo + floor(u (hi - lo + 1)) (5-15: 11 levels of 1/11 each; 1-5: 5 levels of 1/5). (Morris used round();
    with uniform sampling that would give the end levels half weight, so the Sobol uses bins.)

  python sobol2.py design            -> factors.csv, problem.json, design.csv (refuses to overwrite)
  python sobol2.py check             -> dry mapping check (no simulation)
  python sobol2.py ids               -> pending eval ids (no evals/NN/eval_NNNNN.ok), one per line
  python sobol2.py eval --id N       -> one design row x seeds 1-3 -> evals/NN/eval_NNNNN.csv + .ok
  python sobol2.py eval --id headline [--seeds 1,2,3]  -> all factors at headline (= code_v17 headline)
  analyse.py                             -> S1, ST (+ 95% CI), N=256 vs 512 convergence, SOBOL2_RESULTS.md
"""
import argparse
import copy
import csv
import json
import math
import os
import sys
import time
import types

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FA = "@RUN_DIR@"
CODE = os.path.join(FA, "code_variant")
CFG = os.path.join(FA, "configs/config_full_audited.yaml")
STONES7_CACHE = os.path.join(FA, "outputs/caches/config_full_audited_alt_stones7")
MORRIS = os.path.join(HERE, "morris")   # the Morris screen's factors.csv (published with this harness)
sys.path.insert(0, CODE)
SCEN = "MOST_REALISTIC_AUDITED_LIT_P10"
CODE_VERSION = "2026-11-09-v17"
SEEDS = [1, 2, 3]
N_BASE = 512
SAMPLE_SEED = 20261110
OUTPUTS = ["island_years", "island_mh", "mh_transport_share"]
RES_COLS = ["eval_id", "base_row", "block", "seed", "island_years", "island_mh", "mh_transport_share", "seasons",
            "status", "error", "wall_s", "static_s", "pid"]

# ----------------------------------------------------------------------------------- factors
MORRIS_SOBOL2 = ["season_days", "n_phases", "stone_rule", "hardness_hard", "dress_rule", "help_mode", "max_asks",
                 "long_min_haul_m", "specialisation", "bedrock_everywhere", "beta0", "lift_share_of_build",
                 "split_cost_mh", "p_imit", "beta3", "trust0", "lift_rule", "beta1", "beta2", "stair_lever_last_m",
                 "rho_limestone", "learning_rate", "near_site_fixed_face_m", "min_haul_flatm"]   # MORRIS_RESULTS.md order
FIXED = ["relay_fractions", "delta_up", "setup_mh", "alpha", "relay_min_flatm", "block_min_kg", "transfer_h",
         "delta_down"]                                                                        # + A5 alliance_threshold


def _morris_factors():
    """The 24 survivors from the Morris factors.csv (ranges, levels, keys, justification unchanged)."""
    F = pd.read_csv(os.path.join(MORRIS, "factors.csv"), keep_default_na=False)
    out = {}
    for _, r in F.iterrows():
        d = dict(name=r["name"], row=r["row"], kind=r["kind"], key=r["key"], why=r["why"], src="Morris factors.csv")
        if r["kind"] == "binary":
            d["levels"] = json.loads(r["levels"])
            d["headline"] = d["levels"][0]
        else:
            d["lo"], d["hi"] = float(r["lo"]), float(r["hi"])
            d["headline"] = int(float(r["headline"])) if r["kind"] == "int" else float(r["headline"])
            if r["kind"] == "int":
                d["lo"], d["hi"] = int(d["lo"]), int(d["hi"])
        out[d["name"]] = d
    assert set(MORRIS_SOBOL2) | set(FIXED) == set(out) and not set(MORRIS_SOBOL2) & set(FIXED), "Morris factor list"
    return [out[n] for n in MORRIS_SOBOL2]


FACTORS = _morris_factors() + [
    dict(name="R_m", row="A1", kind="unif", lo=5000.0, hi=15000.0, headline=10000.0,
         key="sc.R_m (alliance.Static neighbour radius for requests, relays, imitation; alliance.R_m 10000 unchanged)",
         why="range of Sobol run 1 (params.csv): 5-15 km = the 3 Nov radius runs R5 / R15; no help-distance source",
         src="Sobol run 1 params.csv"),
    dict(name="lift_learning", row="SP-22", kind="binary", levels=[False, True], headline=False,
         key="cfg.sobol.lift_learning (code variant flag)",
         why="lift undiscounted (v17, SP-22 ruling 9 Nov, headline) vs discounted with the build stage by S8 learning "
             "and A3 skill (v16_final behaviour)", src="authors 9 Nov"),
]
NAMES = [f["name"] for f in FACTORS]
FBY = {f["name"]: f for f in FACTORS}
assert len(FACTORS) == 26 and len(set(NAMES)) == 26


def to_value(f, u):
    u = float(u)
    if f["kind"] == "unif":
        return float(f["lo"] + u * (f["hi"] - f["lo"]))
    if f["kind"] == "int":
        n = int(f["hi"]) - int(f["lo"]) + 1
        return int(f["lo"]) + min(int(math.floor(u * n)), n - 1)
    return f["levels"][0 if u < 0.5 else 1]


def problem():
    return {"num_vars": len(FACTORS), "names": NAMES, "bounds": [[0.0, 1.0]] * len(FACTORS)}


# ----------------------------------------------------------------------------------- base and mapping
_HAUL = {}


def load_haul(cfg):
    import model
    p = os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv")
    if p not in _HAUL:
        _HAUL[p] = model.load_haul(cfg, types.SimpleNamespace(sites=None, first_n=None), p)
    return _HAUL[p]


def load_base():
    import alliance
    import lit
    from nbcommon import load_config
    assert lit.CODE_VERSION == CODE_VERSION, lit.CODE_VERSION
    assert os.path.dirname(os.path.abspath(lit.__file__)) == CODE, lit.__file__
    assert hasattr(lit, "lift_learning"), "code variant flag missing"
    cfg = load_config(CFG)
    assert "add4" not in cfg and "sobol" not in cfg
    sc0 = copy.deepcopy(alliance.scenario(cfg, SCEN))
    assert "R_m" not in sc0
    return cfg, sc0


def apply(cfg0, sc0, values):
    """Deep copies of the headline config / scenario with the factor values set (only the factor keys change).
    Rules = the Morris harness's apply() for the 24 Morris factors; R_m as Sobol run 1; lift_learning -> cfg['sobol']."""
    cfg, sc = copy.deepcopy(cfg0), copy.deepcopy(sc0)
    mixed = cfg["lit_scenarios"]["list"]["REALISTIC"]["mixed"]
    for k, x in values.items():
        f = FBY[k]
        if k == "n_phases":
            sc["phase_frac"] = 1.0 / int(x)
        elif k == "season_days":
            cfg["alliance"]["season_days"] = float(x)
        elif k == "rho_limestone":
            cfg["lit_scenarios"]["density_kg_m3"]["limestone/marble"] = float(x)
        elif k == "hardness_hard":
            cfg["lit_scenarios"]["hardness"]["basalt"] = float(x)
            cfg["lit_scenarios"]["hardness"]["granite"] = float(x)
        elif k == "bedrock_everywhere":
            if x != f["headline"]:
                cfg["add4"] = {"bedrock_everywhere": bool(x)}
        elif k == "dress_rule":
            if x == "webster_all":
                mixed["dress_none_max_towers"] = 0
                mixed["dress_fine_min_towers"] = 99
        elif k == "lift_share_of_build":
            cfg["lit_scenarios"]["lift_share_of_build"] = float(x)
        elif k == "stair_lever_last_m":
            cfg["lit_scenarios"]["stair_lever_last_m"] = float(x)
        elif k == "lift_rule":
            if x == "stair_all":
                mixed["lift_by_type"] = {}
        elif k == "learning_rate":
            cfg["lit_scenarios"]["learning_rate"] = float(x)
        elif k == "min_haul_flatm":
            cfg["transport"]["min_haul_flatm"] = float(x)
        elif k == "long_min_haul_m":
            mixed["long_min_haul_m"] = float(x)
        elif k == "split_cost_mh":
            cfg["scenarios"]["split_cost_mh"] = float(x)
        elif k == "stone_rule":
            if x == "stones7":
                cfg["stone_rule"] = "stones7"
                cfg["paths"]["cache_dir"] = STONES7_CACHE
        elif k == "near_site_fixed_face_m":
            cfg["quarry"]["near_site_fixed_face_m"] = float(x)
        elif k == "max_asks":
            cfg["alliance"][k] = int(x)
        elif k in ("trust0", "beta0", "beta1", "beta2", "beta3", "p_imit"):
            cfg["alliance"][k] = float(x)
        elif k == "help_mode":
            if x == "handover":
                sc.pop("help_mode", None)
                sc.pop("join_hands_per_block", None)
        elif k == "specialisation":
            sc["specialisation"] = bool(x)
        elif k == "R_m":                                 # as Sobol run 1 (scenario R_m -> Static radius); the
            if float(x) != float(cfg["alliance"]["R_m"]):  # headline value leaves the scenario untouched
                sc["R_m"] = float(x)
        elif k == "lift_learning":
            if bool(x):
                cfg["sobol"] = {"lift_learning": True}
        else:
            raise KeyError(k)
    return cfg, sc


# ----------------------------------------------------------------------------------- one run
class Unfinished(Exception):
    pass


def make_static(cfg, sc, haul):
    import alliance
    R = float(sc.get("R_m", cfg["alliance"]["R_m"]))
    return alliance.Static(cfg, haul, R, sea_kn=float(sc["sea_kn"]) if sc.get("sea_kn") else None,
                           tech=sc.get("tech_rules"))


def simulate(cfg, sc, seed, S):
    import alliance
    m = alliance.AllianceModel(S, sc, int(seed))
    try:
        m.run()
    except AssertionError as e:
        if "unfinished towers at max_seasons" not in str(e):
            raise
        n = int(m.season)
        del m
        raise Unfinished(f"unfinished (cap {int(sc.get('max_seasons', cfg['alliance']['max_seasons'])):,} seasons)", n)
    sites, seasons = m.results()[0], int(m.season)
    del m
    return sites, seasons


def outputs(sites, cfg):
    T = float(sites.mh_total.sum())
    return {"island_years": (float(sites.finish_day.max()) + 1.0) / float(cfg["alliance"]["season_days"]),
            "island_mh": T, "mh_transport_share": float(sites.mh_transport.sum()) / T}


# ----------------------------------------------------------------------------------- commands
def cmd_design(a):
    from SALib.sample import sobol
    for fn in ("design.csv", "problem.json", "factors.csv"):
        assert a.force or not os.path.exists(os.path.join(HERE, fn)), f"{fn} exists (refusing to overwrite)"
    k = len(FACTORS)
    U = sobol.sample(problem(), N_BASE, calc_second_order=False, scramble=True, seed=SAMPLE_SEED)
    assert U.shape == (N_BASE * (k + 2), k)
    rows = []
    for e, u in enumerate(U):
        j, c = divmod(e, k + 2)
        block = "A" if c == 0 else ("B" if c == k + 1 else f"AB_{NAMES[c - 1]}")
        r = {"eval_id": e, "base_row": j, "block": block}
        r.update({f"u_{n}": float(u[i]) for i, n in enumerate(NAMES)})
        r.update({n: to_value(FBY[n], u[i]) for i, n in enumerate(NAMES)})
        rows.append(r)
    D = pd.DataFrame(rows)
    # Saltelli structure: AB_i = A with column i from B
    Ua = D[[f"u_{n}" for n in NAMES]].to_numpy()
    for j in range(N_BASE):
        blk = Ua[j * (k + 2):(j + 1) * (k + 2)]
        A, B = blk[0], blk[-1]
        for i in range(k):
            exp = A.copy()
            exp[i] = B[i]
            assert np.array_equal(blk[1 + i], exp), (j, i)
    D.to_csv(os.path.join(HERE, "design.csv"), index=False, float_format="%.17g")
    pd.DataFrame([{k_: (json.dumps(v) if isinstance(v, list) else v) for k_, v in f.items()} for f in FACTORS]).to_csv(
        os.path.join(HERE, "factors.csv"), index=False)
    json.dump({"problem": problem(), "N": N_BASE, "k": k, "calc_second_order": False,
               "sampler": "SALib 1.6.0 sobol.sample (Saltelli), scramble=True", "sample_seed": SAMPLE_SEED,
               "n_evals": len(D), "seeds_per_eval": SEEDS, "scenario": SCEN, "code": CODE, "config": CFG,
               "code_version": CODE_VERSION, "fixed_at_headline": FIXED + ["alliance_threshold (A5)"],
               "level_mapping": {"unif": "lo + u (hi - lo)", "int": "lo + floor(u (hi - lo + 1)) (equal-probability bins)",
                                 "binary": "u < 0.5 -> levels[0] (headline), else levels[1]"}},
              open(os.path.join(HERE, "problem.json"), "w"), indent=1)
    lv = {n: D[n].value_counts().to_dict() for n in NAMES if FBY[n]["kind"] != "unif"}
    print(f"design: k = {k}, N = {N_BASE}, {len(D)} evaluations x {len(SEEDS)} seeds = {len(D) * len(SEEDS)} runs "
          f"-> design.csv, factors.csv, problem.json\nlevel counts: {json.dumps(lv, default=str)}")


def flat(d, pre):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{pre}.{k}"))
    else:
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            d = float(d)
        out[pre] = json.dumps(d, sort_keys=True, default=str)
    return out


def changed(cfg0, sc0, cfg, sc):
    a, b = {**flat(cfg0, "cfg"), **flat(sc0, "sc")}, {**flat(cfg, "cfg"), **flat(sc, "sc")}
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def decode(n, v):
    f = FBY[n]
    if f["kind"] == "int":
        return int(v)
    if f["kind"] == "unif":
        return float(v)
    for lv in f["levels"]:
        if str(lv) == str(v):
            return lv
    raise ValueError((n, v))


def cmd_check(a):
    """Dry: headline values; every factor at both ends changes only its own keys and is read back by the model's own
    functions; all at headline = no change; fixed factors untouched on 200 design rows; base config not mutated."""
    import alliance
    import lit
    import phasing
    sys.path.insert(0, MORRIS)
    cfg0, sc0 = load_base()
    snap = json.dumps([cfg0, sc0], sort_keys=True, default=str)
    m0 = cfg0["lit_scenarios"]["list"]["REALISTIC"]["mixed"]
    hv = {"n_phases": phasing.n_phases(sc0["phase_frac"]), "season_days": cfg0["alliance"]["season_days"],
          "rho_limestone": cfg0["lit_scenarios"]["density_kg_m3"]["limestone/marble"],
          "hardness_hard": cfg0["lit_scenarios"]["hardness"]["basalt"],
          "bedrock_everywhere": lit.add4(cfg0)["bedrock_everywhere"],
          "dress_rule": "by_towers" if (m0["dress_none_max_towers"], m0["dress_fine_min_towers"]) == (1, 3) else "?",
          "lift_share_of_build": cfg0["lit_scenarios"]["lift_share_of_build"],
          "stair_lever_last_m": cfg0["lit_scenarios"]["stair_lever_last_m"],
          "lift_rule": "by_type" if m0["lift_by_type"] == {"Nuraghe a corridoio (protonuraghe)": "lever"} and
          m0["lift_default"] == "stair" else "?",
          "learning_rate": cfg0["lit_scenarios"]["learning_rate"], "min_haul_flatm": cfg0["transport"]["min_haul_flatm"],
          "long_min_haul_m": m0["long_min_haul_m"], "split_cost_mh": cfg0["scenarios"]["split_cost_mh"],
          "stone_rule": cfg0["stone_rule"], "near_site_fixed_face_m": alliance.near_face_m(cfg0),
          "help_mode": sc0.get("help_mode"), "specialisation": sc0.get("specialisation"),
          "R_m": float(sc0.get("R_m", cfg0["alliance"]["R_m"])), "lift_learning": lit.lift_learning(cfg0)}
    for n in ("max_asks", "trust0", "beta0", "beta1", "beta2", "beta3", "p_imit"):
        hv[n] = cfg0["alliance"][n]
    bad = 0
    for f in FACTORS:
        v = hv[f["name"]]
        ok = (v == f["headline"]) and ((f["lo"] <= v <= f["hi"]) if f["kind"] != "binary" else v == f["levels"][0])
        print(f"  {f['row']:5s} {f['name']:24s} headline {v!r:>16} {'OK' if ok else 'MISMATCH'}")
        bad += not ok
    assert not bad, "headline values"
    # the fixed factors keep their headline values (Morris factors.csv)
    F = pd.read_csv(os.path.join(MORRIS, "factors.csv"), keep_default_na=False).set_index("name")
    fx = {"relay_fractions": "/".join(f"{x:g}" for x in cfg0["alliance"]["relay_fractions"]),
          "delta_up": cfg0["alliance"]["delta_up"], "setup_mh": float(sc0.get("setup_mh", cfg0["alliance"]["setup_mh"])),
          "alpha": cfg0["alliance"]["alpha"], "relay_min_flatm": cfg0["alliance"]["relay_min_flatm"],
          "block_min_kg": cfg0["stone"]["block_min_kg"], "transfer_h": cfg0["sea"]["transfer_h"],
          "delta_down": cfg0["alliance"]["delta_down"]}
    for n, v in fx.items():
        assert str(v) == str(F.loc[n, "headline"]) or float(v) == float(F.loc[n, "headline"]), (n, v)
    print(f"  fixed at headline: {fx}; alliance_threshold {cfg0['alliance']['alliance_threshold']}")
    assert changed(cfg0, sc0, *apply(cfg0, sc0, {})) == []
    hl = {f["name"]: f["headline"] for f in FACTORS}
    assert changed(cfg0, sc0, *apply(cfg0, sc0, hl)) == [], changed(cfg0, sc0, *apply(cfg0, sc0, hl))
    print("  all factors at their headline values: no key changes")
    for f in FACTORS:
        ch_all = set()
        for u in (0.0, 0.4999, 0.5, 0.999999):
            x = to_value(f, u)
            cfg, sc = apply(cfg0, sc0, {f["name"]: x})
            ch = changed(cfg0, sc0, cfg, sc)
            ch_all.update(ch)
            n = f["name"]
            if n == "n_phases":
                assert phasing.n_phases(sc["phase_frac"]) == x
            elif n == "bedrock_everywhere":
                assert lit.add4(cfg)["bedrock_everywhere"] == x
            elif n == "dress_rule":
                m = cfg["lit_scenarios"]["list"]["REALISTIC"]["mixed"]
                r = [lit.resolve_site(cfg, {"mixed": m}, {"TWR_N": t, "on_outcrop": True, "lit_haul_rule": "short",
                                                          "lit_type": ""})["dress"] for t in (1, 2, 3, 5)]
                assert r == (["none", "webster", "fine", "fine"] if x == "by_towers" else ["webster"] * 4), r
            elif n == "lift_rule":
                m = cfg["lit_scenarios"]["list"]["REALISTIC"]["mixed"]
                r = lit.resolve_site(cfg, {"mixed": m}, {"TWR_N": 1, "on_outcrop": True, "lit_haul_rule": "short",
                                                         "lit_type": "Nuraghe a corridoio (protonuraghe)"})["lift"]
                assert r == ("lever" if x == "by_type" else "stair"), r
            elif n == "near_site_fixed_face_m":
                assert alliance.near_face_m(cfg) == x
            elif n == "min_haul_flatm":
                import sea
                assert sea.params(cfg)["min_haul"] == x
            elif n == "help_mode":
                assert (sc.get("help_mode") == "join") == (x == "join")
            elif n == "R_m":
                assert float(sc.get("R_m", cfg["alliance"]["R_m"])) == x and cfg["alliance"]["R_m"] == cfg0["alliance"]["R_m"]
            elif n == "lift_learning":
                assert lit.lift_learning(cfg) is x
            elif n == "stone_rule" and x == "stones7":
                for fn in ("sites_haul.csv", "alliance/kbest.npz", "sea/sites_haul_sea2kn.csv"):
                    assert os.path.exists(os.path.join(cfg["paths"]["cache_dir"], fn)), fn
        assert ch_all, f"{f['name']} changes nothing"
        print(f"  {f['name']:24s} levels/ends {[to_value(f, u) for u in (0.0, 0.4999, 0.5, 0.999999)]} -> {sorted(ch_all)}")
    # int bins: equal probability
    for n in ("n_phases", "max_asks"):
        f = FBY[n]
        vals = [to_value(f, (i + 0.5) / 10000) for i in range(10000)]
        cnt = pd.Series(vals).value_counts().sort_index()
        assert list(cnt.index) == list(range(f["lo"], f["hi"] + 1)) and cnt.max() - cnt.min() <= 1, cnt
    print("  int factors: equal-probability bins OK")
    if os.path.exists(os.path.join(HERE, "design.csv")):
        D = pd.read_csv(os.path.join(HERE, "design.csv"), float_precision="round_trip")
        allowed = set()
        for f in FACTORS:
            for u in (0.0, 0.999999):
                allowed.update(changed(cfg0, sc0, *apply(cfg0, sc0, {f["name"]: to_value(f, u)})))
        for _, r in D.sample(200, random_state=1).iterrows():
            vals = {n: decode(n, r[n]) for n in NAMES}
            for n in NAMES:
                assert to_value(FBY[n], r[f"u_{n}"]) == vals[n], (n, r[f"u_{n}"], vals[n])
            ch = set(changed(cfg0, sc0, *apply(cfg0, sc0, vals)))
            assert ch <= allowed, ch - allowed
        print(f"  200 design rows: values = mapping of u; only factor keys change ({len(allowed)} keys)")
    assert json.dumps([cfg0, sc0], sort_keys=True, default=str) == snap, "base config mutated"
    print("check: PASS")


def eval_dir(eid):
    return os.path.join(HERE, "evals", f"{int(eid) // 1000:02d}")


def done_ids():
    out = set()
    ev = os.path.join(HERE, "evals")
    for d in os.listdir(ev):
        p = os.path.join(ev, d)
        if os.path.isdir(p):
            out.update(int(x[5:10]) for x in os.listdir(p) if x.endswith(".ok") and x[5:10].isdigit())
    return out


def cmd_eval(a):
    import resource
    t0 = time.time()
    cfg0, sc0 = load_base()
    if a.id == "headline":
        eid, base_row, block, vals = "headline", -1, "headline", {}
        d = os.path.join(HERE, "checks")
        marker = None
        res = os.path.join(d, "headline_results.csv")
    else:
        eid = int(a.id)
        d = eval_dir(eid)
        os.makedirs(d, exist_ok=True)
        marker = os.path.join(d, f"eval_{eid:05d}.ok")
        if os.path.exists(marker):
            print(f"eval {eid}: already done ({marker})")
            return
        r = pd.read_csv(os.path.join(HERE, "design.csv"), float_precision="round_trip", skiprows=range(1, eid + 1),
                        nrows=1).iloc[0]
        assert int(r["eval_id"]) == eid
        base_row, block = int(r["base_row"]), r["block"]
        vals = {n: decode(n, r[n]) for n in NAMES}
        res = os.path.join(d, f"eval_{eid:05d}.csv")
    cfg, sc = apply(cfg0, sc0, vals)
    print(f"eval {eid} (base row {base_row}, {block}); values {json.dumps(vals, default=str)}", flush=True)
    print(f"  changed keys: {changed(cfg0, sc0, cfg, sc)}", flush=True)
    haul = load_haul(cfg)
    ts = time.time()
    S = make_static(cfg, sc, haul)
    static_s = time.time() - ts
    print(f"  Static {static_s:.1f} s", flush=True)
    rows = []
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else SEEDS
    for seed in seeds:
        t1 = time.time()
        row = {"eval_id": eid, "base_row": base_row, "block": block, "seed": seed, "static_s": round(static_s, 2),
               "pid": os.getpid()}
        try:
            sites, seasons = simulate(cfg, sc, seed, S)
            row.update(outputs(sites, cfg), seasons=seasons, status="ok", error="")
            del sites
        except Unfinished as e:
            row.update({o: float("nan") for o in OUTPUTS}, seasons=e.args[1], status="unfinished", error=e.args[0])
        except Exception as e:   # recorded; no marker, a rerun retries it
            row.update({o: float("nan") for o in OUTPUTS}, seasons=-1, status="error",
                       error=f"{type(e).__name__}: {e}"[:300])
        row["wall_s"] = round(time.time() - t1, 2)
        rows.append(row)
        print(f"  seed {seed}: {row['status']} years {row['island_years']!r} mh {row['island_mh']!r} "
              f"share {row['mh_transport_share']!r} seasons {row['seasons']} wall {row['wall_s']} s "
              f"(peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB)", flush=True)
    tmp = res + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RES_COLS)
        w.writeheader()
        for row in rows:
            w.writerow({k: (repr(row[k]) if isinstance(row.get(k), float) else row.get(k, "")) for k in RES_COLS})
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, res)                                 # atomic: a crashed eval leaves no partial result
    if marker is None:
        pass
    elif all(r_["status"] in ("ok", "unfinished") for r_ in rows):
        open(marker, "w").write(json.dumps({"seeds": seeds, "wall_s": round(time.time() - t0, 1),
                                            "status": [r_["status"] for r_ in rows]}) + "\n")
    else:
        print(f"eval {eid}: an error occurred; no marker (rerun retries it)")
    print(f"eval {eid}: done in {time.time() - t0:.1f} s; peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("design")
    d.add_argument("--force", action="store_true")
    sp.add_parser("check")
    e = sp.add_parser("eval")
    e.add_argument("--id", required=True)
    e.add_argument("--seeds", default=None)
    sp.add_parser("ids")
    a = ap.parse_args()
    if a.cmd == "design":
        cmd_design(a)
    elif a.cmd == "check":
        cmd_check(a)
    elif a.cmd == "eval":
        cmd_eval(a)
    elif a.cmd == "ids":
        n = sum(1 for _ in open(os.path.join(HERE, "design.csv"))) - 1
        dn = done_ids()
        print("\n".join(str(i) for i in range(n) if i not in dn))


if __name__ == "__main__":
    main()
