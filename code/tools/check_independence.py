"""Empirical check that sites are independent in the post hoc scenarios: a site's days / man-hours in a 302-site
subset run (scratch/ref, the delivered v5 code, seeds 1-5, 4 ranks) must equal the same (seed, UID) in the delivered
full-island 7,167-site run. If a scenario couples sites (high: inter-site help) the values differ.

  python tools/check_independence.py
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _scen  # noqa: E402

RUN = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "runs/2026-10-29-bugfix")
SUB = os.path.join(RUN, "scratch/ref/cache/runs")
SITES = open(os.path.join(RUN, "scratch/sites302.txt")).read().strip().split(",")
FULL = {"baseline": "nuraghe_manhours_runs.csv.gz", "lit_webster": "scenarios_lit/webster/nuraghe_manhours_runs.csv.gz"}
for n in _scen.COOP:
    FULL[n] = f"scenarios/{n}/nuraghe_manhours_runs.csv.gz"


def main():
    haul = pd.read_csv(os.path.join(RUN, "scratch/ref/cache/sites_haul.csv"), usecols=["UID"])
    sub_uid = haul.UID[haul.UID.isin(SITES)].to_numpy()          # model.load_haul order = gid of the subset
    for tag, rel in FULL.items():
        d = glob.glob(os.path.join(SUB, tag, "*"))
        if not d:
            continue
        parts = [pd.read_csv(f, usecols=["seed", "gid", "days", "mh_total"]) for f in sorted(glob.glob(os.path.join(d[0], "seed_*.rank*.csv")))]
        s = pd.concat(parts)
        s["UID"] = sub_uid[s.gid.to_numpy()]
        seeds = sorted(s.seed.unique())
        f = pd.read_csv(os.path.join(_scen.REF_ROOT, rel), usecols=["seed", "UID", "days", "mh_total"])
        f = f[f.seed.isin(seeds) & f.UID.isin(SITES)]
        m = s.merge(f, on=["seed", "UID"], suffixes=("_sub", "_full"))
        dd = int((m.days_sub != m.days_full).sum())
        dm = float(np.abs(m.mh_total_sub - m.mh_total_full).max())
        verdict = "INDEPENDENT (identical)" if dd == 0 and dm < 1e-3 else "COUPLED (differs)"
        print(f"  {tag:12s} {len(m):5d} site-runs (seeds {seeds[0]}-{seeds[-1]}): days differ {dd:4d}, "
              f"max |dMH| {dm:12.4f}  -> {verdict}")


if __name__ == "__main__":
    main()
