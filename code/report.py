"""Write model outputs (run-level CSV, per-site summary CSV, shapefiles) and print headline statistics.
Called by model.py on rank 0; can also be rerun on its own from an existing runs file:
  python report.py config.yaml
"""
import json
import os
import re
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from nbcommon import load_config


def write_outputs(cfg, haul, df, out_dir, write_shp=True, scenario=None, family="coop"):
    P = cfg["paths"]
    f = cfg["site_fields"]
    H = float(cfg["hours_per_day"])
    runs_path = os.path.join(out_dir, "nuraghe_manhours_runs.csv.gz")
    df.to_csv(runs_path, index=False, float_format="%.4f", compression={"method": "gzip", "mtime": 0})

    g = df.groupby("UID", sort=False)
    summ = pd.DataFrame({
        "mh_mean": g.mh_total.mean(), "mh_min": g.mh_total.min(), "mh_max": g.mh_total.max(),
        "mh_sd": g.mh_total.std(ddof=1),
        "tr_mean": g.mh_transport.mean(), "tr_min": g.mh_transport.min(), "tr_max": g.mh_transport.max(),
        "other_mh": g.mh_other.mean(), "idle_mean": g.mh_idle.mean(),
        "days_mean": g.days.mean(), "days_min": g.days.min(), "days_max": g.days.max(),
        "builders_mean": g.builders.mean(), "blocks_mean": g.n_blocks.mean(),
        "n_split_mean": g.n_splits.mean(), "help_mean": g.mh_help.mean(), "coop_mean": g.n_coop.mean(),
        "mh_qua_mean": g.mh_quarry.mean(), "mh_dre_mean": g.mh_dress.mean(), "mh_bld_mean": g.mh_build.mean(),
        "mh_lift_mean": g.mh_lift.mean(), "ox_h_mean": g.ox_h.mean(),
    }).reset_index()
    sites = gpd.read_file(P["sites"])
    meta = sites[[f["uid"], f["name"], f["comune"], f["tower_filled"]]].rename(
        columns={f["uid"]: "UID", f["name"]: "NAME", f["comune"]: "COMUNE", f["tower_filled"]: "TWR_FILL"})
    h = haul[["UID", "TWR_N", "x", "y", "haul_flatm", "haul_m", "quarry_stone", "quarry_x", "quarry_y",
              "on_outcrop", "haul_flag"]]
    summ = meta.merge(h, on="UID").merge(summ, on="UID")
    summ = summ[["UID", "NAME", "COMUNE", "TWR_N", "TWR_FILL", "x", "y", "haul_flatm", "haul_m", "quarry_stone",
                 "quarry_x", "quarry_y", "on_outcrop", "haul_flag", "mh_mean", "mh_min", "mh_max", "mh_sd",
                 "tr_mean", "tr_min", "tr_max", "other_mh", "idle_mean", "days_mean", "days_min", "days_max",
                 "builders_mean", "blocks_mean", "n_split_mean", "help_mean", "coop_mean"] +
                (["mh_qua_mean", "mh_dre_mean", "mh_bld_mean", "mh_lift_mean", "ox_h_mean"] if family == "lit" else [])]
    summ.to_csv(os.path.join(out_dir, "nuraghe_manhours_summary.csv"), index=False, float_format="%.3f")

    if write_shp:
        shp = summ.rename(columns={
            "haul_flatm": "HAUL_FM", "haul_m": "HAUL_M", "quarry_stone": "Q_STONE", "quarry_x": "Q_X",
            "quarry_y": "Q_Y", "on_outcrop": "ON_OUTCR", "haul_flag": "HAUL_FLAG", "mh_mean": "MH_MEAN",
            "mh_min": "MH_MIN", "mh_max": "MH_MAX", "mh_sd": "MH_SD", "tr_mean": "TR_MEAN", "tr_min": "TR_MIN",
            "tr_max": "TR_MAX", "other_mh": "OTH_MH", "idle_mean": "IDLE_MEAN", "days_mean": "DAY_MEAN",
            "days_min": "DAY_MIN", "days_max": "DAY_MAX", "builders_mean": "BLD_MEAN", "blocks_mean": "BLK_MEAN",
            "n_split_mean": "SPL_MEAN", "help_mean": "HLP_MEAN", "coop_mean": "COOP_MEAN",
            "mh_qua_mean": "MH_QUA", "mh_dre_mean": "MH_DRE", "mh_bld_mean": "MH_BLD", "mh_lift_mean": "MH_LIFT",
            "ox_h_mean": "OX_H"})
        if family == "lit":
            shp["MH_TRA"] = shp["TR_MEAN"]
        shp["ON_OUTCR"] = shp.ON_OUTCR.astype(int)
        gdf = gpd.GeoDataFrame(shp.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(shp.x, shp.y),
                               crs=cfg["crs"])
        assert all(len(c) <= 10 for c in gdf.columns)
        gdf.to_file(os.path.join(out_dir, "nuraghe_manhours.shp"), engine="pyogrio", encoding="UTF-8")
    if write_shp and scenario is None:          # quarries do not depend on the scenario
        q = summ[summ.haul_flag != "unreachable_local"].groupby(["quarry_x", "quarry_y", "quarry_stone"]) \
            .agg(N_SITES=("UID", "size"), MH_SUM=("mh_mean", "sum")).reset_index()
        qg = gpd.GeoDataFrame(q.rename(columns={"quarry_stone": "STONE"})[["STONE", "N_SITES", "MH_SUM"]],
                              geometry=gpd.points_from_xy(q.quarry_x, q.quarry_y), crs=cfg["crs"])
        qg.to_file(os.path.join(out_dir, "quarry_sources.shp"), engine="pyogrio", encoding="UTF-8")
    print_summary(df, summ, H, scenario)
    return summ


