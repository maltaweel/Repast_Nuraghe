"""MOST_REALISTIC subset comparison (tests/most_realistic_subset.sh): island MH, setup MH, median site days by TWR 1-3,
island years (max and p95 / 90) and per-nuraghe years (mean, median), means over seeds.

  python tools/mr_subset_compare.py --alliance DIR --lit DIR --parts DIR

Island years:
  phased alliance runs (_P10/_P20/_P100): island days = last finish day + 1 (parts: finish_day, island days, 0-based);
      p95 = the island day by which 95% of the nuraghi are finished.
  native alliance runs (start_rate 1/450): the all-at-once rule on the sites' own spans (max / p95 of days), with the
      native island seasons (max finish_season) shown separately.
  literature runs (independent sites): all-at-once rule (P100) and the post hoc P10 / P20 rule (phasing.cohorts).
Per-nuraghe years = a site's own build span (days) / 90.
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import phasing  # noqa: E402

SD = 90.0


def parts_dir(root, name):
    ds = [d for d in glob.glob(os.path.join(root, f"alliance_{name}", "*")) if glob.glob(os.path.join(d, "*.done"))]
    return max(ds, key=os.path.getmtime)


def base_stats(df):
    out = {}
    per = []
    for s, g in df.groupby("seed"):
        r = {"island_MH": g.mh_total.sum(), "setup_MH": g.mh_setup.sum() if "mh_setup" in g else 0.0,
             "per_nuraghe_MH": g.mh_total.mean(), "workforce": g.builders.sum(),
             "nuraghe_years_mean": (g.days / SD).mean(), "nuraghe_years_median": (g.days / SD).median()}
        per.append(r)
    out.update(pd.DataFrame(per).mean().to_dict())
    for t in (1, 2, 3):
        out[f"med_days_TWR{t}"] = float(df.days[df.TWR_N == t].median())
    return out


def posthoc(df, frac):
    ym, yp = [], []
    for s, g in df.groupby("seed"):
        days = g.days.to_numpy()
        coh = [np.arange(days.size)] if frac is None else phasing.cohorts(days.size, frac, s)
        t0, fin = 0, np.zeros(days.size)
        for c in coh:
            fin[c] = t0 + days[c]
            t0 += days[c].max()
        ym.append(fin.max() / SD); yp.append(np.percentile(fin, 95) / SD)
    return float(np.mean(ym)), float(np.mean(yp))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alliance", required=True)
    ap.add_argument("--lit", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--names", default="MOST_REALISTIC_P10,MOST_REALISTIC_P20,MOST_REALISTIC_P100,"
                    "MOST_REALISTIC_alone_P10,MOST_REALISTIC_alone_P20,MOST_REALISTIC_alone_P100,A3_trust_learning,A0_alone")
    ap.add_argument("--lit-names", default="REALISTIC,webster")
    a = ap.parse_args()
    rows = {}
    for n in a.names.split(","):
        f = os.path.join(a.alliance, n, "nuraghe_manhours_runs.csv.gz")
        if not os.path.exists(f):
            continue
        df = pd.read_csv(f)
        r = base_stats(df)
        if "_P" in n and phasing.split_name(n)[1] is not None:
            pdir = parts_dir(a.parts, n)
            ym, yp, mx = [], [], 0
            for fs in sorted(glob.glob(os.path.join(pdir, "seed_*.sites.csv.gz"))):
                p = pd.read_csv(fs, usecols=["finish_day", "finish_season"])
                fd = p.finish_day.to_numpy() + 1
                ym.append(fd.max() / SD); yp.append(np.percentile(fd, 95) / SD)
                mx = max(mx, int(p.finish_season.max()))
            r.update({"island_years_max": np.mean(ym), "island_years_p95": np.mean(yp), "max_season": mx,
                      "rule": "simulated phases"})
        else:
            r.update({"island_years_max": (df.groupby("seed").days.max() / SD).mean(),
                      "island_years_p95": (df.groupby("seed").days.quantile(0.95) / SD).mean(),
                      "max_season": int(df.finish_season.max()), "rule": "all-at-once rule on own spans (native schedule: max_season)"})
        rows[n] = r
    for n in a.lit_names.split(","):
        df = pd.read_csv(os.path.join(a.lit, n, "nuraghe_manhours_runs.csv.gz"))
        r = base_stats(df)
        for lab, fr in (("P100", None), ("P10", 0.1), ("P20", 0.2)):
            ym, yp = posthoc(df, fr)
            rr = dict(r); rr.update({"island_years_max": ym, "island_years_p95": yp, "max_season": np.nan,
                                     "rule": f"post hoc {lab}"})
            rows[f"{n}_{lab}" if fr else n] = rr
    t = pd.DataFrame(rows).T
    cols = ["island_MH", "setup_MH", "per_nuraghe_MH", "workforce", "med_days_TWR1", "med_days_TWR2", "med_days_TWR3",
            "island_years_max", "island_years_p95", "nuraghe_years_mean", "nuraghe_years_median", "max_season", "rule"]
    t = t[cols]
    with pd.option_context("display.width", 260, "display.max_columns", 30, "display.max_colwidth", 60):
        print(t.to_string(formatters={c: "{:,.0f}".format for c in ["island_MH", "setup_MH", "per_nuraghe_MH", "workforce"]} |
                          {c: "{:,.2f}".format for c in cols[4:11]}))
    t.to_csv(os.path.join(os.path.dirname(os.path.normpath(a.alliance)), "compare.csv"))


if __name__ == "__main__":
    main()
