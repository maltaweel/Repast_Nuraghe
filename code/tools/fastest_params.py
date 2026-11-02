"""Fastest parameter sets per scenario from a Nurnet collaborator's GPU sweep outputs (specified by the authors).

  python tools/fastest_params.py SWEEP.npz [SWEEP2.npz ...] [--out dev_phase/output/fastest_params] [--top 10] [--decile 0.1]
  python tools/fastest_params.py --make-synthetic dev_phase/scratch/synthetic_sweep.npz      (schema test file)

Accepted npz schema (flexible, a Nurnet collaborator's sweep):
  X              (N, 11) parameter values, one row per run (Saltelli/Morris sample)
  x_names        (11,) parameter names (also accepted: names, param_names, factors); default = the stage-2 factors
  Y              (N, M) outputs with y_names (M,) ... OR one key per output, e.g. island_days_max, island_days_p95,
                 island_days_median, median_site_days_TWR1..7 (other outputs, e.g. island_total_mh, are carried along)
  scenario       optional: scalar name, or (N,) per-row names (several scenarios in one file); default = file stem
  bounds         optional (11, 2) sampling bounds (reported with the ranges)
Rows with a non-finite island_days_max (unfinished / flagged runs) are dropped and counted.
Per scenario:
  top10_island_days_max.csv  the 10 runs with the lowest island_days_max (ties: median TWR1 days), all parameters + outputs
  top10_median_TWR1.csv      the 10 runs with the lowest median_site_days_TWR1
  ranges.csv                 per parameter: median (and 10-90%) over ALL runs vs over the FASTEST DECILE (by
                             island_days_max, and by median TWR1 days); shift = (fast median - all median) / (bounds or
                             sample range); Spearman rho of the parameter with island_days_max (negative = higher value faster)
  fastest_summary.csv        across scenarios: best island_days_max / years and its parameter set, one row per scenario
"""
import argparse
import os

import numpy as np
import pandas as pd

DEFAULT_X = ["block_median_kg", "block_sigma", "builders_mult", "drag_speed_ms", "hours_per_day", "household_size",
             "load_unload_h", "min_haul_flatm", "other_mandays_per_tower", "pull_kg_per_person", "tonnes_per_tower"]
KEY = "island_days_max"
TWR1 = "median_site_days_TWR1"
SEASON_DAYS = 90


def _names(z, keys, default=None):
    for k in keys:
        if k in z:
            return [str(x) for x in np.atleast_1d(z[k])]
    return default


def load(path):
    z = np.load(path, allow_pickle=True)
    X = np.asarray(z["X"], float)
    xn = _names(z, ["x_names", "names", "param_names", "factors"], DEFAULT_X)
    assert X.ndim == 2 and X.shape[1] == len(xn), f"{path}: X is {X.shape}, {len(xn)} names"
    df = pd.DataFrame(X, columns=xn)
    if "Y" in z:
        Y = np.asarray(z["Y"], float)
        Y = Y[:, None] if Y.ndim == 1 else Y
        yn = _names(z, ["y_names", "outputs", "out_names"])
        assert yn and len(yn) == Y.shape[1], f"{path}: Y needs y_names"
        for j, n in enumerate(yn):
            df[n] = Y[:, j]
    skip = {"X", "Y", "x_names", "names", "param_names", "factors", "y_names", "outputs", "out_names", "scenario",
            "scenarios", "bounds"}
    for k in z.files:
        if k not in skip:
            v = np.asarray(z[k])
            if v.ndim == 1 and v.shape[0] == len(df) and np.issubdtype(v.dtype, np.number):
                df[k] = v.astype(float)
    sc = z["scenario"] if "scenario" in z else (z["scenarios"] if "scenarios" in z else None)
    stem = os.path.splitext(os.path.basename(path))[0]
    if sc is None or np.ndim(sc) == 0:
        df["scenario"] = stem if sc is None else str(sc)
    else:
        df["scenario"] = np.asarray(sc).astype(str)
    bounds = np.asarray(z["bounds"], float) if "bounds" in z else None
    assert KEY in df, f"{path}: no {KEY}"
    return df, xn, bounds