def print_summary(df, summ, H, scenario=None):
    print(f"\n================ SUMMARY ({scenario or 'baseline'}) ================")
    nrun = df.seed.nunique()
    per_run = df.groupby("seed").agg(total=("mh_total", "sum"), tr=("mh_transport", "sum"))
    print(f"sites {summ.shape[0]}, runs {nrun} (seeds {df.seed.min()}..{df.seed.max()})")
    print("Island total man-hours (sum over sites, per run):")
    for lab, v in [("mean", per_run.total.mean()), ("min", per_run.total.min()), ("max", per_run.total.max())]:
        print(f"   {lab:4s} {v:,.0f} man-hours = {v / H:,.0f} man-days")
    print(f"   sd across runs {per_run.total.std(ddof=1):,.0f} man-hours")
    tshare = df.mh_transport.sum() / df.mh_total.sum()
    oshare = df.mh_other.sum() / df.mh_total.sum()
    ishare = df.mh_idle.sum() / df.mh_total.sum()
    hshare = df.mh_help.sum() / df.mh_total.sum()
    print(f"Share of total: transport {tshare:.1%}, quarry/build {oshare:.1%}, idle {ishare:.1%}, "
          f"inter-site help (incl. walk) {hshare:.1%}")
    print(f"Splits per site: mean {df.n_splits.mean():.1f}; site-runs with >=1 split {(df.n_splits > 0).mean():.1%}; "
          f"cooperators per site mean {df.n_coop.mean():.1f}; max single-site days {df.days.max()}")
    print("Per-site man-hours by TWR_N (median of per-site means; n sites; median days):")
    for tw, gg in summ.groupby("TWR_N"):
        print(f"   {tw} tower(s): n={len(gg):5d}  median MH {gg.mh_mean.median():>12,.0f}"
              f"  (= {gg.mh_mean.median() / H:,.0f} man-days)  median transport MH {gg.tr_mean.median():>10,.0f}"
              f"  median days {gg.days_mean.median():.0f}")
    print(f"Per-site mean MH overall: median {summ.mh_mean.median():,.0f}, mean {summ.mh_mean.mean():,.0f}, "
          f"max {summ.mh_mean.max():,.0f}")
    print("Haul distribution (per site, n=%d):" % len(summ))
    qs = [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]
    for col in ["haul_m", "haul_flatm"]:
        v = summ[col]
        print(f"   {col:10s} " + "  ".join(f"p{int(q * 100)} {v.quantile(q):,.0f}" for q in qs) +
              f"  mean {v.mean():,.0f}  max {v.max():,.0f}")
    print(f"   sites on an allowed outcrop (haul 0 -> min haul applies): {int(summ.on_outcrop.sum())}")
    print(f"   sites with haul_m <= 1 km: {int((summ.haul_m <= 1000).sum())}, > 5 km: {int((summ.haul_m > 5000).sum())}")
    real = summ[summ.haul_flag != "unreachable_local"]
    print(f"Distinct quarry cells used: {real.groupby(['quarry_x', 'quarry_y']).ngroups}")
    print("Sites per quarry stone type:")
    for k, v in summ.quarry_stone.value_counts().items():
        print(f"   {k:18s} {v}")
    print("Haul flags:", dict(summ.haul_flag.value_counts()))
    print("=========================================")


