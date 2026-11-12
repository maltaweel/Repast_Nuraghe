#!/usr/bin/env python3
"""Cooperation-model Sobol on the FINAL code (code_v17, CODE_VERSION 2026-11-09-v17), STAGED 10 Nov 2026.
PI approval 10 Nov, option (b): Saltelli N = 512, the 11 factors of the 28 Oct cooperation-model ("stage-2") Sobol,
3 cooperation scenarios only (none, mixed, full), budget about 83 CPU-h.

Model: engine B = model.py day engine (Site / Model, numba kernel site_day), cooperation scenarios
`scenarios.list.{none, mixed, full}` of v17/configs/config_full_audited.yaml (p_coop 0.0 / 0.5 / 1.0, no inter-site help,
no phasing, no literature stages). These are the same three scenarios (same names, same p_coop) as the 28 Oct GPU port
(28 Oct GPU port, gpu/coop_kernel_pr.py UNCOUPLED list). The run is in-process, one MPI singleton rank (no mpirun), the whole
island (7,167 sites) per evaluation; the config is read once and every factor is applied to an in-memory deep copy
(no config or code file is written). code_v17 is imported read-only; numba's cache goes to ./numba_cache.

Design: SALib 1.6.0 sobol.sample(N=512, calc_second_order=False, scramble=True, seed=SAMPLE_SEED) on the unit cube,
k = 11, N (k + 2) = 6,656 rows (SALib order per base row j: A, AB_1..AB_11, B). The same 6,656 rows are run in each of
the 3 scenarios (common design): 19,968 evaluations. One evaluation = one design row x one scenario x ONE seed
(the 28 Oct GPU design was one run per sample: 53,248 runs per scenario = N (k + 2) with N 4,096, k 11).
Seed of an evaluation = base_row + 1 (1..512): the A, AB_i and B rows of one base row share a seed (common random
numbers within a Saltelli block, as Sobol run 1), and the same seed is used in all 3 scenarios.

Level mapping of the uniform sample u in [0, 1):
  unif:    lo + u (hi - lo)
  logunif: exp(ln lo + u (ln hi - ln lo))
  int:     lo + floor(u (hi - lo + 1)) (equal-probability bins; household 3..8 = the 28 Oct run's U(2.5, 8.5) rounded)

Outputs per evaluation (28 Oct definitions, 28 Oct stage-2 notes + Table D1): island_total_mh = sum mh_total,
island_transport_mh = sum mh_transport, median_site_total_mh_TWR1..7 = median of mh_total over the sites with that
tower count; island_days_max = max site days (working days to the last nuraghe, Table D1 / Fig. 1b); plus, recorded
but not part of the 28 Oct set: island_days_p95, median_site_days_TWR1..7, n_splits, n_blocks.

  python coopsobol.py design             -> factors.csv, problem.json, design.csv (refuses to overwrite)
  python coopsobol.py check              -> dry mapping check (no simulation)
  python coopsobol.py ids                -> pending global ids (gid = scenario_index * 6656 + row), one per line
  python coopsobol.py eval --gid G       -> one evaluation -> evals/<scen>/NN/eval_RRRRR.csv + .ok
  python coopsobol.py eval --baseline --scenario S --seed s [--compare]
                                             -> all factors at the config values -> checks/baseline_<S>_seed<s>.csv
                                                (--compare: per-site identity against the v16_final engine-B parts)
  python coopsobol.py eval --gid G --pilot    -> as eval, but writes to checks/pilot_* (no .ok, not in evals/)
"""
import argparse
import copy
import csv
import glob
import json
import math
import os
import resource
import sys
import time
import types

T_START = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(HERE, "numba_cache"))   # never write into code_v17/__pycache__

import numpy as np   # noqa: E402
import pandas as pd  # noqa: E402

