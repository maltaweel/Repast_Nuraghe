"""Every scenario run to date, with its realism rating, ranked (executive summary of the 1 Nov (b) edition).

  python tools/all_scenarios.py PRIOR_CSV WL_SUMMARY_CSV WL_RATINGS_MD OUT_CSV

PRIOR_CSV   outputs/summary_all/all_scenarios_prior.csv (built by outputs/summary_all/build_inventory.py from the
            29 Oct - 1 Nov output CSVs; one row per scenario run; checks in checks.csv / INVENTORY_NOTES.md)
WL_SUMMARY  outputs/summary/wl_summary.csv (the 28 wider-literature variants; 100 seeds each)
WL_RATINGS  code/REALISM_RATINGS_WL_1101.md
Adds the 28 rows, recomputes for EVERY row rating_overall = min(rule rating, schedule rating) where a schedule rating
exists (the 29 Oct convention: a scenario is only as realistic as its least realistic part), and ranks by
rating_overall (desc), then rule rating (desc), then island man-hours closeness to MR_P10 (abs % change, asc), then
name. Superseded runs are kept, flagged, and ranked after the current ones.
"""
import re
import sys

import numpy as np
import pandas as pd

FAM_WL = "Wider literature C1-C3, M1-M4 (1 Nov b, on MR_P10)"


def wl_ratings(p):
    out = {}
    for line in open(p, encoding="utf-8"):
        m = re.match(r"^\| ([CM][1-4]_\w+) \| (\d) \| (.+?) \| (.+?) \|\s*$", line)
        if m:
            out[m.group(1)] = (int(m.group(2)), m.group(3), m.group(4))
    return out


def main(prior_p, wl_p, rt_p, out_p):
    d = pd.read_csv(prior_p)
    s = pd.read_csv(wl_p).set_index("scenario")
    RT = wl_ratings(rt_p)
    ref = s.loc["MOST_REALISTIC_P10"]
    rows = []
    for n, r in s.iterrows():
        if n == "MOST_REALISTIC_P10":
            continue
        c = n.replace("MOST_REALISTIC_", "").replace("_P10", "")
        rows.append({
            "family": FAM_WL, "scenario": n,
            "metric_definition": "island years = island day the last nuraghe is finished / 90-day seasons, phased P10 "
                                 "(simulated); island MH = sum of mh_total over the 7,167 sites per seed (M); "
                                 "mean/min/max over 100 seeds",
            "schedule": "P10 simulated (alliance.py)", "season_days": 90.0,
            "years_mean": r.years_max_mean, "years_min": r.years_max_min, "years_max": r.years_max_max,
            "mh_M_mean": r.island_mh_mean / 1e6, "mh_M_min": r.island_mh_min / 1e6, "mh_M_max": r.island_mh_max / 1e6,
            "n_seeds": int(r.seeds), "pct_years_vs_MR_P10": r.years_max_pct_vs_ref,
            "pct_mh_vs_MR_P10": r.island_mh_pct_vs_ref, "comparable": "yes", "comparable_mh": "yes",
            "comparable_note": "MR_P10 plus one rule, same seeds/ranks; wl_summary.csv gives paired per-seed % ranges",
            "rating": RT[c][0], "rating_source": "REALISM_RATINGS_WL_1101.md", "rating_reason": RT[c][1],
            "schedule_rating": 4, "schedule_rating_source": "REALISM_RATINGS.md (29 Oct)", "basis": RT[c][2],
            "source_file": "runs/2026-11-01-wider-lit/outputs/summary/wl_summary.csv", "source_row": n,
            "check": f"identity row MR_P10 = {ref.island_mh_mean / 1e6:.4f} M / {ref.years_max_mean:.4f} yr"})
    a = pd.concat([d, pd.DataFrame(rows)], ignore_index=True)
    a["superseded"] = a.family.str.contains("superseded|pre-fix|pre-30-Oct", case=False, regex=True).astype(int)
    sr = pd.to_numeric(a.schedule_rating, errors="coerce")
    a["rating_overall"] = np.where(sr.notna(), np.minimum(a.rating, sr), a.rating).astype(int)
    a["abs_mh_pct"] = a.pct_mh_vs_MR_P10.abs()
    a = a.sort_values(["superseded", "rating_overall", "rating", "abs_mh_pct", "scenario"],
                      ascending=[True, False, False, True, True], na_position="last").reset_index(drop=True)
    a.insert(0, "rank", np.arange(1, len(a) + 1))
    a.drop(columns=["abs_mh_pct"]).to_csv(out_p, index=False, float_format="%.6g")
    print(f"{len(a)} rows ({len(rows)} new); by overall rating:", a.rating_overall.value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main(*sys.argv[1:5])
