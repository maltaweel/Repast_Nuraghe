"""Summarise SIMULATED phased runs (model.py --scenario NAME_P10, alliance/pre NAME_P10) and their all-at-once twins.

  python tools/phased_sim_summary.py --model DIR [DIR ...] --alliance PARTSDIR [PARTSDIR ...] [--posthoc DIR]

--model    output dirs of model.py runs (nuraghe_manhours_runs.csv.gz; phased ones carry phase, start_day)
--alliance alliance part dirs (cache/runs/alliance_<name>/<hash>; seed_NNNN.sites.csv.gz; phased ones carry
           phase, start_day, finish_day)
--posthoc  NAME:DIR pairs: recompute the post hoc P10/P20 (tools/phased_posthoc.py rule) from an all-at-once model
           output, to check the simulated phasing of an independent scenario (e.g. full_P10) against post hoc.
Per seed: peak_pop = max over phases of the phase's builders (all-at-once: all sites; alliance native: max over
seasons of the builders of building communities); island_days = last finish day (island days, 1-based);
years = island_days / 90; alliance also native seasons (= max finish_season).
"""
import argparse
import glob
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import _scen  # noqa: E402
import phased_posthoc  # noqa: E402

SD = _scen.SEASON_DAYS


def model_rows(d):
    df = pd.read_csv(os.path.join(d, "nuraghe_manhours_runs.csv.gz"))
    name = os.path.basename(os.path.normpath(d))
    out = []
    for seed, g in df.groupby("seed"):
        B = g.builders.to_numpy(); days = g.days.to_numpy()
        if "phase" in g:
            end = g.start_day.to_numpy() + days - 1
            pops = g.groupby("phase").builders.sum()
            durs = g.groupby("phase").days.max()
            island = int(end.max())
            assert island == int(durs.sum()), "phase days do not add up"
            out.append({"scenario": name, "seed": seed, "n_phases": len(pops), "peak_pop": int(pops.max()),
                        "island_days": island, "years": island / SD,
                        "years_season": float(sum(math.ceil(x / SD) for x in durs)), "island_mh": g.mh_total.sum()})
        else:
            out.append({"scenario": name, "seed": seed, "n_phases": 1, "peak_pop": int(B.sum()),
                        "island_days": int(days.max()), "years": days.max() / SD,
                        "years_season": float(math.ceil(days.max() / SD)), "island_mh": g.mh_total.sum()})
    return out


def alliance_rows(d):
    name = os.path.basename(os.path.dirname(os.path.normpath(d))).replace("alliance_", "")
    out = []
    for f in sorted(glob.glob(os.path.join(d, "seed_*.sites.csv.gz"))):
        g = pd.read_csv(f)
        seed = int(g.seed.iloc[0]); B = g.builders.to_numpy()
        ss, fs = g.start_season.to_numpy(), g.finish_season.to_numpy()
        occ = np.zeros(int(fs.max()) + 2, np.int64)
        np.add.at(occ, ss, B); np.add.at(occ, fs + 1, -B)
        r = {"scenario": name, "seed": seed, "native_seasons": int(fs.max()), "island_mh": g.mh_total.sum(),
             "peak_pop": int(np.cumsum(occ).max())}
        if "phase" in g:
            ph = g.groupby("phase").agg(pop=("builders", "sum"), s0=("start_day", "min"), f1=("finish_day", "max"))
            cont = float((ph.f1 - ph.s0 + 1).sum())          # phase spans in working days, idle tails removed
            r.update({"n_phases": len(ph), "peak_pop": int(ph["pop"].max()), "island_days": cont, "years": cont / SD,
                      "years_season": float(fs.max())})
        else:
            r.update({"n_phases": 0, "island_days": float(g.days.max()), "years": g.days.max() / SD,
                      "years_season": float(fs.max())})
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="*", default=[])
    ap.add_argument("--alliance", nargs="*", default=[])
    ap.add_argument("--posthoc", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for d in a.model:
        rows += [dict(r, kind="model") for r in model_rows(d)]
    for d in a.alliance:
        rows += [dict(r, kind="alliance") for r in alliance_rows(d)]
    for spec in a.posthoc:
        nm, d = spec.split(":", 1)
        df = pd.read_csv(os.path.join(d, "nuraghe_manhours_runs.csv.gz"))
        for f in (0.1, 0.2):
            for seed, g in df.groupby("seed"):
                st = phased_posthoc.phase_stats(seed, g.builders.to_numpy(), g.days.to_numpy(), f)
                rows.append({"kind": "posthoc", "scenario": f"{nm}_P{int(f * 100)}(posthoc)", "seed": seed,
                             "n_phases": st["n_phases"], "peak_pop": st["peak_pop"], "years": st["years"],
                             "island_days": st["years"] * SD, "years_season": st["years_season"],
                             "island_mh": g.mh_total.sum()})
    r = pd.DataFrame(rows)
    r.to_csv(a.out.replace(".csv", "_by_seed.csv"), index=False, float_format="%.4f")
    agg = {"seeds": ("seed", "size"), "peak_pop": ("peak_pop", "mean"), "island_days": ("island_days", "mean"),
           "years": ("years", "mean"), "years_season": ("years_season", "mean"), "island_mh": ("island_mh", "mean")}
    if "native_seasons" in r:
        agg["native_seasons"] = ("native_seasons", "mean")
    s = r.groupby(["kind", "scenario"], sort=False).agg(**agg).reset_index()
    s.to_csv(a.out, index=False, float_format="%.4f")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(s.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))


if __name__ == "__main__":
    main()