FA = "@RUN_DIR@"
CODE = os.path.join(FA, "code")
CFG = os.path.join(FA, "configs/config_full_audited.yaml")
REF_PARTS = os.path.join(FA, "outputs/caches/config_full_audited/runs")   # engine-B identity reference
sys.path.insert(0, CODE)
CODE_VERSION = "2026-11-09-v17"
SCENARIOS = ["none", "mixed", "full"]
N_BASE = 512
SAMPLE_SEED = 20261110
TWRS = list(range(1, 8))
OUT_28OCT = ["island_total_mh", "island_transport_mh"] + [f"median_site_total_mh_TWR{t}" for t in TWRS]
OUTPUTS = OUT_28OCT + ["island_days_max", "island_days_p95"] + [f"median_site_days_TWR{t}" for t in TWRS] + \
    ["n_splits", "n_blocks"]
RES_COLS = ["scenario", "eval_id", "gid", "base_row", "block", "seed", "status", "error"] + OUTPUTS + \
    ["t_import_s", "t_setup_s", "t_run_s", "wall_s", "peak_rss_mb", "pid"]

# ----------------------------------------------------------------------------------- factors
# old = the 28 Oct range (28 Oct GPU port, gpu/sobol2.py: SL.FACTORS = lit-Sobol five + six stage-2 factors; sources in README)
FACTORS = [
    dict(name="pull_kg_per_person", key="transport.pull_kg_per_person", kind="logunif", lo=21.0, hi=127.0,
         old="20-350 log", changed="YES",
         why="Sourced range, PI approval 10 Nov: 21 (sourced pull floor, ALT pull21) to 126.7 = 38 kgf / mu 0.3 "
             "(Richards & Whitby 1997: 242, ALT pull38kgf); 300-500 kg (greased rails / rollers) excluded."),
    dict(name="drag_speed_ms", key="transport.drag_speed_ms", kind="logunif", lo=0.19, hi=1.0,
         old="0.03-0.6 log", changed="YES",
         why="0.03 m/s floor dropped as unsourced (PI 5 Nov); current sourced range 0.19 (de Haan 2009: 7, 55.5 W at "
             "294 N) to 1.0 (Harris 2016 AAM p. 4 peak), log-uniform as Sobol run 1 params.csv. 0.6 = press figure."),
    dict(name="other_mandays_per_tower", key="other_mandays_per_tower", kind="unif", lo=1200.0, hi=8000.0,
         old="1,200-8,000", changed="no",
         why="Range kept (headline 2,500 = Webster 1991 Table 1 3,600 - 1,100 inside). Since v11 the pool is Webster's "
             "quarry/dress/build man-days at their source day lengths (5/8/8 h) + (value - 2,500) x hours_per_day, so "
             "the factor shifts the pool by (value - 2,500) man-days of hours_per_day hours (v8: value x hours_per_day)."),
    dict(name="block_median_kg", key="stone.block_median_kg", kind="unif", lo=300.0, hi=1000.0,
         old="300-1,000", changed="no",
         why="Range kept (= TOST ends; headline 450 Webster 1991: 852; Lilliu 549 inside)."),
    dict(name="builders_mult", key="builders.base / per_extra_tower / min / max (x m)", kind="logunif", lo=0.5, hi=2.0,
         old="x0.5-2", changed="no",
         why="Range kept. Applied as m x (base 50, per_extra_tower 25, min 50, max 200): B = clip(round(m (50 + 25 "
             "(tw - 1)) x U(0.9, 1.1)), 50 m, 200 m). Log-uniform (symmetric multiplier; the v11 Sobol crew_mult "
             "0.5-2 log-uniform cites the 28 Oct run's builders_mult); the 28 Oct distribution is not recorded."),
    dict(name="tonnes_per_tower", key="stone.tonnes_per_tower", kind="unif", lo=900.0, hi=2481.0,
         old="900-2,000", changed="YES",
         why="Sourced range, PI approval 10 Nov: upper end raised to ALT 2,481 (model geometry 1,040 m3 x "
             "2,386 kg/m3, DERIVED) so ALT 1,909 / 2,009 / 2,481 are inside; lower 900 as 28 Oct; headline 1,350."),
    dict(name="block_sigma", key="stone.block_sigma", kind="unif", lo=0.3, hi=0.9,
         old="0.3-0.9", changed="no",
         why="28 Oct run (29 Oct note): 0.3-0.9 uniform (= TOST ends). Kept; DERIVED 0.41-0.72 (PARAM_AUDIT B3) inside."),
    dict(name="load_unload_h", key="transport.load_unload_h", kind="logunif", lo=0.1, hi=1.0,
         old="0.1-1.0 log", changed="no",
         why="28 Oct run (29 Oct note): 0.1-1.0 log. Kept; sourced 0.25 / 0.33 / 0.5 h per block inside. Engine B still charges "
             "it per land trip (add4 L3 1.2 ph/t acts only in the season engine)."),
    dict(name="hours_per_day", key="hours_per_day", kind="unif", lo=6.0, hi=10.0,
         old="6-10", changed="no",
         why="28 Oct run (29 Oct note): 6-10 uniform (= TOST ends). Kept; sourced 5-10 h (Boswinkel 2021: 145-146). Since v11 "
             "Webster's man-days use their source day (5/8/8 h), so this is the simulated working day."),
    dict(name="min_haul_flatm", key="transport.min_haul_flatm", kind="logunif", lo=10.0, hi=20.0,
         old="50-300 log", changed="YES",
         why="Sourced range, PI approval 10 Nov: the PI's stated 10-20 m (5 Nov), as Sobol run 2; the old "
             "50-300 excluded the headline 15. 69% of sites sit on their outcrop (haul 0 -> this value)."),
    dict(name="household_size", key="scenarios.household_size", kind="int", lo=3, hi=8,
         old="U(2.5, 8.5) rounded = 3..8", changed="no",
         why="28 Oct run (29 Oct note): 2.5-8.5 uniform, rounded -> 3..8 with equal probability; here as equal-probability "
             "integer bins (same distribution). Headline 5 (Webster 1991: 852-854); TOST ends 3 / 8."),
]
NAMES = [f["name"] for f in FACTORS]
FBY = {f["name"]: f for f in FACTORS}
K = len(FACTORS)
ROWS = N_BASE * (K + 2)
assert K == 11 and ROWS == 6656


