"""Step 1 - preprocessing (run once, single process).

  python preprocess.py config.yaml

1. Rasterize the allowed quarry-stone outcrops onto the cost grid (stone-type code per cell).
2. One multi-source FORWARD directional Dijkstra seeded at every allowed outcrop cell:
   least drag cost (flat-metre equivalents) from any outcrop to every cell, the originating
   outcrop cell, and the real path length in metres along the chosen path.
3. Sample at the nuraghi and write cache/sites_haul.csv (+ cache/outcrop_code.tif).
"""
import argparse
import os
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from rasterio import features

from nbcommon import load_config, multi_source_dijkstra, peak_rss_mb, step_lengths


def main(cfg_path, cost_raster=None, stones_arg=None, tag=None):
    """cost_raster / stones_arg / tag: overrides for the literature scenarios (S3 friction, S5b stone rule).
    stones_arg: comma-separated STONE classes, or 'BUILDSTONE' = every class with BUILDSTONE == 1."""
    t0 = time.time()
    cfg = load_config(cfg_path)
    P = cfg["paths"]
    if cost_raster:
        P["cost_raster"] = cost_raster
    stones = list(cfg["allowed_stones"])
    if stones_arg == "BUILDSTONE":
        bs = pyogrio.read_dataframe(P["lithology"], columns=[cfg["lithology_field"], "BUILDSTONE"], read_geometry=False)
        stones = sorted(bs.loc[bs.BUILDSTONE == 1, cfg["lithology_field"]].unique())
    elif stones_arg:
        stones = stones_arg.split(",")
    out_dir = P["cache_dir"] if not tag else os.path.join(P["cache_dir"], "haul")
    os.makedirs(out_dir, exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    print(f"[0] cost raster {os.path.basename(P['cost_raster'])}; quarry stones {stones}; output tag '{tag or ''}'")
    code_of = {s: i + 1 for i, s in enumerate(stones)}

    # ---- cost raster: 8 bands uint8, read band by band into one array (~350 MB)
    with rasterio.open(P["cost_raster"]) as r:
        H, W, T, crs = r.height, r.width, r.transform, r.crs
        assert r.count == 8 and r.dtypes[0] in ("uint8", "uint16"), "expected 8 uint8/uint16 bands"
        assert abs(T.a) == abs(T.e), "square cells expected"
        res = abs(T.a)
        cost = np.empty((8, H, W), r.dtypes[0])
        for k in range(8):
            r.read(k + 1, out=cost[k])
        nod = r.nodata
    if nod is not None and nod != 0:
        cost[cost == nod] = 0
    print(f"[1] cost raster {W}x{H} @ {res:.0f} m, 8 bands; nodata 0 = impassable. RSS {peak_rss_mb():.0f} MB")

    # ---- allowed outcrops -> code raster
    fld = cfg["lithology_field"]
    where = f"{fld} IN (" + ",".join("'" + s.replace("'", "''") + "'" for s in stones) + ")"
    lith = pyogrio.read_dataframe(P["lithology"], columns=[fld], where=where)
    if lith.crs is not None and lith.crs.to_epsg() != crs.to_epsg():
        lith = lith.to_crs(crs)
    allv = pyogrio.read_dataframe(P["lithology"], columns=[fld], read_geometry=False)[fld].value_counts()
    print("[2] lithology polygons per STONE class (allowed marked *):")
    for s, n in allv.items():
        print(f"      {'*' if s in code_of else ' '} {s:18s} {n}")
    assert set(lith[fld].unique()) <= set(stones)
    shapes = ((g, code_of[s]) for g, s in zip(lith.geometry, lith[fld]))
    code = features.rasterize(shapes, out_shape=(H, W), transform=T, fill=0, dtype="uint8",
                              all_touched=bool(cfg.get("rasterize_all_touched", False)))
    del lith
    for s in stones:
        print(f"      {s:18s} cells {int((code == code_of[s]).sum()):>10,d}")
    valid = cost.any(axis=0)
    seeds = np.flatnonzero(code.ravel() > 0).astype(np.int64)
    print(f"    allowed outcrop cells (Dijkstra seeds): {seeds.size:,d}  "
          f"(of which on nodata: {int((~valid.ravel()[seeds]).sum()):,d})")
    with rasterio.open(os.path.join(out_dir, f"outcrop_code{suffix}.tif"), "w", driver="GTiff", height=H, width=W, count=1,
                       dtype="uint8", crs=crs, transform=T, nodata=0, compress="deflate", tiled=True) as w:
        w.write(code, 1)
        w.update_tags(codes=";".join(f"{v}={k}" for k, v in code_of.items()))

    # ---- multi-source Dijkstra
    N = H * W
    dist = np.empty(N, np.float32)
    origin = np.empty(N, np.int32)
    plen = np.empty(N, np.float32)
    t1 = time.time()
    settled = multi_source_dijkstra(cost, seeds, step_lengths(res), dist, origin, plen)
    print(f"[3] multi-source Dijkstra: {settled:,d} cells settled in {time.time() - t1:.1f} s; "
          f"peak RSS {peak_rss_mb():.0f} MB")

    # ---- sample at sites
    f = cfg["site_fields"]
    sites = gpd.read_file(P["sites"])
    if sites.crs.to_epsg() != crs.to_epsg():
        sites = sites.to_crs(crs)
    x = sites.geometry.x.to_numpy(); y = sites.geometry.y.to_numpy()
    col = np.floor((x - T.c) / T.a).astype(np.int64)
    row = np.floor((y - T.f) / T.e).astype(np.int64)
    inside = (row >= 0) & (row < H) & (col >= 0) & (col < W)
    assert inside.all(), "site outside the cost raster"
    R = int(cfg["nodata_snap_radius_cells"])
    status, srow, scol, snapd = [], row.copy(), col.copy(), np.zeros(len(sites))
    for i in range(len(sites)):
        r0, c0 = row[i], col[i]
        idx = r0 * W + c0
        if np.isfinite(dist[idx]):
            status.append("ok"); continue
        why = "nodata" if not valid[r0, c0] else "unreachable"
        ra, rb, ca, cb = max(0, r0 - R), min(H, r0 + R + 1), max(0, c0 - R), min(W, c0 + R + 1)
        sub = dist.reshape(H, W)[ra:rb, ca:cb]
        rr, cc = np.nonzero(np.isfinite(sub))
        if rr.size == 0:
            status.append(why + "_nosnap"); continue
        dd = np.hypot(rr + ra - r0, cc + ca - c0)
        j = int(np.argmin(dd))        # nearest by cell-centre distance (ties: first in row order)
        srow[i], scol[i], snapd[i] = rr[j] + ra, cc[j] + ca, dd[j] * res
        status.append("snapped_" + why)
    status = np.array(status)
    sidx = srow * W + scol
    hf = dist[sidx].astype(np.float64)
    hm = plen[sidx].astype(np.float64)
    org = origin[sidx]
    ok = org >= 0
    qr = np.where(ok, org // W, -1); qc = np.where(ok, org % W, -1)
    qx = np.where(ok, T.c + (qc + 0.5) * T.a, np.nan)
    qy = np.where(ok, T.f + (qr + 0.5) * T.e, np.nan)
    qcode = np.where(ok, code.ravel()[np.maximum(org, 0)], 0)
    names = np.array(["none"] + stones)
    on_out = code[srow, scol] > 0                                 # N5: the snapped cell (= row/col when ok)
    out = pd.DataFrame({
        "UID": sites[f["uid"]], "x": x, "y": y, "TWR_N": sites[f["towers"]].astype(int),
        "haul_flatm": np.where(ok, hf, np.nan), "haul_m": np.where(ok, hm, np.nan),
        "quarry_x": qx, "quarry_y": qy, "quarry_stone": names[qcode], "on_outcrop": on_out,
        "row": row, "col": col, "snap_status": status, "snap_dist_m": snapd,
        "quarry_row": qr, "quarry_col": qc,
    })
    # ---- sites with no allowed outcrop reachable over land (e.g. an offshore island)
    policy = cfg.get("unreachable_policy", "local_min_haul")
    unr = out.haul_flatm.isna().to_numpy()
    out["haul_flag"] = np.where(unr, "unreachable", np.where(status == "ok", "ok", status))
    if unr.any() and policy == "local_min_haul":
        out.loc[unr, ["haul_flatm", "haul_m"]] = 0.0          # the model then applies min_haul_flatm
        out.loc[unr, "quarry_x"] = out.loc[unr, "x"]; out.loc[unr, "quarry_y"] = out.loc[unr, "y"]
        out.loc[unr, "quarry_stone"] = "local_unlisted"
        out.loc[unr, "haul_flag"] = "unreachable_local"
    elif unr.any() and policy != "exclude":
        raise ValueError(f"unknown unreachable_policy {policy}")
    out_csv = os.path.join(out_dir, f"sites_haul{suffix}.csv")
    out.to_csv(out_csv, index=False)
    print(f"[4] wrote {out_csv} ({len(out)} sites)")
    vc = pd.Series(status).value_counts()
    print("    site status:", dict(vc))
    print(f"    unreachable (inf) at own cell: {int((status != 'ok').sum())}; "
          f"still unreachable after snapping: {int((~ok).sum())} "
          f"-> policy '{policy}': {', '.join(out.UID[unr])}")
    print(f"    on an allowed outcrop: {int(on_out.sum())}")
    print(f"    haul_flatm  median {np.nanmedian(out.haul_flatm):.0f}, mean {np.nanmean(out.haul_flatm):.0f}, "
          f"max {np.nanmax(out.haul_flatm):.0f}")
    print(f"    haul_m      median {np.nanmedian(out.haul_m):.0f}, mean {np.nanmean(out.haul_m):.0f}, "
          f"max {np.nanmax(out.haul_m):.0f}")
    print(f"    total {time.time() - t0:.0f} s, peak RSS {peak_rss_mb():.0f} MB")


# ----------------------------------------------------------------------------------- stone rules (hybrid / stones7 / stones4)
def materiale_sets(cfg, uids):
    """Per site: the recorded STONE-class set from the `materiale` field of Nurnet's data (site building stone) (None = not recorded / unmapped), plus the
    mapping table of every distinct value (for output/materiale_mapping.csv)."""
    M = cfg["materiale"]
    path = M["file"] if os.path.isabs(M["file"]) else os.path.join(cfg["data_dir"], M["file"])
    d = pd.read_csv(path)
    mp = M["map"]
    def parse(v):
        if not isinstance(v, str) or not v.strip():
            return None, []
        toks = [t.strip() for part in v.replace(" e ", ",").split(",") for t in [part] if t.strip()]
        cls, used = [], []
        for t in toks:
            if t in mp:
                cls += mp[t]; used.append(t)
        return (tuple(sorted(set(cls))) if cls else None), toks
    table = []
    for v, n in d.sa_materiale.fillna("").value_counts().items():
        cl, toks = parse(v)
        table.append({"sa_materiale": v if v else "<empty>", "records_in_file": int(n), "tokens": " | ".join(toks),
                      "stone_classes": "; ".join(cl) if cl else "", "rule": "recorded" if cl else "fallback (7-stone)"})
    table = pd.DataFrame(table)
    by_uid = dict(zip(d.codice, d.sa_materiale))
    sets = [parse(by_uid.get(u))[0] for u in uids]
    vals = [by_uid.get(u) if isinstance(by_uid.get(u), str) and by_uid.get(u) else "<empty>" for u in uids]
    return sets, vals, table


def run_rule(cfg, rule, cost_raster=None, tag=None):
    """Hauls under a stone rule. hybrid: recorded stone first (cheapest outcrop of its classes), else the 7-stone
    list; stones7 / stones4: the fixed lists. One multi-source Dijkstra per distinct class set."""
    t0 = time.time()
    P = cfg["paths"]
    if cost_raster:
        P["cost_raster"] = cost_raster
    out_dir = P["cache_dir"] if not tag else os.path.join(P["cache_dir"], "haul")
    os.makedirs(out_dir, exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    with rasterio.open(P["cost_raster"]) as r:
        H, W, T, crs = r.height, r.width, r.transform, r.crs
        res = abs(T.a)
        cost = np.empty((8, H, W), r.dtypes[0])
        for k in range(8):
            r.read(k + 1, out=cost[k])
    fld = cfg["lithology_field"]
    bs = pyogrio.read_dataframe(P["lithology"], columns=[fld, "BUILDSTONE"])
    if bs.crs is not None and bs.crs.to_epsg() != crs.to_epsg():        # B8: same CRS handling as main()
        bs = bs.to_crs(crs)
    classes = sorted(bs.loc[bs.BUILDSTONE == 1, fld].unique())
    code_of = {c: i + 1 for i, c in enumerate(classes)}
    lith = bs[bs.BUILDSTONE == 1]
    code = features.rasterize(((g, code_of[c]) for g, c in zip(lith.geometry, lith[fld])), out_shape=(H, W), transform=T,
                              fill=0, dtype="uint8", all_touched=bool(cfg.get("rasterize_all_touched", False)))
    del lith, bs
    with rasterio.open(os.path.join(out_dir, f"outcrop_code{suffix}.tif"), "w", driver="GTiff", height=H, width=W, count=1,
                       dtype="uint8", crs=crs, transform=T, nodata=0, compress="deflate", tiled=True) as w:
        w.write(code, 1)
        w.update_tags(codes=";".join(f"{v}={k}" for k, v in code_of.items()), rule=rule)
    f = cfg["site_fields"]
    sites = gpd.read_file(P["sites"])
    if sites.crs.to_epsg() != crs.to_epsg():                             # B8: sample in the raster CRS, as main()
        sites = sites.to_crs(crs)
    x = sites.geometry.x.to_numpy(); y = sites.geometry.y.to_numpy()
    col = np.floor((x - T.c) / T.a).astype(np.int64); row = np.floor((y - T.f) / T.e).astype(np.int64)
    assert ((row >= 0) & (row < H) & (col >= 0) & (col < W)).all(), "site outside the cost raster"
    uids = sites[f["uid"]].to_numpy()
    base = tuple(sorted(cfg["stones4"] if rule == "stones4" else cfg["allowed_stones"]))
    if rule == "hybrid":
        rec, vals, table = materiale_sets(cfg, uids)
        if not tag:
            table.to_csv(os.path.join(cfg["paths"]["output_dir"], "materiale_mapping.csv"), index=False)
    else:
        rec, vals = [None] * len(uids), ["<not used>"] * len(uids)
    want = [s_ if s_ is not None else base for s_ in rec]
    valid = cost.any(axis=0)
    R = int(cfg["nodata_snap_radius_cells"])
    N = H * W
    dist = np.empty(N, np.float32); origin = np.empty(N, np.int32); plen = np.empty(N, np.float32)
    res_h = np.full(len(uids), np.nan); res_m = np.full(len(uids), np.nan); res_o = np.full(len(uids), -1, np.int64)
    res_s = np.array(["ok"] * len(uids), dtype=object); res_r = np.full(len(uids), -1, np.int64); res_c = np.full(len(uids), -1, np.int64)
    res_d = np.zeros(len(uids))                                          # B8: actual snap distance (m)

    def sample(idx):
        for i in idx:
            r0, c0 = row[i], col[i]
            if np.isfinite(dist[r0 * W + c0]):
                rr_, cc_, st = r0, c0, "ok"
            else:
                why = "nodata" if not valid[r0, c0] else "unreachable"
                ra, rb, ca, cb = max(0, r0 - R), min(H, r0 + R + 1), max(0, c0 - R), min(W, c0 + R + 1)
                sub = dist.reshape(H, W)[ra:rb, ca:cb]
                rr, cc = np.nonzero(np.isfinite(sub))
                if rr.size == 0:
                    res_s[i] = why + "_nosnap"; continue
                dd = np.hypot(rr + ra - r0, cc + ca - c0)
                j = int(np.argmin(dd))
                rr_, cc_, st = rr[j] + ra, cc[j] + ca, "snapped_" + why
            k = rr_ * W + cc_
            res_h[i], res_m[i], res_o[i], res_s[i], res_r[i], res_c[i] = dist[k], plen[k], origin[k], st, rr_, cc_
            res_d[i] = 0.0 if st == "ok" else dd[j] * res
    sets = sorted(set(want) | {base}, key=lambda z: (len(z), z))
    print(f"[rule {rule}] {len(sets)} distinct stone-class sets; cost raster {os.path.basename(P['cost_raster'])}", flush=True)
    for cs in sets:
        idx = [i for i, w_ in enumerate(want) if w_ == cs]
        if not idx and cs != base:
            continue
        seeds = np.flatnonzero(np.isin(code.ravel(), [code_of[c] for c in cs if c in code_of])).astype(np.int64)
        multi_source_dijkstra(cost, seeds, step_lengths(res), dist, origin, plen)
        sample(idx)
        if cs == base:
            base_dist = (dist.copy(), origin.copy(), plen.copy())
        print(f"   set {'; '.join(cs)}: {len(idx)} sites, {seeds.size:,} seed cells", flush=True)
    # recorded stone with no reachable outcrop of its classes -> 7-stone fallback (flagged)
    qsrc = np.array(["recorded" if s_ is not None else "fallback" for s_ in rec], dtype=object)
    bad = [i for i in range(len(uids)) if rec[i] is not None and res_o[i] < 0]
    if bad:
        dist[:], origin[:], plen[:] = base_dist
        sample(bad)
        qsrc[bad] = "recorded_unreachable_fallback"
    ok = res_o >= 0
    qr = np.where(ok, res_o // W, -1); qc = np.where(ok, res_o % W, -1)
    names = np.array(["none"] + classes)
    qcode = np.where(ok, code.ravel()[np.maximum(res_o, 0)], 0)
    sr = np.where(res_r >= 0, res_r, row); sc_ = np.where(res_c >= 0, res_c, col)   # N5: snapped cell (nosnap: original)
    on_out = np.array([code[sr[i], sc_[i]] > 0 and names[code[sr[i], sc_[i]]] in want[i] for i in range(len(uids))])
    out = pd.DataFrame({"UID": uids, "x": x, "y": y, "TWR_N": sites[f["towers"]].astype(int),
                        "haul_flatm": np.where(ok, res_h, np.nan), "haul_m": np.where(ok, res_m, np.nan),
                        "quarry_x": np.where(ok, T.c + (qc + 0.5) * T.a, np.nan), "quarry_y": np.where(ok, T.f + (qr + 0.5) * T.e, np.nan),
                        "quarry_stone": names[qcode], "on_outcrop": on_out, "row": row, "col": col, "snap_status": res_s,
                        "snap_dist_m": res_d, "quarry_row": qr, "quarry_col": qc, "Q_SRC": qsrc})
    unr = out.haul_flatm.isna().to_numpy()
    out["haul_flag"] = np.where(unr, "unreachable", np.where(res_s == "ok", "ok", res_s))
    if unr.any():
        out.loc[unr, ["haul_flatm", "haul_m"]] = 0.0
        out.loc[unr, "quarry_x"] = out.loc[unr, "x"]; out.loc[unr, "quarry_y"] = out.loc[unr, "y"]
        out.loc[unr, "quarry_stone"] = "local_unlisted"; out.loc[unr, "haul_flag"] = "unreachable_local"
    out.to_csv(os.path.join(out_dir, f"sites_haul{suffix}.csv"), index=False)
    # per-site class sets (cache only: model input for k-best / far-quarry searches; not an output)
    pd.DataFrame({"UID": uids, "stone_set": ["; ".join(w_) if res_o[i] >= 0 and qsrc[i] != "recorded_unreachable_fallback"
                                             else "; ".join(base) for i, w_ in enumerate(want)], "Q_SRC": qsrc}).to_csv(
        os.path.join(out_dir, f"site_stone_sets{suffix}.csv"), index=False)
    vc = pd.Series(qsrc).value_counts()
    print(f"[4] wrote {out_dir}/sites_haul{suffix}.csv; Q_SRC {dict(vc)}; unreachable after all rules {int(unr.sum())}")
    if rule == "hybrid":
        by = pd.DataFrame({"value": vals, "q": qsrc}).groupby(["value", "q"]).size().unstack(fill_value=0)
        by.to_csv(os.path.join(out_dir, f"materiale_use{suffix}.csv"))
    print(f"    haul_flatm median {np.nanmedian(out.haul_flatm):.0f}, mean {np.nanmean(out.haul_flatm):.0f}; "
          f"haul_m mean {np.nanmean(out.haul_m):.0f}; on own-rule outcrop {int(on_out.sum())}; {time.time() - t0:.0f} s, "
          f"peak RSS {peak_rss_mb():.0f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?", default="config.yaml")
    ap.add_argument("--cost-raster", help="override the cost raster (e.g. a rebuilt mu)")
    ap.add_argument("--stones", help="override allowed stones: comma list, or BUILDSTONE")
    ap.add_argument("--tag", help="write cache/haul/sites_haul_<tag>.csv instead of cache/sites_haul.csv")
    ap.add_argument("--rule", help="hybrid | stones7 | stones4 (default: config stone_rule; ignored with --stones)")
    a = ap.parse_args()
    if a.stones:
        main(a.config, a.cost_raster, a.stones, a.tag)
    else:
        cfg0 = load_config(a.config)
        run_rule(cfg0, a.rule or cfg0.get("stone_rule", "stones4"), a.cost_raster, a.tag)