def analyse(df, xn, bounds, top, dec, out):
    os.makedirs(out, exist_ok=True)
    rows = []
    for sc, d in df.groupby("scenario", sort=False):
        n0 = len(d)
        d = d[np.isfinite(d[KEY])].copy()
        dropped = n0 - len(d)
        d["island_years_max"] = d[KEY] / SEASON_DAYS
        sd = os.path.join(out, sc); os.makedirs(sd, exist_ok=True)
        sort1 = [KEY] + ([TWR1] if TWR1 in d else [])
        t1 = d.sort_values(sort1, kind="stable").head(top)
        t1.insert(0, "rank", np.arange(1, len(t1) + 1)); t1.to_csv(os.path.join(sd, "top10_island_days_max.csv"), index_label="run")
        if TWR1 in d:
            t2 = d[np.isfinite(d[TWR1])].sort_values([TWR1, KEY], kind="stable").head(top)
            t2.insert(0, "rank", np.arange(1, len(t2) + 1)); t2.to_csv(os.path.join(sd, "top10_median_TWR1.csv"), index_label="run")
        rr = []
        crit = [(KEY, "island_max")] + ([(TWR1, "twr1")] if TWR1 in d else [])
        ranks_key = d[KEY].rank().to_numpy()
        for j, p in enumerate(xn):
            v = d[p].to_numpy()
            span = (bounds[j, 1] - bounds[j, 0]) if bounds is not None else (np.nanmax(v) - np.nanmin(v))
            r = {"scenario": sc, "param": p, "all_median": np.median(v), "all_p10": np.percentile(v, 10),
                 "all_p90": np.percentile(v, 90),
                 "lo": bounds[j, 0] if bounds is not None else np.nanmin(v),
                 "hi": bounds[j, 1] if bounds is not None else np.nanmax(v)}
            for col, tag in crit:
                fast = d[col] <= d[col].quantile(dec)
                fv = v[fast.to_numpy()]
                r[f"fast_{tag}_median"] = np.median(fv)
                r[f"fast_{tag}_p10"] = np.percentile(fv, 10); r[f"fast_{tag}_p90"] = np.percentile(fv, 90)
                r[f"fast_{tag}_shift"] = (np.median(fv) - np.median(v)) / span if span > 0 else 0.0
            rv = pd.Series(v).rank().to_numpy()
            r["spearman_island_max"] = float(np.corrcoef(rv, ranks_key)[0, 1]) if np.std(rv) > 0 else 0.0
            rr.append(r)
        rg = pd.DataFrame(rr).sort_values("fast_island_max_shift", key=np.abs, ascending=False)
        rg.to_csv(os.path.join(sd, "ranges.csv"), index=False, float_format="%.6g")
        best = t1.iloc[0]
        rows.append({"scenario": sc, "runs": len(d), "dropped_nonfinite": dropped,
                     "best_island_days_max": best[KEY], "best_island_years_max": best[KEY] / SEASON_DAYS,
                     "median_island_days_max": d[KEY].median(),
                     "fast_decile_island_days_max": d[KEY].quantile(dec),
                     **{f"best_{p}": best[p] for p in xn},
                     "drivers": "; ".join(f"{r.param} {'high' if r.fast_island_max_shift > 0 else 'low'} "
                                          f"({r.all_median:.4g}->{r.fast_island_max_median:.4g})"
                                          for r in rg.head(3).itertuples())})
        print(f"\n== {sc}: {len(d)} runs ({dropped} non-finite dropped); island_days_max best {best[KEY]:.1f} d "
              f"({best[KEY] / SEASON_DAYS:.2f} yr), median {d[KEY].median():.1f}, fastest {int(dec * 100)}% <= {d[KEY].quantile(dec):.1f}")
        print("   top 3 sets:")
        for r in t1.head(3).itertuples():
            print("    " + ", ".join(f"{p}={getattr(r, p):.4g}" for p in xn) + f" -> {getattr(r, KEY):.1f} d")
        print(f"   parameter ranges, all runs vs fastest {int(dec * 100)}% (median [p10-p90]), shift as share of range, rho:")
        for r in rg.itertuples():
            print(f"    {r.param:24s} all {r.all_median:9.4g} [{r.all_p10:.4g}-{r.all_p90:.4g}]  fast {r.fast_island_max_median:9.4g} "
                  f"[{r.fast_island_max_p10:.4g}-{r.fast_island_max_p90:.4g}]  shift {r.fast_island_max_shift:+.2f}  rho {r.spearman_island_max:+.2f}")
    s = pd.DataFrame(rows)
    s.to_csv(os.path.join(out, "fastest_summary.csv"), index=False, float_format="%.6g")
    print(f"\nwrote {out}/fastest_summary.csv ({len(s)} scenarios)")