def to_value(f, u):
    u = float(u)
    if f["kind"] == "unif":
        return float(f["lo"] + u * (f["hi"] - f["lo"]))
    if f["kind"] == "logunif":
        return float(math.exp(math.log(f["lo"]) + u * (math.log(f["hi"]) - math.log(f["lo"]))))
    n = int(f["hi"]) - int(f["lo"]) + 1
    return int(f["lo"]) + min(int(math.floor(u * n)), n - 1)


def problem():
    return {"num_vars": K, "names": NAMES, "bounds": [[0.0, 1.0]] * K}


def split_gid(gid):
    si, row = divmod(int(gid), ROWS)
    assert 0 <= si < len(SCENARIOS)
    return SCENARIOS[si], row


def eval_paths(scen, row):
    d = os.path.join(HERE, "evals", scen, f"{row // 1000:02d}")
    return d, os.path.join(d, f"eval_{row:05d}.csv"), os.path.join(d, f"eval_{row:05d}.ok")


# ----------------------------------------------------------------------------------- base and mapping
def load_base():
    import lit
    from nbcommon import load_config
    assert lit.CODE_VERSION == CODE_VERSION, lit.CODE_VERSION
    assert os.path.dirname(os.path.abspath(lit.__file__)) == CODE, lit.__file__
    return load_config(CFG)


