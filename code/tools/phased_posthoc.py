"""Phased construction P10 / P20, post hoc, for the scenarios whose sites never interact (specified by the authors).

  python tools/phased_posthoc.py [--root REF/output] [--out dev_phase/output] [--fracs 0.1,0.2]

Rule: phase 1 = a random fraction f of the nuraghi (phasing.cohorts: own seeded stream per seed); phase k+1 starts
when ALL nuraghi of phase k are built; finished communities stop working. Valid post hoc only where a site's build
does not depend on any other site: cooperation none/low/mixed/mostly/full/patchwork, baseline, all literature
scenarios (model.py: no inter_site_help -> each Site is stepped on its own RNG stream [seed, uid], nothing is
shared; checked in PHASE_NOTES.md). 'high', alliance and pre-network scenarios are NOT done here (simulation:
model.py / alliance.py with a _P10/_P20 scenario suffix).

Per seed and phase k:  pop_k = sum of builders of the phase's sites;  dur_k = max site days in phase k
  peak_pop      = max_k pop_k                     (all-at-once: the whole island workforce W)
  years         = sum_k dur_k / 90                (continuous: the next phase starts the day after the last finishes)
  years_season  = sum_k ceil(dur_k / 90)          (each phase starts at the beginning of a season)
  years_p95     = sum_k p95_k / 90                (95%-of-phase robustness: next phase starts when 95% are done)
  years_250     = sum_k dur_k / 250               (long-calendar check)
  island_mh     unchanged (sites are independent, so each site costs the same whenever it is built)
Outputs: phased_posthoc.csv (one row per scenario x {P100, P10, P20}, means over seeds) and phased_posthoc_by_seed.csv.
"""
import argparse
import math
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import _scen  # noqa: E402
import phasing  # noqa: E402


def phase_stats(seed, B, days, frac):
    sd = _scen.SEASON_DAYS
    if frac is None:
        coh = [np.arange(days.size)]
    else:
        coh = phasing.cohorts(days.size, frac, seed)
    pops = np.array([B[c].sum() for c in coh])
    dur = np.array([days[c].max() for c in coh], float)
    p95 = np.array([np.percentile(days[c], 95) for c in coh])
    return {"n_phases": len(coh), "peak_pop": int(pops.max()), "min_phase_pop": int(pops.min()),
            "years": dur.sum() / sd, "years_season": float(sum(math.ceil(x / sd) for x in dur)),
            "years_p95": p95.sum() / sd, "years_250": dur.sum() / 250.0,
            "longest_phase_years": dur.max() / sd}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=_scen.REF_ROOT)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output"))
    ap.add_argument("--fracs", default="0.1,0.2")
    a = ap.parse_args()
    fracs = [None] + [float(x) for x in a.fracs.split(",")]
    os.makedirs(a.out, exist_ok=True)
    o0 = _scen.oom_kill()
    rows, seeds = [], []
    t0 = time.time()
    for fam, name, path in _scen.scenarios(a.root):
        if not _scen.independent(fam, name):
            continue
        df = _scen.load_runs(path, fam)
        per = []
        for seed, d in _scen.by_seed(df):
            B = d.builders.to_numpy().astype(np.int64)
            days = d.days.to_numpy().astype(np.int64)
            mh = float(d.mh_total.sum())
            for f in fracs:
                r = {"family": fam, "scenario": name, "phasing": "P100" if f is None else f"P{int(round(f * 100))}",
                     "seed": seed, "workforce": int(B.sum()), "island_mh": mh}
                r.update(phase_stats(seed, B, days, f))
                per.append(r)
        del df
        p = pd.DataFrame(per)
        seeds.append(p)
        g = p.groupby(["family", "scenario", "phasing"], sort=False).agg(
            seeds=("seed", "size"), n_phases=("n_phases", "first"), workforce=("workforce", "mean"),
            peak_pop=("peak_pop", "mean"), peak_pop_max=("peak_pop", "max"), island_mh=("island_mh", "mean"),
            years=("years", "mean"), years_seedmin=("years", "min"), years_seedmax=("years", "max"),
            years_season=("years_season", "mean"), years_p95=("years_p95", "mean"), years_250=("years_250", "mean"),
            longest_phase_years=("longest_phase_years", "mean")).reset_index()
        g["peak_pop_share"] = g.peak_pop / g.workforce
        rows.append(g)
        s = "  ".join(f"{r.phasing}: peak {r.peak_pop:,.0f} yrs {r.years:.2f} (p95 {r.years_p95:.2f})" for r in g.itertuples())
        print(f"  {name:22s} {s}  [{time.time() - t0:.0f} s, peak {_scen.rss_mb()} MB]", flush=True)
    res = pd.concat(rows, ignore_index=True)
    res.to_csv(os.path.join(a.out, "phased_posthoc.csv"), index=False, float_format="%.4f")
    pd.concat(seeds).to_csv(os.path.join(a.out, "phased_posthoc_by_seed.csv"), index=False, float_format="%.4f")
    print(f"wrote {a.out}/phased_posthoc.csv ({res.scenario.nunique()} scenarios); peak RSS {_scen.rss_mb()} MB; "
          f"oom_kill {o0} -> {_scen.oom_kill()}")


if __name__ == "__main__":
    main()
