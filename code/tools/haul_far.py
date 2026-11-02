"""S5c_complex_far: complex nuraghi (TWR_N >= min_towers) take stone from the cheapest allowed outcrop cell that
lies at least min_dist_m (straight line) from the site.

  python tools/haul_far.py config.yaml

Method: a REVERSE directional Dijkstra from the site (edge p -> u costs band k at p, explored backwards), on a
window around the site. Cells are settled in order of their least drag cost TO the site; the first settled
allowed-outcrop cell >= min_dist_m away is the answer (= the least-cost far source). The window grows if needed.
Check: for 3 sites a forward single-source Dijkstra from the chosen quarry must give the same cost.
Writes cache/haul/sites_haul_complexfar.csv (other sites keep their baseline haul).
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
from nbcommon import DIRS, load_config, snapped_cell, step_lengths  # noqa: E402
from tests.verify_hauls import single_source  # noqa: E402


@njit(cache=True)
def reverse_far(cost, code, sr, sc, min_cells2, steplen, open_n, open_s, open_w, open_e, allowed):
    """Returns (cost, path_m, row, col, exact) of the first settled outcrop cell with (dr^2+dc^2) >= min_cells2.
    exact = no cell on an 'open' window edge (one that is not the raster edge) was settled first, so no
    path leaving the window can be cheaper."""
    _, H, W = cost.shape
    dist = np.full((H, W), np.inf)
    plen = np.zeros((H, W))
    dist[sr, sc] = 0.0
    heap = [(0.0, sr * W + sc)]
    while heap:
        d, idx = heapq.heappop(heap)
        r = idx // W
        c = idx % W
        if d > dist[r, c]:
            continue
        if allowed[code[r, c]] and (r - sr) ** 2 + (c - sc) ** 2 >= min_cells2:
            return d, plen[r, c], r, c, True
        if (open_n and r == 0) or (open_s and r == H - 1) or (open_w and c == 0) or (open_e and c == W - 1):
            return np.inf, 0.0, -1, -1, False
        for k in range(8):
            pr = r - DIRS[k, 0]          # predecessor p with p + DIRS[k] = u
            pc = c - DIRS[k, 1]
            if pr < 0 or pc < 0 or pr >= H or pc >= W:
                continue
            w = cost[k, pr, pc]
            if w == 0:
                continue
            nd = d + w
            if nd < dist[pr, pc]:
                dist[pr, pc] = nd
                plen[pr, pc] = plen[r, c] + steplen[k]
                heapq.heappush(heap, (nd, pr * W + pc))
    return np.inf, 0.0, -1, -1, True


def main(cfg_path):
    cfg = load_config(cfg_path)
    L = cfg["lit_scenarios"]
    min_tw, min_m = int(L["complex_far_min_towers"]), float(L["complex_far_min_dist_m"])
    h = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    out = h.copy()
    sel = h.index[h.TWR_N >= min_tw]
    with rasterio.open(os.path.join(cfg["paths"]["cache_dir"], "outcrop_code.tif")) as oc0:
        tags = oc0.tags().get("codes", "")
    code_of = {v: int(k) for k, v in (t.split("=", 1) for t in tags.split(";") if t)}
    names = np.array(["none"] + [k for k, _ in sorted(code_of.items(), key=lambda kv: kv[1])])
    ss = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "site_stone_sets.csv")).set_index("UID").stone_set
    with rasterio.open(cfg["paths"]["cost_raster"]) as r, \
            rasterio.open(os.path.join(cfg["paths"]["cache_dir"], "outcrop_code.tif")) as oc:
        T = r.transform; H, W = r.height, r.width; res = abs(T.a)
        sl = step_lengths(res)
        checks = []
        for n, i in enumerate(sel):
            r0, c0 = snapped_cell(h.loc[i], lambda ra, rb, ca, cb: r.read(window=Window(ca, ra, cb - ca, rb - ra)).any(axis=0),
                                  int(cfg["nodata_snap_radius_cells"]), H, W, res)   # item 11: the snapped cell
            pad = int(4 * min_m / res)
            while True:
                ra, rb, ca, cb = max(0, r0 - pad), min(H, r0 + pad + 1), max(0, c0 - pad), min(W, c0 + pad + 1)
                win = Window(ca, ra, cb - ca, rb - ra)
                cost = r.read(window=win); code = oc.read(1, window=win)
                allowed = np.zeros(len(names), np.bool_)
                for c_ in str(ss[h.UID[i]]).split("; "):
                    allowed[code_of[c_]] = True
                d, pm, qr, qc, exact = reverse_far(cost, code, r0 - ra, c0 - ca, (min_m / res) ** 2, sl,
                                                   ra > 0, rb < H, ca > 0, cb < W, allowed)
                if exact and np.isfinite(d):
                    break
                if exact or pad > 5000:        # B13 (by design: no silent partial table), with a clear reason
                    why = (f"no outcrop of its classes ({ss[h.UID[i]]}) >= {min_m:.0f} m away is reachable over land"
                           if exact else f"the search window reached its cap ({pad} cells) before an exact answer")
                    raise RuntimeError(f"S5c: no far outcrop for {h.UID[i]}: {why}; S5c needs one for every site with "
                                       f"TWR_N >= {min_tw}")
                pad *= 2
            gr, gc = qr + ra, qc + ca
            out.loc[i, ["haul_flatm", "haul_m"]] = [d, pm]
            out.loc[i, "quarry_x"] = T.c + (gc + 0.5) * T.a
            out.loc[i, "quarry_y"] = T.f + (gr + 0.5) * T.e
            out.loc[i, ["quarry_row", "quarry_col"]] = [gr, gc]
            out.loc[i, "quarry_stone"] = names[code[qr, qc]]
            out.loc[i, "on_outcrop"] = False
            out.loc[i, "haul_flag"] = "complex_far"
            if len(checks) < 3 and n % 150 == 0:
                fd, _ = single_source(cost, qr, qc, r0 - ra, c0 - ca)
                checks.append((h.UID[i], d, fd))
    out.to_csv(os.path.join(cfg["paths"]["cache_dir"], "haul", "sites_haul_complexfar.csv"), index=False)
    s = out.loc[sel]
    straight = np.hypot(s.quarry_x - s.x, s.quarry_y - s.y)
    print(f"S5c: {len(sel)} sites with TWR_N >= {min_tw}; far source >= {min_m:.0f} m: straight-line "
          f"min {straight.min():.0f} m, median {straight.median():.0f} m; haul_m median {s.haul_m.median():.0f}, "
          f"max {s.haul_m.max():.0f}; haul_flatm median {s.haul_flatm.median():.0f} "
          f"(baseline median for these sites {h.loc[sel, 'haul_flatm'].median():.0f})")
    for uid, d, fd in checks:
        print(f"  check {uid}: reverse search {d:.0f} flat-m, forward single-source from the chosen quarry {fd:.0f} "
              f"-> {'MATCH' if d == fd else 'MISMATCH'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