def headline(cfg):
    return {"pull_kg_per_person": cfg["transport"]["pull_kg_per_person"],
            "drag_speed_ms": cfg["transport"]["drag_speed_ms"],
            "other_mandays_per_tower": cfg["other_mandays_per_tower"],
            "block_median_kg": cfg["stone"]["block_median_kg"], "builders_mult": 1.0,
            "tonnes_per_tower": cfg["stone"]["tonnes_per_tower"], "block_sigma": cfg["stone"]["block_sigma"],
            "load_unload_h": cfg["transport"]["load_unload_h"], "hours_per_day": cfg["hours_per_day"],
            "min_haul_flatm": cfg["transport"]["min_haul_flatm"],
            "household_size": cfg["scenarios"]["household_size"]}


def apply(cfg0, values):
    """Deep copy of the config with the factor values set (only the factor keys change)."""
    cfg = copy.deepcopy(cfg0)
    for k, x in values.items():
        if k == "pull_kg_per_person":
            cfg["transport"]["pull_kg_per_person"] = float(x)
        elif k == "drag_speed_ms":
            cfg["transport"]["drag_speed_ms"] = float(x)
        elif k == "other_mandays_per_tower":
            cfg["other_mandays_per_tower"] = float(x)
        elif k == "block_median_kg":
            cfg["stone"]["block_median_kg"] = float(x)
        elif k == "builders_mult":
            if float(x) != 1.0:
                b = cfg["builders"]
                for kk in ("base", "per_extra_tower", "min", "max"):
                    b[kk] = float(b[kk]) * float(x)
        elif k == "tonnes_per_tower":
            cfg["stone"]["tonnes_per_tower"] = float(x)
        elif k == "block_sigma":
            cfg["stone"]["block_sigma"] = float(x)
        elif k == "load_unload_h":
            cfg["transport"]["load_unload_h"] = float(x)
        elif k == "hours_per_day":
            cfg["hours_per_day"] = float(x)
        elif k == "min_haul_flatm":
            cfg["transport"]["min_haul_flatm"] = float(x)
        elif k == "household_size":
            cfg["scenarios"]["household_size"] = int(x)
        else:
            raise KeyError(k)
    return cfg


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


def changed(cfg0, cfg):
    a, b = flat(cfg0, "cfg"), flat(cfg, "cfg")
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def decode(n, v):
    return int(v) if FBY[n]["kind"] == "int" else float(v)


def cost_proxy(vals, cfg0):
    """Crude relative island-days proxy of a design row (1.0 = headline), used ONLY to pick pilot rows and to
    scale the projected wall: labour of a 1-tower site / (builders x hours per day), transport and pool parts
    weighted by their headline shares (none, seed 1: transport 64%, pool 36%)."""
    h = headline(cfg0)
    hf = 0.69 * vals["min_haul_flatm"] + 0.31 * 1100.0                  # on-outcrop share / typical off-outcrop haul
    hf0 = 0.69 * h["min_haul_flatm"] + 0.31 * 1100.0
    trip = hf / vals["drag_speed_ms"] / 3600 + hf / 1.39 / 3600 + vals["load_unload_h"]
    trip0 = hf0 / h["drag_speed_ms"] / 3600 + hf0 / 1.39 / 3600 + h["load_unload_h"]
    tr = (vals["tonnes_per_tower"] / h["tonnes_per_tower"]) * (h["pull_kg_per_person"] / vals["pull_kg_per_person"]) \
        * trip / trip0
    pool = (18500.0 + (vals["other_mandays_per_tower"] - 2500.0) * vals["hours_per_day"]) / 18500.0
    lab = 0.64 * tr + 0.36 * pool
    return lab / vals["builders_mult"] / (vals["hours_per_day"] / h["hours_per_day"])