def make_synthetic(path, n=4096, seed=1):
    """Same schema as the GPU sweep: X (n x 11) within the stage-2 bounds, Y with island/TWR day outputs from a toy
    labour/workforce response (days ~ tonnes x (haul/drag + load) / (pull x builders x hours)). TEST DATA ONLY."""
    rng = np.random.default_rng(seed)
    b = np.array([[350, 550], [0.4, 0.8], [0.8, 1.2], [0.4, 0.8], [6, 10], [3, 8], [0.1, 0.5], [50, 200],
                  [2000, 3000], [70, 130], [1100, 1600]], float)
    X = b[:, 0] + rng.random((n, 11)) * (b[:, 1] - b[:, 0])
    c = dict(zip(DEFAULT_X, X.T))
    labour_tower = c["tonnes_per_tower"] * 1000 / c["pull_kg_per_person"] * (1500 / c["drag_speed_ms"] / 3600 + c["load_unload_h"]) \
        + c["other_mandays_per_tower"] * c["hours_per_day"]
    rate = 50 * c["builders_mult"] * c["hours_per_day"]
    twr = np.stack([labour_tower * k / (rate * (1 + 0.5 * (k - 1))) for k in range(1, 8)], 1)
    twr *= np.exp(rng.normal(0, 0.03, twr.shape))
    tail = 1 + 12 * (0.6 / c["drag_speed_ms"]) * (100 / c["pull_kg_per_person"]) * np.exp(rng.normal(0, 0.05, n))
    Y = np.column_stack([twr, twr[:, 0] * tail, twr[:, 0] * 1.8, twr[:, 0] * 0.95,
                         labour_tower * 7167 * 1.3])
    yn = [f"median_site_days_TWR{k}" for k in range(1, 8)] + ["island_days_max", "island_days_p95",
                                                              "island_days_median", "island_total_mh"]
    Y[rng.random(n) < 0.002, 7] = np.nan            # a few flagged runs
    np.savez(path, X=X, x_names=np.array(DEFAULT_X), Y=Y, y_names=np.array(yn), bounds=b,
             scenario=np.where(rng.random(n) < 0.5, "full", "mixed"))
    print(f"wrote synthetic sweep {path}: X {X.shape}, Y {Y.shape} (scenarios full/mixed) - TEST DATA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("npz", nargs="*")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "fastest_params"))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--decile", type=float, default=0.1)
    ap.add_argument("--make-synthetic")
    a = ap.parse_args()
    if a.make_synthetic:
        make_synthetic(a.make_synthetic)
        if not a.npz:
            return
    parts, xn, bounds = [], None, None
    for p in a.npz:
        d, x, b = load(p)
        assert xn is None or x == xn, "all sweep files must have the same parameters"
        xn, bounds = x, (b if b is not None else bounds)
        parts.append(d)
    analyse(pd.concat(parts, ignore_index=True), xn, bounds, a.top, a.decile, a.out)


if __name__ == "__main__":
    main()
