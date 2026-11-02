"""Verification (b): spot-check real sites against an independent single-source Dijkstra.

For N sites (chosen deterministically: not on an outcrop, hauls near 500 m, 2 km and 6 km), read a window of
the cost raster around site + reported quarry cell, run a separate lazy-deletion heapq Dijkstra (different
code from the indexed-heap multi-source one) FROM the reported quarry cell, and compare the cost at the site
with haul_flatm. Also reports the path length of the recovered path vs haul_m, checks that the quarry cell
is an allowed outcrop, and recomputes the path cost from the DEM with the recipe formula
(max(0.5, |mu + t| / mu) * d) as an independent check of the band semantics.

  python tests/verify_hauls.py config.yaml
"""
import heapq
import os
import sys

import numpy as np
import pandas as pd
import rasterio
from numba import njit
from rasterio.windows import Window

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import DIRS, load_config, step_lengths  # noqa: E402


@njit(cache=True)
def single_source(cost, sr, sc, tr_, tc):
    _, H, W = cost.shape
    dist = np.full((H, W), np.inf)
    prev = np.full((H, W), -1, np.int64)
    dist[sr, sc] = 0.0
    heap = [(0.0, sr * W + sc)]
    while heap:
        d, idx = heapq.heappop(heap)
        r = idx // W
        c = idx % W
        if d > dist[r, c]:
            continue
        if r == tr_ and c == tc:
            break
        for k in range(8):
            w = cost[k, r, c]
            if w == 0:
                continue
            rr = r + DIRS[k, 0]
            cc = c + DIRS[k, 1]
            if rr < 0 or cc < 0 or rr >= H or cc >= W:
                continue
            nd = d + w
            if nd < dist[rr, cc]:
                dist[rr, cc] = nd
                prev[rr, cc] = idx
                heapq.heappush(heap, (nd, rr * W + cc))
    path = []
    i = tr_ * W + tc
    while i != -1:
        path.append(i)
        i = prev[i // W, i % W]
    return dist[tr_, tc], path[::-1]


def main(cfg_path):
    cfg = load_config(cfg_path)
    P = cfg["paths"]
    v = cfg["verify"]
    h = pd.read_csv(os.path.join(P["cache_dir"], "sites_haul.csv"))
    cand = h[(~h.on_outcrop) & (h.haul_flag == "ok")]
    picks = []
    for target in [500, 2000, 6000][: v["spot_check_n"]]:
        picks.append(cand.iloc[(cand.haul_m - target).abs().argsort().iloc[0]])
    pad = int(v["spot_check_pad_m"] / 30)
    dem_path = os.path.join(cfg["data_dir"], v["dem"]) if v.get("dem") else None
    mu = v.get("dem_mu", 0.3)
    allok = True
    with rasterio.open(P["cost_raster"]) as r, rasterio.open(os.path.join(P["cache_dir"], "outcrop_code.tif")) as oc:
        T = r.transform
        for s in picks:
            r0, c0, qr, qc = int(s.row), int(s.col), int(s.quarry_row), int(s.quarry_col)
            ra, rb = max(0, min(r0, qr) - pad), min(r.height, max(r0, qr) + pad + 1)
            ca, cb = max(0, min(c0, qc) - pad), min(r.width, max(c0, qc) + pad + 1)
            win = Window(ca, ra, cb - ca, rb - ra)
            cost = r.read(window=win)
            d, path = single_source(cost, qr - ra, qc - ca, r0 - ra, c0 - ca)
            W = cb - ca
            rows = np.array([p // W for p in path]); cols = np.array([p % W for p in path])
            dr = np.diff(rows); dc = np.diff(cols)
            plen = float(np.sum(np.where((dr != 0) & (dc != 0), 30 * np.sqrt(2), 30.0)))
            code = oc.read(1, window=Window(qc, qr, 1, 1))[0, 0]
            ok = (d == s.haul_flatm)
            allok &= ok
            print(f"  {s.UID}: haul_flatm (multi-source) {s.haul_flatm:.0f}  single-source from quarry "
                  f"({s.quarry_x:.0f}, {s.quarry_y:.0f}) {d:.0f}  -> {'MATCH' if ok else 'MISMATCH'};  "
                  f"path length {plen:.1f} m vs haul_m {s.haul_m:.1f} m; quarry cell code {code} "
                  f"({s.quarry_stone}); window {cb - ca}x{rb - ra} cells")
            if dem_path:
                with rasterio.open(dem_path) as dem:
                    assert dem.transform == T
                    z = dem.read(1, window=win).astype(np.float64)
                zz = z[rows, cols]
                dd = np.where((dr != 0) & (dc != 0), 30 * np.sqrt(2), 30.0)
                t = np.clip(np.diff(zz) / dd, -1, 1)
                demcost = float(np.sum(np.maximum(0.5, np.abs(mu + t) / mu) * dd))
                up = float(np.sum(np.maximum(np.diff(zz), 0))); down = float(np.sum(np.maximum(-np.diff(zz), 0)))
                print(f"      DEM recomputation of the same path (recipe formula, mu={mu}): {demcost:.1f} flat-m "
                      f"(int raster sum {d:.0f}, diff {100 * (d - demcost) / demcost:+.2f}%); "
                      f"climb {up:.0f} m, descent {down:.0f} m, z quarry {zz[0]:.0f} -> site {zz[-1]:.0f}")
    print("SPOT CHECK", "PASSED" if allok else "FAILED")
    return allok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml") else 1)