# ----------------------------------------------------------------------------------- commands
def cmd_design(a):
    from SALib.sample import sobol
    for fn in ("design.csv", "problem.json", "factors.csv"):
        assert a.force or not os.path.exists(os.path.join(HERE, fn)), f"{fn} exists (refusing to overwrite)"
    cfg0 = load_base()
    U = sobol.sample(problem(), N_BASE, calc_second_order=False, scramble=True, seed=SAMPLE_SEED)
    assert U.shape == (ROWS, K)
    rows = []
    for e, u in enumerate(U):
        j, c = divmod(e, K + 2)
        block = "A" if c == 0 else ("B" if c == K + 1 else f"AB_{NAMES[c - 1]}")
        r = {"eval_id": e, "base_row": j, "block": block, "seed": j + 1}
        r.update({f"u_{n}": float(u[i]) for i, n in enumerate(NAMES)})
        vals = {n: to_value(FBY[n], u[i]) for i, n in enumerate(NAMES)}
        r.update(vals)
        r["cost_proxy"] = cost_proxy(vals, cfg0)
        rows.append(r)
    D = pd.DataFrame(rows)
    Ua = D[[f"u_{n}" for n in NAMES]].to_numpy()
    for j in range(N_BASE):                                      # Saltelli structure: AB_i = A with column i from B
        blk = Ua[j * (K + 2):(j + 1) * (K + 2)]
        A, B = blk[0], blk[-1]
        for i in range(K):
            exp = A.copy()
            exp[i] = B[i]
            assert np.array_equal(blk[1 + i], exp), (j, i)
    D.to_csv(os.path.join(HERE, "design.csv"), index=False, float_format="%.17g")
    pd.DataFrame([{**f, "headline": headline(cfg0)[f["name"]]} for f in FACTORS]).to_csv(
        os.path.join(HERE, "factors.csv"), index=False)
    json.dump({"problem": problem(), "N": N_BASE, "k": K, "calc_second_order": False,
               "sampler": "SALib 1.6.0 sobol.sample (Saltelli), scramble=True", "sample_seed": SAMPLE_SEED,
               "rows": ROWS, "scenarios": SCENARIOS, "n_evals": ROWS * len(SCENARIOS),
               "seed_rule": "seed = base_row + 1 (one seed per evaluation; same seed in every scenario)",
               "code": CODE, "config": CFG, "code_version": CODE_VERSION, "outputs_28oct": OUT_28OCT,
               "outputs": OUTPUTS,
               "level_mapping": {"unif": "lo + u (hi - lo)", "logunif": "exp(ln lo + u (ln hi - ln lo))",
                                 "int": "lo + floor(u (hi - lo + 1)) (equal-probability bins)"}},
              open(os.path.join(HERE, "problem.json"), "w"), indent=1)
    print(f"design: k = {K}, N = {N_BASE}, {ROWS} rows x {len(SCENARIOS)} scenarios = {ROWS * len(SCENARIOS)} "
          f"evaluations (1 seed each) -> design.csv, factors.csv, problem.json")
    print(f"household_size counts: {D.household_size.value_counts().sort_index().to_dict()}")
    print(f"cost_proxy: mean {D.cost_proxy.mean():.3f}, median {D.cost_proxy.median():.3f}, "
          f"p90 {D.cost_proxy.quantile(0.9):.3f}, max {D.cost_proxy.max():.3f}")


