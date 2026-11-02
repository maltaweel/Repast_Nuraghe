"""S9 sea access: sea-aware haul tables and people travel times (config.yaml -> sea).

  python tools/sea_routes.py config.yaml [--speeds 4,5,6,2]

Stone (per site, per boat speed): transport = min(existing land route [cache/sites_haul.csv],
    quarry -drag-> landing a -boat along the coast-> landing b -drag-> site).
People (per site, per boat speed): travel time to other sites / quarry points = min(walk, walk + boat + walk).

Geometry (all on the 30 m cost grid, EPSG:25832):
  land  = DEM z > 0 (nodata -9999 = sea/outside).  sea = non-land connected to the raster border.
  coast distance of a point = distance to the nearest sea cell (cell centres, KD-tree, exact at 30 m).
  sea routing grid = 3 x 3 blocks of 30 m cells (90 m); a block is water if >= 50% of its cells are sea;
  coastal water band = water blocks within sea.sea_band_m of a land block (EDT). Boats move only inside it
  (8-neighbour, isotropic), so routes hug the coast and never cross open sea.
  landings = coastal land cells (8-neighbour of a sea cell): beach if z <= 10 m and slope < 10 deg;
  hoist if not beach and z <= 5 m (hoist height = z of the cell); otherwise no landing. Each landing attaches
  to the nearest band block within 2 blocks; the cell-to-block distance is added to the sea leg.
Stone chain (3 Dijkstras per stone-class set and speed, all multi-source, with origin tracking):
  1 land: from permitted outcrop cells within sea.coast_band_m of the coast -> every landing cell
  2 sea : seeded at the band blocks of landings a with value stage-1 + transfer + hoist(a)
  3 land: seeded at landings b with value stage-2 + transfer + hoist(b) -> the coastal sites of the set.
  Land legs run on the drag cost raster inside land within sea.land_band_m of the coast; edge weight =
  crew hours of the drag (cost/0.6 m/s) + the walk back over the same move (length/1.4 m/s).
  Sea weight = boat_factor x 2 x length / v_boat (boat out loaded + back empty; boat_factor = crew x pull / payload).
The currency is the model's trip time per crew (hours); hoisting (per block, not per crew) enters the route
choice as hoist_ph_per_block_m x h / mean crew per block; the model charges the exact per-block hoist labour.
Writes cache/sea/: sites_haul_sea{kn}kn.csv, people_sea{kn}kn.csv, landings.csv(.npz), sea_meta.json.
Memory: about 1 GB peak (compact land domain); run single-process.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import rasterio
from numba import njit
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import DIRS, _sift_down, _sift_up, load_config, peak_rss_mb, step_lengths  # noqa: E402

KN = 0.514444  # m/s per knot


def cgmem():
    try:
        an = [int(l.split()[1]) for l in open("/sys/fs/cgroup/memory.stat") if l.startswith("anon ")][0]
        oom = [l.split()[1] for l in open("/sys/fs/cgroup/memory.events") if l.startswith("oom_kill")][0]
        return f"RSS peak {peak_rss_mb():.0f} MB; cgroup anon {an // 1048576} MB; oom_kill {oom}"
    except Exception:
        return f"RSS peak {peak_rss_mb():.0f} MB"


# ----------------------------------------------------------------------------------- compact-graph Dijkstra
@njit(cache=True)
def dijkstra(flat, idx, cost_c, H, W, steplen, a_cost, a_len, seeds, seed_val, seed_org, cutoff,
             dist, acc_c, acc_l, org, pos, heap):
    """Multi-source Dijkstra on a compact node set (flat = grid flat index per node, idx = node of a grid cell or -1).
    Edge u -> u + DIRS[k] (cost band k at u, 0 = impassable) weighs a_cost * cost + a_len * steplen[k].
    Seeds may carry different start values (seed_val) and labels (seed_org). Nodes beyond cutoff stay unsettled
    (their tentative values are > cutoff). acc_c / acc_l accumulate the raw band cost and the length along the
    chosen path. Returns the number of settled nodes."""
    dist[:] = np.inf
    acc_c[:] = 0.0
    acc_l[:] = 0.0
    org[:] = -1
    pos[:] = -1
    n = 0
    for i in range(seeds.size):
        s = seeds[i]
        v = np.float32(seed_val[i])
        if v < dist[s]:
            dist[s] = v
            org[s] = seed_org[i]
            if pos[s] == -1:
                heap[n] = s
                pos[s] = n
                n += 1
                _sift_up(heap, pos, dist, n - 1)
            else:
                _sift_up(heap, pos, dist, pos[s])
    settled = 0
    while n > 0:
        u = heap[0]
        if dist[u] > cutoff:
            break
        n -= 1
        if n > 0:
            heap[0] = heap[n]
            pos[heap[0]] = 0
            _sift_down(heap, pos, dist, 0, n)
        pos[u] = -2
        settled += 1
        f = flat[u]
        r = f // W
        c = f - r * W
        du = dist[u]
        for k in range(8):
            w = cost_c[k, u]
            if w == 0:
                continue
            rr = r + DIRS[k, 0]
            cc = c + DIRS[k, 1]
            if rr < 0 or cc < 0 or rr >= H or cc >= W:
                continue
            v = idx[rr * W + cc]
            if v < 0:
                continue
            pv = pos[v]
            if pv == -2:
                continue
            nd = np.float32(du + a_cost * w + a_len * steplen[k])
            if nd < dist[v]:
                dist[v] = nd
                acc_c[v] = acc_c[u] + w
                acc_l[v] = acc_l[u] + steplen[k]
                org[v] = org[u]
                if pv == -1:
                    heap[n] = v
                    pos[v] = n
                    n += 1
                    _sift_up(heap, pos, dist, n - 1)
                else:
                    _sift_up(heap, pos, dist, pv)
    return settled


class Graph:
    """Compact node set + work arrays for repeated Dijkstras."""

    def __init__(self, flat, H, W, cost_c, steplen):
        self.flat = flat.astype(np.int32)
        self.H, self.W = H, W
        self.idx = np.full(H * W, -1, np.int32)
        self.idx[self.flat] = np.arange(flat.size, dtype=np.int32)
        self.cost_c = cost_c
        self.steplen = steplen
        n = flat.size
        self.dist = np.empty(n, np.float32); self.acc_c = np.empty(n, np.float32); self.acc_l = np.empty(n, np.float32)
        self.org = np.empty(n, np.int32); self.pos = np.empty(n, np.int32); self.heap = np.empty(n, np.int32)

    def run(self, a_cost, a_len, seeds, val, org, cutoff):
        o = np.argsort(val, kind="stable")                   # pushing in key order keeps the heap shallow
        return dijkstra(self.flat, self.idx, self.cost_c, self.H, self.W, self.steplen, float(a_cost), float(a_len),
                        seeds[o].astype(np.int64), val[o].astype(np.float64), org[o].astype(np.int32),
                        float(cutoff), self.dist, self.acc_c, self.acc_l, self.org, self.pos, self.heap)


# ----------------------------------------------------------------------------------- parameters
def sea_params(cfg):
    """All S9 parameters (config sea:, transport:, lit_scenarios:), with derived values."""
    S = dict(cfg["sea"])
    tp = cfg["transport"]
    L = cfg["lit_scenarios"]
    S["v_drag"] = float(tp["drag_speed_ms"]); S["v_back"] = float(tp["return_walk_ms"])
    S["lu_h"] = float(tp["load_unload_h"]); S["min_haul"] = float(tp["min_haul_flatm"]); S["pull"] = float(tp["pull_kg_per_person"])
    S["transfer_h"] = float(S.get("transfer_h", tp["load_unload_h"]))
    S["boat_factor"] = float(S["crew"]) * S["pull"] / float(S["payload_kg"])
    S["hoist_ph_per_block_m"] = float(L["lever_ph_per_block_course"]) / float(L["geometry"]["course_height_m"])
    # mean crew per block (for the hoist term of the route choice only): E[ceil(m / pull)] of the block draw
    s = cfg["stone"]
    m = np.clip(np.random.default_rng(0).lognormal(np.log(s["block_median_kg"]), s["block_sigma"], 200000),
                s["block_min_kg"], s["block_max_kg"])
    S["mean_crew"] = float(np.ceil(m / S["pull"]).mean())
    S["mean_block_kg"] = float(m.mean())
    return S


def land_trip_h(hf, hm, S):
    return np.maximum(hf, S["min_haul"]) / S["v_drag"] / 3600.0 + np.maximum(hm, S["min_haul"]) / S["v_back"] / 3600.0 + S["lu_h"]


def sea_trip_h(hf1, hm1, hf2, hm2, sea_m, kn, S):
    """Crew trip time of the sea chain (same units as the land trip): two drag legs (each >= min haul) with their
    walks back, transfer at both landings, and the boat leg there and back scaled by the boat factor."""
    v = kn * KN
    return ((np.maximum(hf1, S["min_haul"]) + np.maximum(hf2, S["min_haul"])) / S["v_drag"]
            + (np.maximum(hm1, S["min_haul"]) + np.maximum(hm2, S["min_haul"])) / S["v_back"]) / 3600.0 \
        + 2.0 * S["transfer_h"] + S["boat_factor"] * 2.0 * sea_m / v / 3600.0


def hoist_eq_h(h, S):
    return S["hoist_ph_per_block_m"] * h / S["mean_crew"]


# ----------------------------------------------------------------------------------- main
def main(cfg_path, speeds):
    t0 = time.time()
    cfg = load_config(cfg_path)
    S = sea_params(cfg)
    P = cfg["paths"]
    dd = cfg["data_dir"]
    out = os.path.join(P["cache_dir"], "sea")
    os.makedirs(out, exist_ok=True)
    print(f"[0] {cgmem()}; params: boat_factor {S['boat_factor']:.3f}, hoist {S['hoist_ph_per_block_m']:.4f} ph/block/m, "
          f"mean crew/block {S['mean_crew']:.3f}, mean block {S['mean_block_kg']:.0f} kg", flush=True)

    # ---- 1. land / sea masks (30 m)
    with rasterio.open(os.path.join(dd, S["dem"])) as r:
        H, W, T = r.height, r.width, r.transform
        z = r.read(1)
        nod = r.nodata
    res = abs(T.a)
    land = (z > 0) & (z != nod)
    lab, nl = ndimage.label(~land)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    border = border[border > 0]
    sea = np.isin(lab, border)
    del lab
    print(f"[1] grid {W}x{H} @ {res:.0f} m; land cells {int(land.sum()):,}; sea (border-connected) {int(sea.sum()):,}; "
          f"inland non-land {int((~land & ~sea).sum()):,}; {cgmem()}", flush=True)
    # coastal cells: land with an 8-neighbour sea cell; shore sea cells: sea with an 8-neighbour land cell
    sea_nb = ndimage.binary_dilation(sea, structure=np.ones((3, 3), bool))
    coast = land & sea_nb
    del sea_nb
    land_nb = ndimage.binary_dilation(land, structure=np.ones((3, 3), bool))
    shore = sea & land_nb
    del land_nb
    rs, cs = np.nonzero(shore)
    shore_xy = np.column_stack([T.c + (cs + 0.5) * T.a, T.f + (rs + 0.5) * T.e])
    shore_tree = cKDTree(shore_xy)
    del rs, cs, shore

    # ---- 2. sea routing grid (90 m blocks) and coastal water band
    f = int(S["sea_grid_factor"])
    Hc, Wc = -(-H // f), -(-W // f)
    pad = np.ones((Hc * f, Wc * f), bool)
    pad[:H, :W] = sea
    frac = pad.reshape(Hc, f, Wc, f).mean(axis=(1, 3))
    del pad
    water = frac >= 0.5
    resc = res * f
    d_land_c = ndimage.distance_transform_edt(water) * resc       # block centre to nearest land block
    band = water & (d_land_c <= float(S["sea_band_m"]))
    # keep band blocks connected to the main band component (drop isolated ponds)
    bl, nb_ = ndimage.label(band, structure=np.ones((3, 3), bool))
    sizes = np.bincount(bl.ravel())
    sizes[0] = 0
    band = bl == int(np.argmax(sizes))
    del bl
    d_sea_c = ndimage.distance_transform_edt(~water) * resc       # land block to nearest water block (domain mask)
    print(f"[2] sea grid {Wc}x{Hc} @ {resc:.0f} m; water blocks {int(water.sum()):,}; band (<= {S['sea_band_m']} m of land, "
          f"main component) {int(band.sum()):,} blocks; {cgmem()}", flush=True)

    # ---- 3. landings
    with rasterio.open(os.path.join(dd, S["slope"])) as r:
        slope = r.read(1)
    lr, lc = np.nonzero(coast)
    lz = z[lr, lc].astype(np.float64)
    lsl = slope[lr, lc].astype(np.float64)
    del slope
    beach = (lz <= float(S["beach_max_z_m"])) & (lsl < float(S["beach_max_slope_deg"])) & (lsl >= 0)
    hoist = ~beach & (lz <= float(S["hoist_max_z_m"]))
    keep = beach | hoist
    lr, lc, lz, lsl, beach = lr[keep], lc[keep], lz[keep], lsl[keep], beach[keep]
    lx = T.c + (lc + 0.5) * T.a
    ly = T.f + (lr + 0.5) * T.e
    # attach to the nearest band block within attach radius
    R = int(S["attach_radius_blocks"])
    best_d = np.full(lr.size, np.inf)
    best_b = np.full(lr.size, -1, np.int64)
    br0, bc0 = lr // f, lc // f
    for dr in range(-R, R + 1):
        for dc in range(-R, R + 1):
            rr, cc = br0 + dr, bc0 + dc
            ok = (rr >= 0) & (rr < Hc) & (cc >= 0) & (cc < Wc)
            ok[ok] = band[rr[ok], cc[ok]]
            bx = T.c + (cc + 0.5) * resc
            by = T.f - (rr + 0.5) * resc
            d = np.hypot(bx - lx, by - ly)
            better = ok & (d < best_d)
            best_d[better] = d[better]
            best_b[better] = rr[better] * Wc + cc[better]
    att = best_b >= 0
    n_coast = int(coast.sum())
    print(f"[3] coastal land cells {n_coast:,}; landings beach {int(beach.sum()):,}, hoist {int((~beach).sum()):,}; "
          f"attached to the band {int(att.sum()):,} (beach {int((beach & att).sum()):,}, hoist {int((~beach & att).sum()):,})", flush=True)
    lr, lc, lz, lsl, beach, lx, ly = lr[att], lc[att], lz[att], lsl[att], beach[att], lx[att], ly[att]
    l_blk = best_b[att]
    l_att = best_d[att]
    l_h = np.where(beach, 0.0, np.maximum(lz, 0.0))                 # hoist height (m)
    l_flat = (lr.astype(np.int64) * W + lc)
    NL = lr.size
    pd.DataFrame({"lid": np.arange(NL), "x": lx, "y": ly, "row": lr, "col": lc, "z": lz, "slope": lsl,
                  "type": np.where(beach, "beach", "hoist"), "hoist_m": l_h, "block": l_blk, "attach_m": l_att}
                 ).to_csv(os.path.join(out, "landings.csv"), index=False)
    del coast

    # ---- 4. distance to coast: sites and outcrop cells; eligibility
    haul = pd.read_csv(os.path.join(P["cache_dir"], "sites_haul.csv"))
    ss = pd.read_csv(os.path.join(P["cache_dir"], "site_stone_sets.csv"))
    assert (ss.UID.to_numpy() == haul.UID.to_numpy()).all()
    haul["stone_set"] = ss.stone_set.to_numpy()
    haul["d_coast_m"] = shore_tree.query(haul[["x", "y"]].to_numpy())[0]
    band_m = float(S["coast_band_m"])
    elig = (haul.d_coast_m <= band_m).to_numpy()
    with rasterio.open(os.path.join(P["cache_dir"], "outcrop_code.tif")) as r:
        code = r.read(1)
        tags = r.tags().get("codes", "")
    code_of = {v: int(k) for k, v in (t.split("=", 1) for t in tags.split(";") if t)}
    name_of = {v: k for k, v in code_of.items()}
    # candidate outcrop cells: within the coarse band + one block, then exact distance
    near_c = d_sea_c <= band_m + 2 * resc
    qr, qc = np.nonzero((code > 0) & near_c[np.arange(H)[:, None] // f, np.arange(W)[None, :] // f] & land)
    qxy = np.column_stack([T.c + (qc + 0.5) * T.a, T.f + (qr + 0.5) * T.e])
    qd = shore_tree.query(qxy)[0]
    ok = qd <= band_m
    q_flat = qr[ok].astype(np.int64) * W + qc[ok]
    q_code = code[qr[ok], qc[ok]]
    del qr, qc, qxy, qd, near_c
    print(f"[4] sites within {band_m:.0f} m of the coast: {int(elig.sum())} of {len(haul)}; permitted-class outcrop cells "
          f"within {band_m:.0f} m: {q_flat.size:,}; {cgmem()}", flush=True)

    # ---- 5. compact land domain (land within land_band_m of the coast, passable)
    dom_c = d_sea_c <= float(S["land_band_m"])
    with rasterio.open(P["cost_raster"]) as r:
        dom = land & dom_c[np.arange(H)[:, None] // f, np.arange(W)[None, :] // f]
        del dom_c
        flat = np.flatnonzero(dom.ravel()).astype(np.int32)
        del dom
        cost_c = np.empty((8, flat.size), np.uint8)
        for k in range(8):
            cost_c[k] = r.read(k + 1).ravel()[flat]
    del z, land, sea
    pas = cost_c.any(axis=0)
    flat = flat[pas]
    cost_c = np.ascontiguousarray(cost_c[:, pas])
    G = Graph(flat, H, W, cost_c, step_lengths(res))
    del flat, pas
    print(f"[5] land domain (<= {S['land_band_m']} m of the coast, passable): {G.flat.size:,} cells; {cgmem()}", flush=True)
    l_node = G.idx[l_flat]
    s_flat = haul.row.to_numpy().astype(np.int64) * W + haul.col.to_numpy()
    s_node = G.idx[s_flat]
    q_node = G.idx[q_flat]
    print(f"    landings in domain {int((l_node >= 0).sum()):,}/{NL:,}; eligible sites in domain "
          f"{int((s_node[elig] >= 0).sum())}/{int(elig.sum())}; eligible outcrop cells in domain {int((q_node >= 0).sum()):,}", flush=True)
    # sea graph
    b_flat = np.flatnonzero(band.ravel()).astype(np.int32)
    GS = Graph(b_flat, Hc, Wc, np.ones((8, b_flat.size), np.uint8), step_lengths(resc))
    l_bnode = GS.idx[l_blk]
    assert (l_bnode >= 0).all()

    # ---- 6. stone chains per stone-class set and speed
    S_lu = S["transfer_h"]
    a_drag, a_walk = 1.0 / S["v_drag"] / 3600.0, 1.0 / S["v_back"] / 3600.0
    land_h = land_trip_h(haul.haul_flatm.to_numpy(), haul.haul_m.to_numpy(), S)
    res_cols = ["s_cost", "hf1", "hm1", "hf2", "hm2", "sea_m", "la", "lb", "q_flat"]
    R_ = {kn: {c: np.full(len(haul), np.nan) for c in res_cols} for kn in speeds}
    sets = sorted(set(haul.stone_set[elig]))
    hoist_eq = hoist_eq_h(l_h, S)
    for cs_ in sets:
        sites = np.flatnonzero(elig & (haul.stone_set.to_numpy() == cs_) & (s_node >= 0))
        allowed = [code_of[c] for c in cs_.split("; ") if c in code_of]
        qm = np.isin(q_code, allowed) & (q_node >= 0)
        if sites.size == 0 or not qm.any():
            print(f"  set [{cs_}]: {sites.size} eligible sites, {int(qm.sum())} coastal quarry cells -> no sea route", flush=True)
            continue
        cutoff = float(land_h[sites].max())
        t1 = time.time()
        n1 = G.run(a_drag, a_walk, q_node[qm], np.zeros(int(qm.sum())), np.flatnonzero(qm), cutoff)
        # stage-1 values at landings (q index into q_* arrays)
        ln = l_node >= 0
        D1 = np.full(NL, np.inf); hf1 = np.zeros(NL); hm1 = np.zeros(NL); o1 = np.full(NL, -1, np.int64)
        D1[ln] = G.dist[l_node[ln]]; hf1[ln] = G.acc_c[l_node[ln]]; hm1[ln] = G.acc_l[l_node[ln]]; o1[ln] = G.org[l_node[ln]]
        D1[(o1 < 0) | (D1 > cutoff)] = np.inf
        for kn in speeds:
            v = kn * KN
            a_sea = S["boat_factor"] * 2.0 / v / 3600.0
            fin = np.isfinite(D1)
            sv = D1[fin] + S_lu + hoist_eq[fin] + a_sea * l_att[fin]
            n2 = GS.run(0.0, a_sea, l_bnode[fin], sv, np.flatnonzero(fin), cutoff)
            D2 = GS.dist[l_bnode].astype(np.float64)
            o2 = GS.org[l_bnode].astype(np.int64)            # landing a for the block of landing b
            sl2 = GS.acc_l[l_bnode].astype(np.float64)
            okb = (o2 >= 0) & (D2 <= cutoff) & ln
            sv3 = D2[okb] + S_lu + hoist_eq[okb] + a_sea * l_att[okb]
            n3 = G.run(a_drag, a_walk, l_node[okb], sv3, np.flatnonzero(okb), cutoff)
            sn = s_node[sites]
            b = G.org[sn].astype(np.int64)
            got = (b >= 0) & (G.dist[sn] <= cutoff)
            sites_g, b = sites[got], b[got]
            a = o2[b]
            rr = R_[kn]
            rr["lb"][sites_g] = b; rr["la"][sites_g] = a
            rr["hf2"][sites_g] = G.acc_c[sn[got]]; rr["hm2"][sites_g] = G.acc_l[sn[got]]
            rr["hf1"][sites_g] = hf1[a]; rr["hm1"][sites_g] = hm1[a]
            rr["sea_m"][sites_g] = sl2[b] + l_att[a] + l_att[b]
            rr["q_flat"][sites_g] = q_flat[o1[a]]
            rr["s_cost"][sites_g] = G.dist[sn[got]]
            print(f"  set [{cs_}] {kn} kn: {sites.size} eligible sites, {int(qm.sum()):,} quarry cells; settled land {n1:,}/"
                  f"sea {n2:,}/land {n3:,}; sea route found for {int(got.sum())}; {time.time() - t1:.1f} s", flush=True)
    del G
    print(f"[6] stone chains done; {cgmem()}", flush=True)

    # ---- 7. outcrop regions (as tools/kbest_quarries.py) for the alliance's sea faces
    label = np.zeros(code.shape, np.int32)
    nreg = 0
    for c_ in sorted(code_of.values()):
        lab_c, n_c = ndimage.label(code == c_, structure=np.ones((3, 3), bool))
        m_ = lab_c > 0
        label[m_] = lab_c[m_] + nreg
        nreg += n_c
        del lab_c, m_
    lab_flat = label.ravel()
    code_flat = code.ravel()

    # ---- 8. tables per speed
    meta = {"params": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in S.items()},
            "n_landings": int(NL), "n_beach": int(beach.sum()), "n_hoist": int((~beach).sum()),
            "n_eligible_sites": int(elig.sum()), "speeds": speeds}
    for kn in speeds:
        rr = R_[kn]
        h = haul.drop(columns=["stone_set"]).copy()
        found = np.isfinite(rr["s_cost"])
        la = np.where(found, rr["la"], -1).astype(np.int64)
        lb = np.where(found, rr["lb"], -1).astype(np.int64)
        hA = np.where(found, l_h[np.maximum(la, 0)], 0.0); hB = np.where(found, l_h[np.maximum(lb, 0)], 0.0)
        st = sea_trip_h(rr["hf1"], rr["hm1"], rr["hf2"], rr["hm2"], rr["sea_m"], kn, S)
        cost_sea = np.where(found & (la != lb), st + hoist_eq_h(hA + hB, S), np.inf)
        use = cost_sea < land_h
        h["mode"] = np.where(use, "sea", "land")
        h["eligible"] = elig
        h["land_haul_flatm"] = haul.haul_flatm; h["land_haul_m"] = haul.haul_m
        h["land_trip_h"] = land_h
        h["sea_trip_h"] = np.where(found, st, np.nan)
        h["sea_cost_h"] = np.where(np.isfinite(cost_sea), cost_sea, np.nan)
        z0 = np.zeros(len(h))
        h["haul_flatm_1"] = np.where(use, rr["hf1"], haul.haul_flatm); h["haul_m_1"] = np.where(use, rr["hm1"], haul.haul_m)
        h["haul_flatm_2"] = np.where(use, rr["hf2"], z0); h["haul_m_2"] = np.where(use, rr["hm2"], z0)
        h["sea_km"] = np.where(use, rr["sea_m"] / 1000.0, z0)
        h["hoist_a_m"] = np.where(use, hA, z0); h["hoist_b_m"] = np.where(use, hB, z0)
        h["hoist_m"] = h.hoist_a_m + h.hoist_b_m
        h["landing_a"] = np.where(use, la, -1); h["landing_b"] = np.where(use, lb, -1)
        h["landing_a_type"] = np.where(use, np.where(beach[np.maximum(la, 0)], "beach", "hoist"), "")
        h["landing_b_type"] = np.where(use, np.where(beach[np.maximum(lb, 0)], "beach", "hoist"), "")
        h["landing_a_x"] = np.where(use, lx[np.maximum(la, 0)], np.nan); h["landing_a_y"] = np.where(use, ly[np.maximum(la, 0)], np.nan)
        h["landing_b_x"] = np.where(use, lx[np.maximum(lb, 0)], np.nan); h["landing_b_y"] = np.where(use, ly[np.maximum(lb, 0)], np.nan)
        # sea rows: land-leg totals in the baseline columns and the sea quarry
        qf = np.where(use, rr["q_flat"], -1).astype(np.int64)
        h.loc[use, "haul_flatm"] = rr["hf1"][use] + rr["hf2"][use]
        h.loc[use, "haul_m"] = rr["hm1"][use] + rr["hm2"][use]
        qrow, qcol = qf[use] // W, qf[use] % W
        h.loc[use, "quarry_row"] = qrow; h.loc[use, "quarry_col"] = qcol
        h.loc[use, "quarry_x"] = T.c + (qcol + 0.5) * T.a; h.loc[use, "quarry_y"] = T.f + (qrow + 0.5) * T.e
        h.loc[use, "quarry_stone"] = [name_of[int(c)] for c in code_flat[qf[use]]]
        h.loc[use, "on_outcrop"] = False
        h["quarry_region"] = -1
        h.loc[use, "quarry_region"] = lab_flat[qf[use]]
        h["trip_h"] = np.where(use, st, land_h)
        h.to_csv(os.path.join(out, f"sites_haul_sea{kn:g}kn.csv"), index=False)
        print(f"[8] wrote sites_haul_sea{kn:g}kn.csv: sea {int(use.sum())} of {int(elig.sum())} eligible sites", flush=True)
    del label, lab_flat, code, code_flat

    # ---- 9. people: site -> sites / quarry points, min(walk, walk + boat + walk) (crew time = real time here)
    kb = np.load(os.path.join(P["cache_dir"], "alliance", "kbest.npz"))
    km = pd.DataFrame(kb["meta"])
    Tk = kb["transform"]
    tgt = [pd.DataFrame({"kind": "site", "key": haul.UID, "x": haul.x, "y": haul.y})]
    qx_k = Tk[2] + (km.qcol.to_numpy() + 0.5) * Tk[0]; qy_k = Tk[5] + (km.qrow.to_numpy() + 0.5) * Tk[4]
    tgt.append(pd.DataFrame({"kind": "quarry", "key": "", "x": qx_k, "y": qy_k}))
    for kn in speeds:
        hs = pd.read_csv(os.path.join(out, f"sites_haul_sea{kn:g}kn.csv"), usecols=["mode", "quarry_x", "quarry_y"])
        hs = hs[hs["mode"] == "sea"]
        tgt.append(pd.DataFrame({"kind": "quarry", "key": "", "x": hs.quarry_x, "y": hs.quarry_y}))
    tg = pd.concat(tgt, ignore_index=True)
    tg["kx"] = np.round(tg.x).astype(np.int64); tg["ky"] = np.round(tg.y).astype(np.int64)
    tg = tg.drop_duplicates(["kind", "key", "kx", "ky"]).reset_index(drop=True)
    walk = float(cfg["scenarios"].get("help_walk_ms", 1.4))
    rmax = float(S["people_walk_to_landing_m"])
    ltree = cKDTree(np.column_stack([lx, ly]))
    tg_near = ltree.query_ball_point(tg[["x", "y"]].to_numpy(), r=rmax)
    has = np.array([len(v) > 0 for v in tg_near])
    tg = tg[has].reset_index(drop=True)                          # only targets with a landing within walking reach
    t_reach = [np.array(v, np.int64) for v, h_ in zip(tg_near, has) if h_]
    tgt_tree = cKDTree(tg[["x", "y"]].to_numpy())
    src = np.flatnonzero(elig)
    sxy = haul[["x", "y"]].to_numpy()
    s_near = ltree.query_ball_point(sxy[src], r=rmax)
    cut = float(S["people_max_h"])
    for kn in speeds:
        v = kn * KN
        a_sea = 1.0 / v / 3600.0
        rows = []
        t1 = time.time()
        for si, i in enumerate(src):
            near = np.array(s_near[si], np.int64)
            if near.size == 0:
                continue
            sv = np.hypot(lx[near] - sxy[i, 0], ly[near] - sxy[i, 1]) / walk / 3600.0 + float(S["people_embark_h"]) + a_sea * l_att[near]
            GS.run(0.0, a_sea, l_bnode[near], sv, near, cut)
            # candidate targets: within the sea reach (straight line <= cut x v + 2 walks)
            cand = tgt_tree.query_ball_point(sxy[i], r=cut * 3600.0 * v + 2 * rmax)
            for j in cand:
                lj = t_reach[j]
                if lj.size == 0:
                    continue
                d = GS.dist[l_bnode[lj]].astype(np.float64)
                if not np.isfinite(d).any():
                    continue
                tt = d + a_sea * l_att[lj] + np.hypot(lx[lj] - tg.x[j], ly[lj] - tg.y[j]) / walk / 3600.0
                k = int(np.argmin(tt))
                tsea = float(tt[k])
                twalk = float(np.hypot(sxy[i, 0] - tg.x[j], sxy[i, 1] - tg.y[j])) / walk / 3600.0
                if tsea < twalk and tsea <= cut:
                    rows.append((haul.UID[i], tg.kind[j], tg.key[j], int(tg.kx[j]), int(tg.ky[j]), tsea, twalk))
        pp = pd.DataFrame(rows, columns=["src_UID", "kind", "tgt_UID", "kx", "ky", "t_sea_h", "t_walk_h"])
        pp.to_csv(os.path.join(out, f"people_sea{kn:g}kn.csv.gz"), index=False, compression="gzip")
        print(f"[9] people {kn} kn: {len(src)} source sites; {len(pp):,} (site, target) pairs faster by sea "
              f"({int((pp.kind == 'site').sum()):,} site targets); {time.time() - t1:.0f} s; {cgmem()}", flush=True)
    with open(os.path.join(out, "sea_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1, default=str)
    print(f"done in {time.time() - t0:.0f} s; {cgmem()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--speeds", default=None, help="comma list of knots (default: sea.speeds_kn + sea.extra_speeds_kn)")
    a = ap.parse_args()
    c = load_config(a.config)
    sp = [float(x) for x in a.speeds.split(",")] if a.speeds else \
        [float(x) for x in c["sea"]["speeds_kn"]] + [float(x) for x in c["sea"].get("extra_speeds_kn", [])]
    main(a.config, sp)
