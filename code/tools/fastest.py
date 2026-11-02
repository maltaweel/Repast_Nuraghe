"""Which scenarios build fastest, and why: one common time metric across all scenario families.

  python tools/fastest.py config.yaml

Time metric: median over sites of each site's mean working days from start to completion, for 1-, 2- and 3-tower
nuraghi, with the model's own workforce (50-200 builders, 8-hour days):
  baseline / cooperation / literature: the ABM's `days` (days_mean in each summary CSV);
  alliance: `days` = working days between a site's start and its completion (seasons of 90 working days are
            counted only by their working days, so the metric is the same).
Labour metric: island man-hours (mean over seeds) and the median man-hours of a 1-tower site.
Stage decomposition from each family's runs file: quarry, dress, transport, build+lift, setup/splits, track, walk,
idle (baseline and cooperation pools are split with Webster's Table 1 shares, which is exact for the 2,500 man-days
per tower; anything above it is setup/splits).
Writes output/fastest_scenarios.csv, output/fastest_stage_decomposition.csv, output/fastest_combined_effects.csv.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
OUT = cfg["paths"]["output_dir"]
H = float(cfg["hours_per_day"])
md = cfg["lit_scenarios"]["webster_md_per_tower"]
lam = cfg["lit_scenarios"]["lift_share_of_build"]
guide = pd.read_csv(os.path.join(OUT, "scenario_guide.csv")).set_index("code")


def sources():
    yield "baseline", "baseline", OUT
    for n in cfg["scenarios"]["list"]:
        yield "cooperation", n, os.path.join(OUT, "scenarios", n)
    for n in cfg["lit_scenarios"]["list"]:
        yield "literature", n, os.path.join(OUT, "scenarios_lit", n)
    for n in cfg["alliance"]["list"]:
        yield "alliance", n, os.path.join(OUT, "scenarios_alliance", n)


def stages(family, d):
    r = pd.read_csv(os.path.join(d, "nuraghe_manhours_runs.csv.gz"))
    g = r.groupby("seed")
    if family == "alliance":
        s = {"quarry": g.mh_quarry.sum(), "dress": g.mh_dress.sum(), "transport": g.mh_transport.sum(),
             "build_lift": g.mh_build.sum() + g.mh_lift.sum(), "setup_splits": g.mh_setup.sum(),
             "track": g.mh_track.sum(), "walk": g.mh_walk.sum(), "idle": 0 * g.mh_total.sum()}
    elif family == "literature":
        s = {"quarry": g.mh_quarry.sum(), "dress": g.mh_dress.sum(), "transport": g.mh_transport.sum(),
             "build_lift": g.mh_build.sum() + g.mh_lift.sum(),
             "setup_splits": g.mh_other.sum() - (g.mh_quarry.sum() + g.mh_dress.sum() + g.mh_build.sum() + g.mh_lift.sum()),
             "track": 0 * g.mh_total.sum(), "walk": g.mh_total.sum() - g.mh_transport.sum() - g.mh_other.sum() - g.mh_idle.sum(),
             "idle": g.mh_idle.sum()}
    else:
        towers = g.TWR_N.sum()
        tot_md = md["quarry"] + md["dress"] + md["build"]
        base_pool = tot_md * H * towers
        s = {"quarry": md["quarry"] * H * towers, "dress": md["dress"] * H * towers, "transport": g.mh_transport.sum(),
             "build_lift": md["build"] * H * towers, "setup_splits": g.mh_other.sum() - base_pool,
             "track": 0 * towers, "walk": g.mh_total.sum() - g.mh_transport.sum() - g.mh_other.sum() - g.mh_idle.sum(),
             "idle": g.mh_idle.sum()}
    out = {k: float(v.mean()) for k, v in s.items()}
    out["total"] = float(g.mh_total.sum().mean())
    out["check"] = sum(out[k] for k in s) - out["total"]
    return out


rows, dec = [], []
for fam, code, d in sources():
    sm = pd.read_csv(os.path.join(d, "nuraghe_manhours_summary.csv"))
    row = {"family": fam, "code": code, "name": guide.loc[code, "name"], "description": guide.loc[code, "description"]}
    for tw in (1, 2, 3):
        s = sm[sm.TWR_N == tw]
        row[f"median_days_twr{tw}"] = float(s.days_mean.median())
        row[f"median_mh_twr{tw}"] = float(s.mh_mean.median())
    s1 = sm[sm.TWR_N == 1]
    bcol = "builders_mean" if "builders_mean" in sm.columns else None
    row["effective_workers_twr1"] = float((s1.mh_mean / (s1.days_mean * H)).median())
    row["builders_twr1"] = float(s1[bcol].median()) if bcol else np.nan
    st = stages(fam, d)
    row["island_mh_mean"] = st["total"]
    rows.append(row)
    dec.append({"family": fam, "code": code, **st})
df = pd.DataFrame(rows)
dec = pd.DataFrame(dec)
b = df[df.code == "baseline"].iloc[0]
for tw in (1, 2, 3):
    df[f"time_saved_pct_twr{tw}"] = 100 * (1 - df[f"median_days_twr{tw}"] / b[f"median_days_twr{tw}"])
df["labour_saved_pct"] = 100 * (1 - df.island_mh_mean / b.island_mh_mean)
df["labour_saved_pct_twr1"] = 100 * (1 - df.median_mh_twr1 / b.median_mh_twr1)
df = df.sort_values(["median_days_twr1", "median_days_twr2", "island_mh_mean"]).reset_index(drop=True)
df.insert(0, "rank_time", np.arange(1, len(df) + 1))
df.to_csv(os.path.join(OUT, "fastest_scenarios.csv"), index=False, float_format="%.4f")
bd = dec[dec.code == "baseline"].iloc[0]
for k in ["quarry", "dress", "transport", "build_lift", "setup_splits", "track", "walk", "idle", "total"]:
    dec[f"d_{k}_pct_of_base"] = 100 * (dec[k] - bd[k]) / bd["total"]
dec.to_csv(os.path.join(OUT, "fastest_stage_decomposition.csv"), index=False, float_format="%.4f")
# combined effects (arithmetic from the comparison files)
lit = pd.read_csv(os.path.join(OUT, "scenarios_lit", "scenario_comparison_lit.csv")).set_index("scenario")
al = pd.read_csv(os.path.join(OUT, "scenarios_alliance", "alliance_comparison.csv")).set_index("scenario")
dd = df.set_index("code")
ce = []


def add(combo, parts, ref, kind, value_of):
    v = value_of(combo); vs = [value_of(p) for p in parts]; r = value_of(ref)
    ce.append({"combination": combo, "parts": "+".join(parts), "reference": ref, "metric": kind,
               "combined_change_pct": 100 * (v / r - 1), "sum_of_parts_pct": sum(100 * (x / r - 1) for x in vs),
               "product_of_parts_pct": 100 * (np.prod([x / r for x in vs]) - 1)})


mh_lit = lambda n: lit.loc[n, "island_mh_mean"]
mh_al = lambda n: al.loc[n, "island_mh_mean"]
days1 = lambda n: dd.loc[n, "median_days_twr1"]
add("LOW", ["S1a_scree", "S2a_unworked", "S3a_rails_tallow", "S4c_internal_stair", "S5b_any_buildstone"], "webster", "island man-hours", mh_lit)
add("HIGH", ["S1b_joints_high", "S2b_fine", "S3d_rough", "S4b_ramp", "S6_density"], "webster", "island man-hours", mh_lit)
add("A5_full", ["A3_trust_learning", "A4_trust_track"], "A2_trust", "island man-hours", mh_al)
add("LOW", ["S1a_scree", "S2a_unworked", "S3a_rails_tallow", "S4c_internal_stair", "S5b_any_buildstone"], "webster", "median days, 1 tower", days1)
add("A5_full", ["A3_trust_learning", "A4_trust_track"], "A2_trust", "median days, 1 tower", days1)
ce = pd.DataFrame(ce)
ce.to_csv(os.path.join(OUT, "fastest_combined_effects.csv"), index=False, float_format="%.4f")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print("================ FASTEST (median working days, model workforce) ================")
print(df[["rank_time", "family", "code", "median_days_twr1", "median_days_twr2", "median_days_twr3", "time_saved_pct_twr1",
          "island_mh_mean", "labour_saved_pct", "median_mh_twr1", "effective_workers_twr1"]].head(14).round(2).to_string(index=False))
print("\nbaseline row:", df[df.code == "baseline"][["rank_time", "median_days_twr1", "island_mh_mean"]].to_dict("records"))
print("\n================ STAGE CHANGE vs baseline (% of baseline island total), top 12 ================")
top = df.code.head(12).tolist()
print(dec.set_index("code").loc[top, [c for c in dec.columns if c.startswith("d_")]].round(2).to_string())
print("max |stage sum - total| =", f"{dec.check.abs().max():.3g}")
print("\n================ COMBINED EFFECTS ================")
print(ce.round(2).to_string(index=False))