SC_ABBR = {"none": "NONE", "low": "LOW", "mixed": "MIX", "mostly": "MOST", "full": "FULL", "high": "HIGH",
           "patchwork": "PATCH"}


def _sc_abbr(names):
    """K1 (30 Oct b): unique <= 6-character abbreviations for the MH_/DAY_ shapefile fields. SC_ABBR names keep
    theirs (unchanged). Other names use their first 6 characters, upper case; when several names share that prefix
    (all four S9_sea_*kn gave S9_SEA) each of them uses the LAST 6 alphanumeric characters instead (SEA4KN, SEA2KN, ...),
    and a 2-digit suffix if that still collides. Same purpose as report_alliance._fields (B21)."""
    first = [SC_ABBR.get(n, n.upper()[:6]) for n in names]
    out, used = [], set()
    for k, n in enumerate(names):
        a = first[k]
        if n not in SC_ABBR and first.count(a) > 1:
            a = re.sub(r"[^A-Z0-9]", "", n.upper())[-6:]
        if a in used:
            a = n.upper()[:4] + f"{k:02d}"
        assert a not in used, f"abbreviation collision: {n} -> {a}"
        used.add(a); out.append(a)
    return out


def compare_scenarios(cfg, names):
    """scenario_comparison.csv + one shapefile with MH_*/DAY_* per scenario."""
    H = float(cfg["hours_per_day"])
    root = os.path.join(cfg["paths"]["output_dir"], "scenarios")
    rows, summs = [], {}
    for n in names:
        df = pd.read_csv(os.path.join(root, n, "nuraghe_manhours_runs.csv.gz"))
        sm = pd.read_csv(os.path.join(root, n, "nuraghe_manhours_summary.csv"))
        summs[n] = sm
        pr = df.groupby("seed").mh_total.sum()
        sc = cfg["scenarios"]["list"][n]
        r = {"scenario": n, "p_coop": sc.get("p_coop", np.nan), "site_coop_prob": sc.get("site_coop_prob", np.nan),
             "inter_site_help": bool(sc.get("inter_site_help", False)),
             "island_mh_mean": pr.mean(), "island_mh_min": pr.min(), "island_mh_max": pr.max()}
        r["transport_share"] = df.mh_transport.sum() / df.mh_total.sum()
        r["idle_share"] = df.mh_idle.sum() / df.mh_total.sum()
        r["help_share"] = df.mh_help.sum() / df.mh_total.sum()
        for tw in (1, 2, 3):
            r[f"median_mh_twr{tw}"] = sm[sm.TWR_N == tw].mh_mean.median()
        for tw in (1, 2, 3):
            r[f"median_days_twr{tw}"] = sm[sm.TWR_N == tw].days_mean.median()
        r["mean_splits_per_site"] = df.n_splits.mean()
        r["pct_sites_with_split"] = 100.0 * (df.n_splits > 0).mean()
        r["max_site_days"] = int(df.days.max())
        rows.append(r)
    comp = pd.DataFrame(rows)
    if "full" in names:
        f = comp.loc[comp.scenario == "full", "island_mh_mean"].iloc[0]
        comp.insert(7, "pct_vs_full", 100.0 * (comp.island_mh_mean / f - 1.0))
    comp.to_csv(os.path.join(root, "scenario_comparison.csv"), index=False, float_format="%.4f")
    base = summs[names[0]][["UID", "NAME", "COMUNE", "TWR_N", "TWR_FILL", "x", "y", "haul_m"]].copy()
    for n, a in zip(names, _sc_abbr(names)):
        base = base.merge(summs[n][["UID", "mh_mean", "days_mean"]].rename(
            columns={"mh_mean": f"MH_{a}", "days_mean": f"DAY_{a}"}), on="UID")
    gdf = gpd.GeoDataFrame(base.drop(columns=["x", "y"]).rename(columns={"haul_m": "HAUL_M"}),
                           geometry=gpd.points_from_xy(base.x, base.y), crs=cfg["crs"])
    assert all(len(c) <= 10 for c in gdf.columns)
    gdf.to_file(os.path.join(root, "nuraghe_manhours_scenarios.shp"), engine="pyogrio", encoding="UTF-8")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print("\n================ SCENARIO COMPARISON ================")
    show = comp.copy()
    for c in ["island_mh_mean", "island_mh_min", "island_mh_max"]:
        show[c] = show[c].map(lambda v: f"{v:,.0f}")
    for c in ["transport_share", "idle_share", "help_share"]:
        show[c] = show[c].map(lambda v: f"{v:.1%}")
    print(show.drop(columns=["p_coop", "site_coop_prob", "inter_site_help"]).T.to_string())
    pc = comp.set_index("scenario")
    order = [n for n in ["none", "low", "mixed", "mostly", "full"] if n in pc.index]
    v = pc.loc[order, "island_mh_mean"].to_numpy()
    print("Monotone check (island mean MH by p_coop " + " > ".join(order) + "):",
          [f"{o} {x:,.0f}" for o, x in zip(order, v)],
          "-> strictly decreasing with p_coop:", bool(np.all(np.diff(v) < 0)))
    return comp