def cmd_check(a):
    """Dry: the headline values lie inside every range; all factors at the config values = no key change; each factor
    at its ends changes only its own key(s) and is read back by model.scenario_params / the config; base not mutated."""
    import model
    cfg0 = load_base()
    snap = json.dumps(cfg0, sort_keys=True, default=str)
    hv = headline(cfg0)
    for f in FACTORS:
        v = hv[f["name"]]
        ok = f["lo"] <= v <= f["hi"]
        print(f"  {f['name']:24s} headline {v!r:>8} range {f['lo']:g}-{f['hi']:g} ({f['kind']}) "
              f"old {f['old']:24s} changed {f['changed']:3s} {'OK' if ok else 'OUTSIDE'}")
        assert ok, f["name"]
    assert changed(cfg0, apply(cfg0, hv)) == [], changed(cfg0, apply(cfg0, hv))
    print("  all factors at the config values: no key changes")
    for s in SCENARIOS:
        sc = model.scenario_params(cfg0, s)
        exp = {"none": 0.0, "mixed": 0.5, "full": 1.0}[s]
        assert float(sc["p_coop"]) == exp and not sc.get("inter_site_help") and not sc.get("phase_frac") \
            and "lit" not in sc and sc.get("site_coop_prob") is None, (s, sc)
        print(f"  scenario {s}: p_coop {sc['p_coop']}, household_size {sc['household_size']}, split_cost_mh "
              f"{sc['split_cost_mh']}, no help / phasing / lit")
    allowed = set()
    for f in FACTORS:
        ch_all = set()
        for u in (0.0, 0.5, 0.999999):
            x = to_value(f, u)
            cfg = apply(cfg0, {f["name"]: x})
            ch = changed(cfg0, cfg)
            ch_all.update(ch)
            n = f["name"]
            if n == "household_size":
                assert model.scenario_params(cfg, "mixed")["household_size"] == x
            elif n == "builders_mult":
                b = cfg["builders"]
                assert abs(b["base"] - 50 * x) < 1e-9 and abs(b["max"] - 200 * x) < 1e-9
        assert ch_all, f"{f['name']} changes nothing"
        allowed |= ch_all
        print(f"  {f['name']:24s} ends {[round(to_value(f, u), 6) for u in (0.0, 0.5, 0.999999)]} -> {sorted(ch_all)}")
    vals = [to_value(FBY["household_size"], (i + 0.5) / 6000) for i in range(6000)]
    cnt = pd.Series(vals).value_counts().sort_index()
    assert list(cnt.index) == list(range(3, 9)) and cnt.max() - cnt.min() <= 1, cnt
    print("  household_size: equal-probability bins 3..8 OK")
    if os.path.exists(os.path.join(HERE, "design.csv")):
        D = pd.read_csv(os.path.join(HERE, "design.csv"), float_precision="round_trip")
        assert len(D) == ROWS and (D.seed == D.base_row + 1).all()
        for _, r in D.sample(300, random_state=1).iterrows():
            v = {n: decode(n, r[n]) for n in NAMES}
            for n in NAMES:
                assert to_value(FBY[n], r[f"u_{n}"]) == v[n], (n, r[f"u_{n}"], v[n])
            assert set(changed(cfg0, apply(cfg0, v))) <= allowed
        print(f"  300 design rows: values = mapping of u; only factor keys change ({len(allowed)} keys)")
    assert json.dumps(cfg0, sort_keys=True, default=str) == snap, "base config mutated"
    print("check: PASS")


def done_gids():
    out = set()
    for si, s in enumerate(SCENARIOS):
        for f in glob.glob(os.path.join(HERE, "evals", s, "*", "eval_*.ok")):
            out.add(si * ROWS + int(os.path.basename(f)[5:10]))
    return out


def simulate(cfg, scen, seed):
    """One whole-island engine-B run in this process (MPI singleton). Returns the per-site DataFrame."""
    from mpi4py import MPI
    import model
    assert MPI.COMM_WORLD.Get_size() == 1, "run as a single process (no mpirun)"
    a = types.SimpleNamespace(sites=None, first_n=None)
    haul = model.load_haul(cfg, a, os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    sc = model.scenario_params(cfg, scen)
    recs = haul[["UID", "uid_int", "TWR_N", "haul_flatm", "haul_m", "quarry_stone"]].to_dict("records")
    t0 = time.time()
    m = model.Model(MPI.COMM_WORLD, cfg, sc, list(enumerate(recs)), int(seed))
    t1 = time.time()
    try:
        res = m.run()
    finally:
        t2 = time.time()
    df = pd.DataFrame(res, columns=model.RES_COLS)
    df.insert(0, "gid", np.arange(len(df)))
    df.insert(0, "seed", int(seed))
    df["UID"] = haul.UID.to_numpy()
    df["TWR_N"] = haul.TWR_N.to_numpy()
    del m
    return df, t1 - t0, t2 - t1, model.run_signature(cfg, haul, sc)


def outputs(df):
    o = {"island_total_mh": float(df.mh_total.sum()), "island_transport_mh": float(df.mh_transport.sum()),
         "island_days_max": float(df.days.max()), "island_days_p95": float(np.percentile(df.days, 95)),
         "n_splits": float(df.n_splits.sum()), "n_blocks": float(df.n_blocks.sum())}
    for t in TWRS:
        d = df[df.TWR_N == t]
        o[f"median_site_total_mh_TWR{t}"] = float(d.mh_total.median()) if len(d) else float("nan")
        o[f"median_site_days_TWR{t}"] = float(d.days.median()) if len(d) else float("nan")
    return o


def write_row(path, row):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RES_COLS)
        w.writeheader()
        w.writerow({k: (repr(row[k]) if isinstance(row.get(k), float) else row.get(k, "")) for k in RES_COLS})
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)                                        # atomic: a crashed eval leaves no partial result


