"""Where the savings are: stage-by-stage decomposition and a pairwise scenario matrix for the alliance runs.

  python tools/alliance_savings.py config.yaml

Reads output/scenarios_alliance/<scenario>/nuraghe_manhours_runs.csv.gz. Writes to output/scenarios_alliance/:
  savings_by_stage.csv  per scenario and stage (quarry, dress, transport, build+lift, setup, track, walk): island
                        man-hours (mean over seeds), change vs A0_alone (man-hours and % of the A0 island total)
  time_by_scenario.csv  median working days and seasons per tower by TWR_N, island completion (seasons),
                        days per tower for sites that received help vs not
  scenario_matrix.csv   pairwise (row vs column): % difference in island man-hours, in the median days per tower
                        (all sites) and in the mean island completion season
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

STAGES = {"quarry": ["mh_quarry"], "dress": ["mh_dress"], "transport": ["mh_transport"],
          "build_lift": ["mh_build", "mh_lift"], "setup": ["mh_setup"], "track": ["mh_track"], "walk": ["mh_walk"]}

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
root = os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance")
names = list(cfg["alliance"]["list"])
sd = int(cfg["alliance"]["season_days"])
isl, tim, per_tower = {}, [], {}
for n in names:
    r = pd.read_csv(os.path.join(root, n, "nuraghe_manhours_runs.csv.gz"))
    g = r.groupby("seed")
    st = {k: g[cols].sum().sum(axis=1).mean() for k, cols in STAGES.items()}
    st["total"] = g.mh_total.sum().mean()
    st["check_sum_minus_total"] = sum(st[k] for k in STAGES) - st["total"]
    isl[n] = st
    r["days_per_tower"] = r.days / r.TWR_N
    r["seasons_per_tower"] = r.years / r.TWR_N
    per_tower[n] = r.days_per_tower.median()
    row = {"scenario": n, "island_seasons_mean": g.finish_season.max().mean(),
           "median_days_per_tower_all": r.days_per_tower.median()}
    for tw in (1, 2, 3):
        d = r[r.TWR_N == tw]
        row[f"median_days_per_tower_twr{tw}"] = d.days_per_tower.median()
        row[f"median_seasons_twr{tw}"] = d.years.median()
        row[f"mean_seasons_twr{tw}"] = d.years.mean()
    h = r.mh_received > 0
    row["share_site_runs_helped"] = h.mean()
    row["median_days_per_tower_helped"] = r.days_per_tower[h].median() if h.any() else np.nan
    row["median_days_per_tower_not_helped"] = r.days_per_tower[~h].median()
    row["mean_days_per_tower_helped"] = r.days_per_tower[h].mean() if h.any() else np.nan
    row["mean_days_per_tower_not_helped"] = r.days_per_tower[~h].mean()
    tim.append(row)
a0 = isl["A0_alone"]
rows = []
for n in names:
    for k in list(STAGES) + ["total"]:
        rows.append({"scenario": n, "stage": k, "island_mh_mean": isl[n][k], "a0_mh_mean": a0[k],
                     "change_vs_A0_mh": isl[n][k] - a0[k], "change_vs_A0_pct_of_A0_total": 100 * (isl[n][k] - a0[k]) / a0["total"]})
sav = pd.DataFrame(rows)
sav.to_csv(os.path.join(root, "savings_by_stage.csv"), index=False, float_format="%.4f")
tim = pd.DataFrame(tim)
tim.to_csv(os.path.join(root, "time_by_scenario.csv"), index=False, float_format="%.4f")
t = tim.set_index("scenario")
mat = []
for a in names:
    for b in names:
        mat.append({"row": a, "col": b,
                    "pct_island_mh": 100 * (isl[a]["total"] / isl[b]["total"] - 1),
                    "pct_median_days_per_tower": 100 * (t.loc[a, "median_days_per_tower_all"] / t.loc[b, "median_days_per_tower_all"] - 1),
                    "diff_island_seasons": t.loc[a, "island_seasons_mean"] - t.loc[b, "island_seasons_mean"]})
mat = pd.DataFrame(mat)
mat.to_csv(os.path.join(root, "scenario_matrix.csv"), index=False, float_format="%.4f")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
print("================ SAVINGS BY STAGE vs A0_alone (% of the A0 island total) ================")
print(sav.pivot(index="scenario", columns="stage", values="change_vs_A0_pct_of_A0_total").loc[names].round(3).to_string())
print("\nman-hours change vs A0 (island, mean over seeds)")
print(sav.pivot(index="scenario", columns="stage", values="change_vs_A0_mh").loc[names].round(0).to_string())
print("\ncheck: max |sum of stages - total| =", f"{max(abs(v['check_sum_minus_total']) for v in isl.values()):.3g}")
print("\n================ TIME ================")
print(tim.round(3).to_string(index=False))
print("\n================ PAIRWISE: % difference in island man-hours (row vs column) ================")
print(mat.pivot(index="row", columns="col", values="pct_island_mh").loc[names, names].round(2).to_string())
