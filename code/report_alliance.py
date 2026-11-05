"""Outputs of the alliance scenarios (called by alliance.run on rank 0, or `python report_alliance.py config.yaml`).

Per scenario, in output/scenarios_alliance/<name>/:
  nuraghe_manhours_runs.csv.gz, nuraghe_manhours_summary.csv, nuraghe_manhours.shp,
  alliances.shp, handoffs.shp, tracks_uses.tif, strategy_by_season.csv, specialisation.csv, stats.json
Across scenarios: alliance_comparison.csv, nuraghe_manhours_alliance.shp, field_lookup.csv, sensitivity.csv.
"""
import glob
import json
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from nbcommon import load_config

ABBR = {"A0_alone": "A0", "A1_ask": "A1", "A2_trust": "A2", "A3_trust_learning": "A3", "A4_trust_track": "A4",
        "A5_full": "A5", "A5_full_freerider": "A5FR"}
SEASON_BIN = 25


def read_parts(run_dir, seeds, kind):
    fr = [pd.read_csv(os.path.join(run_dir, f"seed_{s:04d}.{kind}.csv.gz")) for s in seeds]
    fr = [f for f in fr if len(f)]
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def components(pairs):
    """Connected components of an undirected edge list; returns list of sizes (>= 2)."""
    parent = {}

    def f(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in pairs:
        ra, rb = f(a), f(b)
        if ra != rb:
            parent[ra] = rb
    roots = {}
    for x in list(parent):
        roots[f(x)] = roots.get(f(x), 0) + 1
    return list(roots.values())


STAGE_KEYS = ["quarry", "dress", "transport", "build", "lift", "setup", "track", "walk"]


def spread(x):
    """v16: spread of a per-seed quantity across seeds: mean, sd (sample, ddof=1; 0 for one seed), min, max, p5, p95
    (numpy linear percentiles)."""
    x = np.asarray(x, dtype=float)
    return {"mean": float(x.mean()), "sd": float(x.std(ddof=1)) if x.size > 1 else 0.0, "min": float(x.min()),
            "max": float(x.max()), "p5": float(np.percentile(x, 5)), "p95": float(np.percentile(x, 95))}


def island_years_q(sites, q=95.0):
    """v16 L5 (addendum 4): per seed, the sum over cohorts of the q-th percentile site finish in seasons from the cohort
    start (finish_season - cohort start season + 1). q = 100 (the max) gives the island years (max finish_season) of a
    phased run, since each cohort starts the season after the previous one finished. Unphased runs (no 'phase' column):
    one cohort starting in season 1. S10 / S11 unit cohorts: a site counts in the cohort of its last unit
    (phase_add if set), the cohort start = the earliest start_season of the sites whose first unit is in it (else the
    season after the previous cohort's last finish). Returns a Series indexed by seed."""
    out = {}
    for s, d in sites.groupby("seed"):
        if "phase" not in d.columns:
            out[s] = float(np.percentile(d.finish_season.to_numpy(), q))
            continue
        ph = d.phase.to_numpy()
        last = np.where(d.phase_add.to_numpy() >= 0, d.phase_add.to_numpy(), ph) if "phase_add" in d.columns else ph
        tot, prev_end = 0.0, 0
        for k in sorted(set(last.tolist())):
            fin = d.finish_season.to_numpy()[last == k]
            st0 = d.start_season.to_numpy()[ph == k]
            start = int(st0.min()) if st0.size else prev_end + 1
            tot += float(np.percentile(fin - start + 1, q))
            prev_end = int(fin.max())
        out[s] = tot
    return pd.Series(out)


def write_scenario(cfg, S, haul, run_dir, seeds, out_dir, name, write_shp=True):
    os.makedirs(out_dir, exist_ok=True)
    H = float(cfg["hours_per_day"])
    crs = cfg["crs"]
    sites = read_parts(run_dir, seeds, "sites")
    sites["UID"] = haul.UID.to_numpy()[sites.gid.to_numpy()]
    cols = ["seed", "UID", "TWR_N", "mh_total", "mh_own", "mh_received", "mh_given", "mh_quarry", "mh_dress",
            "mh_transport", "mh_build", "mh_lift", "mh_setup", "mh_track", "mh_walk", "builders", "defector",
            "start_season", "finish_season", "years", "days", "tonnes"]
    sites = sites.sort_values(["seed", "gid"])
    sites[cols].to_csv(os.path.join(out_dir, "nuraghe_manhours_runs.csv.gz"), index=False, float_format="%.4f",
                       compression={"method": "gzip", "mtime": 0})
    g = sites.groupby("gid")
    summ = pd.DataFrame({
        "mh_mean": g.mh_total.mean(), "mh_min": g.mh_total.min(), "mh_max": g.mh_total.max(), "mh_sd": g.mh_total.std(ddof=1),
        "own_mean": g.mh_own.mean(), "rcv_mean": g.mh_received.mean(), "giv_mean": g.mh_given.mean(),
        "days_mean": g.days.mean(), "days_min": g.days.min(), "days_max": g.days.max(),
        "years_mean": g.years.mean(), "builders_mean": g.builders.mean(), "defector_frac": g.defector.mean(),
        "tr_mean": g.mh_transport.mean(), "qua_mean": g.mh_quarry.mean(), "dre_mean": g.mh_dress.mean(),
        "bld_mean": g.mh_build.mean(), "lift_mean": g.mh_lift.mean()})
    h = haul.reset_index(drop=True)
    meta = gpd.read_file(cfg["paths"]["sites"])[["UID", "NAME", "COMUNE", "TWR_FILL"]]
    summ = h[["UID", "TWR_N", "x", "y", "haul_m"]].join(summ).merge(meta, on="UID", how="left")
    summ.to_csv(os.path.join(out_dir, "nuraghe_manhours_summary.csv"), index=False, float_format="%.3f")
    if write_shp:
        shp = summ.rename(columns={"mh_mean": "MH_MEAN", "mh_min": "MH_MIN", "mh_max": "MH_MAX", "mh_sd": "MH_SD",
                                   "own_mean": "OWN_MH", "rcv_mean": "RCV_MH", "giv_mean": "GIV_MH",
                                   "days_mean": "DAY_MEAN", "days_min": "DAY_MIN", "days_max": "DAY_MAX",
                                   "years_mean": "YEARS", "builders_mean": "BLD_MEAN", "defector_frac": "DEFECT",
                                   "tr_mean": "MH_TRA", "qua_mean": "MH_QUA", "dre_mean": "MH_DRE", "bld_mean": "MH_BLD",
                                   "lift_mean": "MH_LIFT", "haul_m": "HAUL_M"})
        gdf = gpd.GeoDataFrame(shp.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(shp.x, shp.y), crs=crs)
        assert all(len(c) <= 10 for c in gdf.columns)
        gdf.to_file(os.path.join(out_dir, "nuraghe_manhours.shp"), engine="pyogrio", encoding="UTF-8")
    # alliances
    pairs = read_parts(run_dir, seeds, "pairs")
    if len(pairs) and "ask_only" in pairs.columns:           # rows known only from asks: no help, no trust change
        pairs = pairs[pairs.ask_only == 0]
    ns = len(seeds)
    n_all, sizes = [], []
    if len(pairs):
        for s, d in pairs[pairs.allied == 1].groupby("seed"):
            n_all.append(len(d))
            sizes += components(zip(d.a, d.b))
        agg = pairs.groupby(["a", "b"]).agg(trust=("trust_ab", "mean"), trust_ba=("trust_ba", "mean"),
                                           help_ab=("help_ab", "sum"), help_ba=("help_ba", "sum"),
                                           allied=("allied", "sum")).reset_index()
        agg["help_mh"] = (agg.help_ab + agg.help_ba) / ns
        agg["frac_all"] = agg.allied / ns
        agg["trust"] = (agg.trust + agg.trust_ba) / 2
        al = agg[agg.frac_all > 0]
        if write_shp and len(al):
            geom = [LineString([tuple(S.xy[a]), tuple(S.xy[b])]) for a, b in zip(al.a, al.b)]
            gl = gpd.GeoDataFrame({"UID_A": h.UID.to_numpy()[al.a], "UID_B": h.UID.to_numpy()[al.b],
                                   "TRUST": al.trust.round(4), "HELP_MH": al.help_mh.round(2),
                                   "FRAC_ALL": al.frac_all.round(4)}, geometry=geom, crs=crs)
            gl.to_file(os.path.join(out_dir, "alliances.shp"), engine="pyogrio", encoding="UTF-8")
    T = S.T
    ho = read_parts(run_dir, seeds, "handoffs")
    if write_shp and len(ho):
        hh = ho.groupby(["col", "row"]).uses.sum().reset_index()
        gh = gpd.GeoDataFrame({"USES": hh.uses, "USES_SEED": (hh.uses / ns).round(4)},
                              geometry=gpd.points_from_xy(T[2] + (hh.col + 0.5) * T[0], T[5] + (hh.row + 0.5) * T[4]), crs=crs)
        gh.to_file(os.path.join(out_dir, "handoffs.shp"), engine="pyogrio", encoding="UTF-8")
    tr = read_parts(run_dir, seeds, "tracks")
    n_track_cells = 0
    if len(tr):
        tt = tr.groupby(["col", "row"]).agg(uses=("uses", "sum"), built=("seed", "nunique")).reset_index()
        n_track_cells = len(tr) / ns
        if write_shp:
            import rasterio
            from rasterio.transform import Affine
            arr = np.zeros((2, S.H, S.W), np.float32)
            arr[0, tt.row, tt.col] = tt.uses / ns
            arr[1, tt.row, tt.col] = tt.built / ns
            with rasterio.open(os.path.join(out_dir, "tracks_uses.tif"), "w", driver="GTiff", height=S.H, width=S.W,
                               count=2, dtype="float32", crs=crs, transform=Affine(*T), nodata=0,
                               compress="deflate", tiled=True) as w:
                w.write(arr)
                w.set_band_description(1, "track uses per seed (towers whose route used the cell with access)")
                w.set_band_description(2, "fraction of seeds in which the cell carries a track")
            del arr
    # strategy by season
    lg = read_parts(run_dir, seeds, "strategy")
    if len(lg):
        lg["season_bin"] = (lg.season - 1) // SEASON_BIN * SEASON_BIN + 1
        rows = []
        for sb, d in lg.groupby("season_bin"):
            r = {"season_from": sb, "season_to": sb + SEASON_BIN - 1, "towers_started": len(d) / ns,
                 "face0_share": (d.quarry_face == 0).mean(), "req_quarry": d.req_quarry.mean(),
                 "req_dress": d.req_dress.mean(), "req_build": d.req_build.mean(), "relay_any": (d.relay > 0).mean(),
                 "relay_mean_frac": d.relay.mean(), "track": d.track.mean(), "imitated": d.imitated.mean()}
            for f in (0.25, 0.5, 0.75):
                r[f"relay_{f}"] = (d.relay == f).mean()
            rows.append(r)
        pd.DataFrame(rows).to_csv(os.path.join(out_dir, "strategy_by_season.csv"), index=False, float_format="%.4f")
    # specialisation
    sp = read_parts(run_dir, seeds, "spec")
    gs = [c for c in sp.columns if c.startswith("given_")]
    spm = sp.groupby("gid")[gs + [c for c in sp.columns if c.startswith("skill_") or c.startswith("cum_")] + ["defector"]].mean()
    tot = spm[gs].sum(axis=1)
    for c in gs:
        spm["share_" + c[6:]] = np.where(tot > 0, spm[c] / tot.replace(0, np.nan), 0.0)
    spm.insert(0, "UID", h.UID.to_numpy()[spm.index])
    spm.to_csv(os.path.join(out_dir, "specialisation.csv"), float_format="%.4f")
    # stats
    pr = sites.groupby("seed").mh_total.sum()
    isl = sites.groupby("seed").finish_season.max()
    tot = sites.mh_total.sum()
    st = {"scenario": name, "seeds_run": ns, "island_mh_mean": pr.mean(), "island_mh_min": pr.min(),
          "island_mh_max": pr.max()}
    for k in ["quarry", "dress", "transport", "build", "lift", "setup", "track", "walk"]:
        st["share_" + k] = sites["mh_" + k].sum() / tot
    st["share_received"] = sites.mh_received.sum() / tot
    for tw in (1, 2, 3):
        st[f"median_mh_twr{tw}"] = float(summ[summ.TWR_N == tw].mh_mean.median())
    st["pct_sites_over_30k"] = 100.0 * float((summ.mh_mean > cfg["lit_scenarios"]["community_threshold_ph"]).mean())
    st["island_seasons_mean"] = isl.mean(); st["island_seasons_min"] = int(isl.min()); st["island_seasons_max"] = int(isl.max())
    st["median_years_twr1"] = float(summ[summ.TWR_N == 1].years_mean.median())
    st["n_alliances_mean"] = float(np.sum(n_all) / ns) if n_all else 0.0
    st["mean_alliance_size"] = float(np.mean(sizes)) if sizes else 0.0
    st["max_alliance_size"] = int(np.max(sizes)) if sizes else 0
    st["track_cells_mean"] = n_track_cells
    st["relay_share_towers"] = float((lg.relay > 0).mean()) if len(lg) else 0.0
    # v16 S1: relays chosen (strategy) vs relays made (hand-off executed); relay_share_towers above = the old name of
    # relay_share_chosen, kept as an alias so existing readers keep working
    st["relay_share_chosen"] = st["relay_share_towers"]
    st["relay_share_made"] = float(lg.relay_made.mean()) if (len(lg) and "relay_made" in lg.columns) else float("nan")
    # v16 spread across seeds (existing keys unchanged; new keys added): island years (= island seasons), the L5
    # island_years_p95, total man-hours and man-hours by stage
    # L5 (project team 5 Nov, replaces the per-cohort sum, which breaks when cohorts overlap): island_years_p95 = the
    # island-wide 95th percentile of the site finish seasons (numpy linear); the per-cohort sum is kept as
    # island_years_p95_cohortsum for the record
    by = pd.DataFrame({"island_seasons": isl,
                       "island_years_p95": sites.groupby("seed").finish_season.quantile(0.95),
                       "island_years_p95_cohortsum": island_years_q(sites, 95.0), "island_mh": pr})
    for k in STAGE_KEYS:
        by["island_mh_" + k] = sites.groupby("seed")["mh_" + k].sum()
    by.index.name = "seed"
    by.to_csv(os.path.join(out_dir, "island_by_seed.csv"), float_format="%.4f")
    for c in by.columns:
        for k, v in spread(by[c]).items():
            key = f"{c}_{k}"
            if key not in st:                               # never overwrite an existing key (mean/min/max kept)
                st[key] = v
    pops = sorted(glob.glob(os.path.join(run_dir, "seed_*.population.json")))
    pops = [json.load(open(f)) for f in pops if int(os.path.basename(f)[5:9]) in set(seeds)]
    if pops:                                               # v16 S3: ceiling on all residents of existing communities
        st["ceiling_binding"] = bool(any(p.get("binding") for p in pops))
        st["ceiling_binding_seeds"] = int(sum(bool(p.get("binding")) for p in pops))
        st["total_residents_mean"] = float(np.mean([p["total_residents"] for p in pops]))
        st["total_residents_max"] = float(np.max([p["total_residents"] for p in pops]))
    si = os.path.join(run_dir, "static_info.json")
    if os.path.exists(si):                                 # v16: static choices (rails sites, sea faces, add4 flags)
        st["static_info"] = json.load(open(si))
    d = sites[sites.defector == 1]; c = sites[sites.defector == 0]
    if len(d):
        st["defector_rcv_mh_mean"] = d.mh_received.mean(); st["coop_rcv_mh_mean"] = c.mh_received.mean()
        st["defector_mh_own_mean"] = d.mh_own.mean(); st["coop_mh_own_mean"] = c.mh_own.mean()
        st["defector_given_mh_mean"] = d.mh_given.mean()
        # trust others hold in defectors at the end
        if len(pairs):
            dset = set(sites.loc[sites.defector == 1, ["seed", "gid"]].itertuples(index=False, name=None))
            tin_d, tin_c = [], []
            for r in pairs.itertuples():
                for holder, target, t in ((r.a, r.b, r.trust_ab), (r.b, r.a, r.trust_ba)):
                    (tin_d if (r.seed, target) in dset else tin_c).append(t)
            st["trust_in_defectors"] = float(np.mean(tin_d)) if tin_d else np.nan
            st["trust_in_cooperators"] = float(np.mean(tin_c)) if tin_c else np.nan
    with open(os.path.join(out_dir, "stats.json"), "w") as fh:
        json.dump(st, fh, indent=1, default=float)
    print(f"[alliance {name}] island MH mean {st['island_mh_mean']:,.0f} (min {st['island_mh_min']:,.0f}, max "
          f"{st['island_mh_max']:,.0f}); received {st['share_received']:.1%}; alliances/seed {st['n_alliances_mean']:.1f}, "
          f"mean size {st['mean_alliance_size']:.2f}; island finished in {st['island_seasons_mean']:.1f} seasons", flush=True)
    return st


def write_ties(cfg, haul, info, out_dir, write_shp=True):
    """tie_networks.shp (the pre-existing ties, per stage set) and group_membership.csv."""
    h = haul.reset_index(drop=True)
    xy = h[["x", "y"]].to_numpy()
    rows, geom = [], []
    same = all(np.array_equal(np.asarray(info[s]["edges"]), np.asarray(info["stone"]["edges"])) for s in ("move", "build"))
    for st in (("all",) if same else ("stone", "move", "build")):
        E = info["stone" if st == "all" else st]["edges"]
        for a, b in E:
            rows.append({"STAGE": st, "UID_A": h.UID[a], "UID_B": h.UID[b], "DIST_KM": round(float(np.hypot(*(xy[a] - xy[b]))) / 1000, 3)})
            geom.append(LineString([tuple(xy[a]), tuple(xy[b])]))
    if write_shp and rows:
        gpd.GeoDataFrame(rows, geometry=geom, crs=cfg["crs"]).to_file(os.path.join(out_dir, "tie_networks.shp"),
                                                                     engine="pyogrio", encoding="UTF-8")
    gm = pd.DataFrame({"UID": h.UID, "TWR_N": h.TWR_N})
    for st in ("stone", "move", "build"):
        lab = np.asarray(info[st]["groups"])
        gm[f"group_{st}"] = lab
        sz = pd.Series(lab).map(pd.Series(lab).value_counts()).to_numpy()
        gm[f"group_size_{st}"] = np.where(lab >= 0, sz, 0)
        gm[f"hub_{st}"] = [int(i in info[st]["hubs"]) for i in range(len(h))]
        deg = np.zeros(len(h), int)
        for a, b in info[st]["edges"]:
            deg[a] += 1; deg[b] += 1
        gm[f"ties_{st}"] = deg
    gm.to_csv(os.path.join(out_dir, "group_membership.csv"), index=False)
    return gm


def _definition(cfg, n):
    """NEW-6: a scenario's definition for field_lookup.csv: alliance.list, else alliance_extra (MOST_REALISTIC...), else
    the resolved scenario (alliance.scenario: phased _P10/_P20, _sea, SENS_ and pre-network P_/PS_ names), else {}."""
    if n in cfg["alliance"]["list"]:
        return cfg["alliance"]["list"][n] or {}
    if n in cfg.get("alliance_extra", {}):
        return cfg["alliance_extra"][n] or {}
    try:
        import alliance
        sc = alliance.scenario(cfg, n)
        return {k: v for k, v in sc.items() if k != "name"}
    except Exception as ex:                       # unknown name: keep the comparison, flag the definition
        return {"definition": f"unknown ({type(ex).__name__}: {ex})"}


def _fields(names):
    """Shapefile fields MH_<abbr> (<= 10 chars). alliance.list names keep their ABBR (unchanged); other names use their
    first 7 characters, made unique with a 2-digit suffix when two would collide (NEW-6: e.g. MOST_REALISTIC_P10 and
    MOST_REALISTIC_alone_P10 both gave MH_MOST_RE, and the merge's _x/_y suffixes broke the 10-character limit)."""
    out, used = [], set()
    for k, n in enumerate(names):
        f = "MH_" + ABBR.get(n, n[:7])
        if f in used:
            f = "MH_" + n[:5] + f"{k:02d}"
        used.add(f); out.append(f)
    return out


def compare(cfg, names, root=None, quiet=False):
    root = root or os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance")
    rows, summs = [], {}
    ref = os.path.join(cfg["paths"]["output_dir"], "scenarios_lit", "scenario_comparison_lit.csv")
    if not os.path.exists(ref):                   # BUGFIX_REPORT item 10 (fixed in v12): skip the lit comparison only
        print(f"report_alliance.compare: {ref} is missing (run `model.py CONFIG --lit all` to fill it); "
              "pct_vs_webster left empty, lit comparison skipped", flush=True)
        web_mean = np.nan
    else:
        web = pd.read_csv(ref)
        web_mean = float(web.loc[web.scenario == "webster", "island_mh_mean"].iloc[0])
    for n in names:
        with open(os.path.join(root, n, "stats.json")) as fh:
            rows.append(json.load(fh))
        summs[n] = pd.read_csv(os.path.join(root, n, "nuraghe_manhours_summary.csv"))
    comp = pd.DataFrame(rows)
    a0 = float(comp.loc[comp.scenario == "A0_alone", "island_mh_mean"].iloc[0]) if "A0_alone" in names else np.nan
    comp.insert(5, "pct_vs_A0", 100.0 * (comp.island_mh_mean / a0 - 1.0))
    comp.insert(6, "pct_vs_webster", 100.0 * (comp.island_mh_mean / web_mean - 1.0))
    comp.insert(1, "field", _fields(comp.scenario))
    comp.to_csv(os.path.join(root, "alliance_comparison.csv"), index=False, float_format="%.4f")
    base = summs[names[0]][["UID", "NAME", "COMUNE", "TWR_N", "x", "y"]].copy()
    for n, fld in zip(names, comp.field):
        base = base.merge(summs[n][["UID", "mh_mean", "years_mean"]].rename(
            columns={"mh_mean": fld, "years_mean": fld.replace("MH_", "YR_")}), on="UID")
    gdf = gpd.GeoDataFrame(base.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(base.x, base.y), crs=cfg["crs"])
    assert all(len(c) <= 10 for c in gdf.columns)
    gdf.to_file(os.path.join(root, "nuraghe_manhours_alliance.shp"), engine="pyogrio", encoding="UTF-8")
    lk = comp[["field", "scenario"]].copy()
    lk["years_field"] = lk.field.str.replace("MH_", "YR_", regex=False)
    lk["definition"] = [json.dumps(_definition(cfg, n)) for n in lk.scenario]          # NEW-6
    lk.to_csv(os.path.join(root, "field_lookup.csv"), index=False)
    if not quiet:
        pd.set_option("display.width", 250); pd.set_option("display.max_columns", 80)
        print("\n================ ALLIANCE SCENARIO COMPARISON ================")
        print(comp.drop(columns=["field"]).set_index("scenario").T.to_string())
    return comp


def sensitivity(cfg, names):
    root = os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance")
    a0 = json.load(open(os.path.join(root, "A0_alone", "stats.json")))["island_mh_mean"]
    rows = []
    for n in names:
        st = json.load(open(os.path.join(root, "sensitivity", n, "stats.json")))
        R, b, t = n[5:].split("_")
        rows.append({"scenario": n, "R_m": float(R[1:]), "b": float(b[1:]), "track_cost": float(t[1:]),
                     "seeds_run": st["seeds_run"], "island_mh_mean": st["island_mh_mean"],
                     "island_mh_min": st["island_mh_min"], "island_mh_max": st["island_mh_max"],
                     "pct_vs_A0": 100.0 * (st["island_mh_mean"] / a0 - 1.0), "share_received": st["share_received"],
                     "share_track": st["share_track"], "n_alliances_mean": st["n_alliances_mean"],
                     "mean_alliance_size": st["mean_alliance_size"], "median_mh_twr1": st["median_mh_twr1"],
                     "median_years_twr1": st["median_years_twr1"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(root, "sensitivity", "sensitivity.csv"), index=False, float_format="%.4f")
    print("\n================ ALLIANCE SENSITIVITY (A5_full) ================")
    print(df.drop(columns=["scenario"]).to_string(index=False))
    return df


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
    if "--sensitivity" in sys.argv:
        import alliance
        sensitivity(cfg, alliance.sensitivity_names(cfg))
    else:
        compare(cfg, list(cfg["alliance"]["list"]))