LIT_ABBR = {"webster": "WEB", "S1a_scree": "S1A", "S1b_joints_low": "S1BL", "S1b_joints_high": "S1BH",
            "S2a_unworked": "S2A", "S2b_fine": "S2B", "S3a_rails_tallow": "S3A", "S3b_rails_grease": "S3B",
            "S3c_dry_ground": "S3C", "S3d_rough": "S3D", "S3e_oxen": "S3E", "S4a_lever": "S4A", "S4b_ramp": "S4B",
            "S4c_internal_stair": "S4C", "S5a_onsite": "S5A", "S5b_any_buildstone": "S5B", "S5c_complex_far": "S5C",
            "S6_density": "S6", "S7_webster_classes": "S7", "S8_learning": "S8", "LOW": "LOW", "HIGH": "HIGH",
            "REALISTIC": "REAL", "REALISTIC_oxen": "REALOX"}


def compare_lit(cfg, names, root=None):
    """scenario_comparison_lit.csv, duration_years.csv, field lookup and ONE combined shapefile."""
    H = float(cfg["hours_per_day"])
    L = cfg["lit_scenarios"]
    root = root or os.path.join(cfg["paths"]["output_dir"], "scenarios_lit")
    thr = float(L["community_threshold_ph"])
    rows, summs, dur = [], {}, []
    for n in names:
        df = pd.read_csv(os.path.join(root, n, "nuraghe_manhours_runs.csv.gz"))
        sm = pd.read_csv(os.path.join(root, n, "nuraghe_manhours_summary.csv"))
        summs[n] = sm
        pr = df.groupby("seed").mh_total.sum()
        tot = df.mh_total.sum()
        r = {"scenario": n, "field": "MH_" + LIT_ABBR.get(n, n[:7].upper()),
             "island_mh_mean": pr.mean(), "island_mh_min": pr.min(), "island_mh_max": pr.max()}
        for st, col in [("quarry", "mh_quarry"), ("transport", "mh_transport"), ("dress", "mh_dress"),
                        ("build", "mh_build"), ("lift", "mh_lift"), ("idle", "mh_idle")]:
            r[f"share_{st}"] = df[col].sum() / tot
        for tw in (1, 2, 3):
            r[f"median_mh_twr{tw}"] = sm[sm.TWR_N == tw].mh_mean.median()
        r["pct_sites_over_30k"] = 100.0 * (sm.mh_mean > thr).mean()
        r["median_days_twr1"] = sm[sm.TWR_N == 1].days_mean.median()
        r["max_site_days"] = int(df.days.max())
        r["oxen_hours_mean_island"] = df.groupby("seed").ox_h.sum().mean()
        rows.append(r)
        # duration in calendar years, from each site's mean man-days
        md = sm.mh_mean / H
        for D_name, D in L["duration"]["calendars_days"].items():
            for W_name, W in list(L["duration"]["workforces"].items()) + [("community_abm", None)]:
                yrs = (sm.days_mean / D) if W is None else md / (W * D)
                for tw, g in yrs.groupby(sm.TWR_N):
                    dur.append({"scenario": n, "workforce": W_name, "workers": W if W else "50-200 (ABM)",
                                "calendar": D_name, "days_per_year": D, "TWR_N": tw, "n_sites": len(g),
                                "median_years": g.median()})
    comp = pd.DataFrame(rows)
    if "webster" in names:
        w = comp.loc[comp.scenario == "webster", "island_mh_mean"].iloc[0]
        comp.insert(5, "pct_vs_webster", 100.0 * (comp.island_mh_mean / w - 1.0))
    comp.to_csv(os.path.join(root, "scenario_comparison_lit.csv"), index=False, float_format="%.4f")
    dur = pd.DataFrame(dur)
    dur.to_csv(os.path.join(root, "duration_years.csv"), index=False, float_format="%.3f")
    lk = comp[["field", "scenario"]].copy()
    lk["day_field"] = lk.field.str.replace("MH_", "DAY_", regex=False)
    lk["definition"] = [json.dumps(L["list"][n] or {}) for n in lk.scenario]
    lk.to_csv(os.path.join(root, "field_lookup.csv"), index=False)
    base = summs[names[0]][["UID", "NAME", "COMUNE", "TWR_N", "TWR_FILL", "x", "y"]].copy()
    for n, fld in zip(names, comp.field):
        base = base.merge(summs[n][["UID", "mh_mean", "days_mean"]].rename(
            columns={"mh_mean": fld, "days_mean": fld.replace("MH_", "DAY_")}), on="UID")
    gdf = gpd.GeoDataFrame(base.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(base.x, base.y), crs=cfg["crs"])
    assert all(len(c) <= 10 for c in gdf.columns)
    gdf.to_file(os.path.join(root, "nuraghe_manhours_lit_scenarios.shp"), engine="pyogrio", encoding="UTF-8")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
    print("\n================ LITERATURE SCENARIO COMPARISON ================")
    show = comp.copy()
    for c in ["island_mh_mean", "island_mh_min", "island_mh_max", "oxen_hours_mean_island"]:
        show[c] = show[c].map(lambda v: f"{v:,.0f}")
    for c in [c for c in show.columns if c.startswith("share_")]:
        show[c] = show[c].map(lambda v: f"{100 * v:.1f}")
    for c in ["pct_vs_webster", "pct_sites_over_30k"]:
        show[c] = show[c].map(lambda v: f"{v:+.2f}" if c == "pct_vs_webster" else f"{v:.1f}")
    for c in ["median_mh_twr1", "median_mh_twr2", "median_mh_twr3"]:
        show[c] = show[c].map(lambda v: f"{v:,.0f}")
    print(show.drop(columns=["field"]).to_string(index=False))
    for n in [x for x in ["webster", "LOW", "HIGH"] if x in names]:
        t = dur[(dur.scenario == n) & (dur.TWR_N <= 3)].pivot_table(index=["workforce", "calendar"], columns="TWR_N",
                                                                    values="median_years", sort=False)
        print(f"\nMedian years to build, {n} (rows: workforce x calendar; columns: TWR_N)")
        print(t.round(2).to_string())
    return comp


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
    if "--compare" in sys.argv:              # python report.py config.yaml --compare
        compare_scenarios(cfg, list(cfg["scenarios"]["list"]))
        sys.exit(0)
    if "--compare-lit" in sys.argv:          # python report.py config.yaml --compare-lit
        compare_lit(cfg, list(cfg["lit_scenarios"]["list"]))
        sys.exit(0)
    out = cfg["paths"]["output_dir"]
    haul = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    df = pd.read_csv(os.path.join(out, "nuraghe_manhours_runs.csv.gz"))
    write_outputs(cfg, haul[haul.UID.isin(df.UID.unique())], df, out)
