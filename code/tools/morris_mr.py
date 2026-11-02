"""Morris screen of MOST_REALISTIC_P10 (join) over the influential factors only (specified by the authors: drop the others).

  python tools/morris_mr.py design --cfg CFG --out DIR [--r 10 --seed 2026]   -> DIR/design.csv, DIR/cfg/run_NNN.yaml, DIR/commands.txt
  (run the commands, e.g. xargs -P 6, each: model.py run_NNN.yaml --alliance MOST_REALISTIC_P10 --seeds 1 --no-merge)
  python tools/morris_mr.py analyse --out DIR                                  -> DIR/morris_mr.csv (mu*, sigma per factor x output)

Factors (k = 5; r = 10 trajectories -> r (k + 1) = 60 runs, 1 seed each; p = 4 levels, delta = 2/3):
  pull_kg_per_person  per-person pull. MOST_REALISTIC crews use 30 kgf / mu (lit f_person_kgf), not the mu-0.3 pull,
                      so the factor scales BOTH: f_person_kgf = 30 x pull / 100 and pull_kg_per_person = pull
  drag_speed_ms, tonnes_per_tower, load_unload_h, min_haul_flatm: the config values themselves
SKIPPED: other_mandays_per_tower. The alliance model never reads it (stage hours come from the Webster stages /
the REALISTIC per-site rules), so it cannot be varied there; its literature analogue is the stage-hour set itself.
Fixed at defaults: builders (MOST_REALISTIC work-party rule), block_median_kg, block_sigma, household_size,
hours_per_day.
RANGES: the stage-2 Sobol ranges are in a Nurnet collaborator's gpu/sobol2.py, which is NOT on this machine (REF README lists the
factors only). The ranges below are (were placeholders; replaced 15:19 with a Nurnet collaborator's ranges) centred on the defaults; replace RANGES before the night run if
a Nurnet collaborator's file is available (the design must then be regenerated).
Outputs per run: island MH, island days max / p95 (island finish days, phased), median site days TWR1-3.
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd
import yaml

RANGES = {"pull_kg_per_person": (20.0, 350.0), "drag_speed_ms": (0.03, 0.6), "tonnes_per_tower": (900.0, 2000.0),
          "load_unload_h": (0.1, 1.0), "min_haul_flatm": (50.0, 300.0)}       # a Nurnet collaborator 29 Oct: alliance npz (pull, drag) + gpu/sobol2.py (rest)       # (were placeholders; replaced 15:19 with a Nurnet collaborator's ranges), see docstring
LOG = {"pull_kg_per_person", "drag_speed_ms", "load_unload_h", "min_haul_flatm"}   # a Nurnet collaborator alliance Sobol npz 29 Oct: lo/hi + islog (20-350, 0.03-0.6, log)
SCEN = "MOST_REALISTIC_P10"


def trajectories(k, r, p, rng):
    """Morris (1991) one-at-a-time trajectories on the p-level grid of [0,1]^k: r x (k + 1) points."""
    delta = p / (2.0 * (p - 1))
    levels = np.arange(p // 2) / (p - 1)                     # start levels so that x + delta stays in [0, 1]
    X = []
    for _ in range(r):
        x = rng.choice(levels, k)
        order = rng.permutation(k)
        sign = rng.choice([-1.0, 1.0], k)
        pts = [x.copy()]
        for j in order:
            x = x.copy()
            x[j] = x[j] + delta if sign[j] > 0 or x[j] - delta < 0 else x[j] - delta
            pts.append(x)
        X.append(np.array(pts))
    return np.array(X), delta


def design(a):
    names = list(RANGES)
    X, delta = trajectories(len(names), a.r, 4, np.random.default_rng(a.seed))
    base = yaml.safe_load(open(a.cfg))
    os.makedirs(os.path.join(a.out, "cfg"), exist_ok=True)
    rows, cmds = [], []
    for t in range(X.shape[0]):
        for s in range(X.shape[1]):
            v = {n: float(np.exp(np.log(RANGES[n][0]) + X[t, s, j] * (np.log(RANGES[n][1]) - np.log(RANGES[n][0]))) if n in LOG else RANGES[n][0] + X[t, s, j] * (RANGES[n][1] - RANGES[n][0])) for j, n in enumerate(names)}
            run = t * X.shape[1] + s
            c = yaml.safe_load(yaml.safe_dump(base))
            c["transport"]["pull_kg_per_person"] = v["pull_kg_per_person"]
            c["lit_scenarios"]["f_person_kgf"] = 30.0 * v["pull_kg_per_person"] / 100.0
            c["transport"]["drag_speed_ms"] = v["drag_speed_ms"]
            c["stone"]["tonnes_per_tower"] = v["tonnes_per_tower"]
            c["transport"]["load_unload_h"] = v["load_unload_h"]
            c["transport"]["min_haul_flatm"] = v["min_haul_flatm"]
            f = os.path.join(a.out, "cfg", f"run_{run:03d}.yaml")
            yaml.safe_dump(c, open(f, "w"), sort_keys=False)
            rows.append({"run": run, "traj": t, "step": s, **v, **{f"u_{n}": X[t, s, j] for j, n in enumerate(names)}})
            cmds.append(f"{a.py} model.py {f} --alliance {SCEN} --seeds 1 --no-merge --no-shapefile "
                        f"--parts-dir {os.path.join(a.out, 'parts', f'run_{run:03d}')}")
    pd.DataFrame(rows).to_csv(os.path.join(a.out, "design.csv"), index=False)
    open(os.path.join(a.out, "commands.txt"), "w").write("\n".join(cmds) + "\n")
    print(f"{len(rows)} runs ({a.r} trajectories x {len(names) + 1}), delta {delta:.3f} -> {a.out}/commands.txt")


def outputs(d):
    f = glob.glob(os.path.join(d, f"alliance_{SCEN}", "*", "seed_0001.sites.csv.gz"))
    if not f:
        return None
    s = pd.read_csv(f[0], usecols=["TWR_N", "mh_total", "days", "finish_day"])
    fd = s.finish_day.to_numpy() + 1.0
    o = {"island_mh": s.mh_total.sum(), "island_days_max": fd.max(), "island_days_p95": float(np.percentile(fd, 95))}
    for t in (1, 2, 3):
        o[f"median_days_TWR{t}"] = float(s.days[s.TWR_N == t].median())
    return o


def analyse(a):
    D = pd.read_csv(os.path.join(a.out, "design.csv"))
    names = list(RANGES)
    Y = []
    for r in D.run:
        o = outputs(os.path.join(a.out, "parts", f"run_{r:03d}"))
        Y.append(o if o else {})
    Y = pd.DataFrame(Y)
    D = pd.concat([D, Y], axis=1)
    D.to_csv(os.path.join(a.out, "design_outputs.csv"), index=False)
    res = []
    for out in Y.columns:
        ee = {n: [] for n in names}
        for t, g in D.groupby("traj"):
            g = g.sort_values("step")
            U = g[[f"u_{n}" for n in names]].to_numpy(); y = g[out].to_numpy()
            for s in range(1, len(g)):
                j = int(np.flatnonzero(np.abs(U[s] - U[s - 1]) > 1e-12)[0])
                ee[names[j]].append((y[s] - y[s - 1]) / (U[s, j] - U[s - 1, j]))
        for n in names:
            e = np.array(ee[n], float); e = e[np.isfinite(e)]
            res.append({"output": out, "factor": n, "mu_star": np.abs(e).mean(), "mu": e.mean(), "sigma": e.std(ddof=1),
                        "n_ee": e.size})
    R = pd.DataFrame(res)
    R["pct_of_max"] = 100 * R.mu_star / R.groupby("output").mu_star.transform("max")
    R.sort_values(["output", "mu_star"], ascending=[True, False]).to_csv(os.path.join(a.out, "morris_mr.csv"), index=False)
    print(R.sort_values(["output", "mu_star"], ascending=[True, False]).to_string(index=False))
    print(f"runs with outputs: {Y.dropna().shape[0]} / {len(D)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["design", "analyse"])
    ap.add_argument("--cfg"); ap.add_argument("--out", required=True)
    ap.add_argument("--r", type=int, default=10); ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--py", default=sys.executable)
    a = ap.parse_args()
    design(a) if a.cmd == "design" else analyse(a)


if __name__ == "__main__":
    main()