def cmd_eval(a):
    t_imp0 = time.time()
    cfg0 = load_base()
    import model  # noqa: F401  (import cost counted in t_import_s)
    t_import = time.time() - T_START
    if a.baseline:
        scen, row, seed, block, base_row, gid = a.scenario, -1, int(a.seed), "baseline", -1, -1
        vals = {}
        res = os.path.join(HERE, "checks", f"baseline_{scen}_seed{seed}.csv")
        marker = None
    else:
        gid = int(a.gid)
        scen, row = split_gid(gid)
        r = pd.read_csv(os.path.join(HERE, "design.csv"), float_precision="round_trip", skiprows=range(1, row + 1),
                        nrows=1).iloc[0]
        assert int(r["eval_id"]) == row
        base_row, block, seed = int(r["base_row"]), r["block"], int(r["seed"])
        vals = {n: decode(n, r[n]) for n in NAMES}
        if a.pilot:
            res, marker = os.path.join(HERE, "checks", f"pilot_{scen}_row{row:05d}.csv"), None
        else:
            d, res, marker = eval_paths(scen, row)
            os.makedirs(d, exist_ok=True)
            if os.path.exists(marker):
                print(f"eval {gid}: already done ({marker})")
                return
    cfg = apply(cfg0, vals)
    if os.environ.get("COOPSOBOL_MAX_DAYS"):                     # opt-in safety-stop override (README, decision 2):
        cfg["max_days"] = int(os.environ["COOPSOBOL_MAX_DAYS"])  # a stop only; finished runs are unchanged by it
    print(f"eval gid {gid} scenario {scen} row {row} (base row {base_row}, {block}) seed {seed}; "
          f"values {json.dumps(vals)}; changed keys {changed(cfg0, cfg)}", flush=True)
    row_out = {"scenario": scen, "eval_id": row, "gid": gid, "base_row": base_row, "block": block, "seed": seed,
               "pid": os.getpid(), "t_import_s": round(t_import, 2)}
    df = None
    try:
        df, t_setup, t_run, sig = simulate(cfg, scen, seed)
        row_out.update(outputs(df), status="ok", error="", t_setup_s=round(t_setup, 2), t_run_s=round(t_run, 2))
        print(f"  signature {sig}; setup {t_setup:.1f} s, run {t_run:.1f} s", flush=True)
    except RuntimeError as e:
        if "unfinished after max_days" not in str(e):
            raise
        row_out.update({o: float("nan") for o in OUTPUTS}, status="unfinished", error=str(e)[:300])
    except Exception as e:                                       # recorded; no marker, a rerun retries it
        row_out.update({o: float("nan") for o in OUTPUTS}, status="error", error=f"{type(e).__name__}: {e}"[:300])
    row_out["wall_s"] = round(time.time() - T_START, 2)
    row_out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 0)
    write_row(res, row_out)
    print("  " + ", ".join(f"{k} {row_out[k]!r}" for k in ("status", "island_total_mh", "island_transport_mh",
                                                            "island_days_max", "median_site_total_mh_TWR1",
                                                            "wall_s", "peak_rss_mb")), flush=True)
    if marker is not None:
        if row_out["status"] in ("ok", "unfinished"):
            open(marker, "w").write(json.dumps({"seed": seed, "wall_s": row_out["wall_s"],
                                                "status": row_out["status"]}) + "\n")
        else:
            print(f"eval {gid}: error; no marker (rerun retries it): {row_out['error']}")
            sys.exit(3)
    if a.baseline and df is not None:
        df.to_csv(os.path.join(HERE, "checks", f"baseline_{scen}_seed{seed}_sites.csv.gz"), index=False)
        if a.compare:
            compare_ref(df, scen, seed)


def compare_ref(df, scen, seed):
    """Per-site identity of a baseline evaluation against the v16_final engine-B run parts of the same scenario and
    seed (inventory item 24: engine B is unchanged by v17, so the final-model engine-B output = these parts)."""
    import model
    dirs = sorted(glob.glob(os.path.join(REF_PARTS, scen, "*")))
    assert len(dirs) == 1, dirs
    nr = int(open(os.path.join(dirs[0], f"seed_{seed:04d}.done")).read().strip())
    ref = pd.concat([pd.read_csv(os.path.join(dirs[0], f"seed_{seed:04d}.rank{r:03d}of{nr:03d}.csv"),
                                 float_precision="round_trip")                 # default parser is off by <= 1 ulp
                     for r in range(nr)], ignore_index=True).sort_values("gid").reset_index(drop=True)
    cols = [c for c in model.RES_COLS if c in ref.columns]
    mine = df.sort_values("gid").reset_index(drop=True)
    assert len(ref) == len(mine) and (ref.gid.to_numpy() == mine.gid.to_numpy()).all()
    lines = [f"compare baseline {scen} seed {seed} (code_v17, in-process singleton) vs v16_final parts "
             f"{dirs[0]} ({nr} ranks)"]
    nbad = 0
    for c in cols:
        a_, b_ = mine[c].to_numpy(float), ref[c].to_numpy(float)
        same = np.array_equal(a_, b_, equal_nan=True)
        nbad += not same
        mx = float(np.nanmax(np.abs(a_ - b_))) if not same else 0.0
        lines.append(f"  {c:14s} {'IDENTICAL' if same else f'DIFF (max abs {mx:.6g}, {int((a_ != b_).sum())} sites)'}")
    o_m, o_r = outputs(mine), outputs(ref.assign(TWR_N=mine.TWR_N.to_numpy()))
    for k in OUT_28OCT + ["island_days_max"]:
        lines.append(f"  {k:28s} eval {o_m[k]!r:>22}  v16_final {o_r[k]!r:>22}  {'=' if o_m[k] == o_r[k] else '!='}")
    lines.append(f"compare: {'PASS (all per-site columns bit-identical)' if nbad == 0 else f'{nbad} columns differ'}")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(HERE, "checks", f"compare_{scen}_seed{seed}.txt"), "w").write(txt + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("design")
    d.add_argument("--force", action="store_true")
    sp.add_parser("check")
    sp.add_parser("ids")
    e = sp.add_parser("eval")
    e.add_argument("--gid")
    e.add_argument("--baseline", action="store_true")
    e.add_argument("--scenario", choices=SCENARIOS)
    e.add_argument("--seed", default="1")
    e.add_argument("--compare", action="store_true")
    e.add_argument("--pilot", action="store_true")
    a = ap.parse_args()
    if a.cmd == "design":
        cmd_design(a)
    elif a.cmd == "check":
        cmd_check(a)
    elif a.cmd == "ids":
        dn = done_gids()
        print("\n".join(str(i) for i in range(ROWS * len(SCENARIOS)) if i not in dn))
    elif a.cmd == "eval":
        assert a.baseline != (a.gid is not None), "eval needs --gid G or --baseline --scenario S"
        assert not a.baseline or a.scenario, "--baseline needs --scenario"
        cmd_eval(a)


if __name__ == "__main__":
    main()
