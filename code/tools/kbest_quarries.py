"""Alliance model preprocessing: the k cheapest DISTINCT quarry faces per site, with their least-cost paths.

  python tools/kbest_quarries.py config.yaml

1. Outcrop regions: connected components (8-neighbour) of the allowed-outcrop raster (cache/outcrop_code.tif).
   A "quarry face" = one region; its cell = the cheapest cell of that region for the site.
2. Per site, a REVERSE directional Dijkstra (edge p -> u costs band k at p) over the whole grid with early stop,
   settling cells in order of drag cost TO the site, until k distinct regions have been settled. The first
   settled cell of each region is that region's cheapest quarry cell (exact: Dijkstra order).
3. For each (site, face) the path quarry -> site is read back from the search tree. Per move we keep the
   from-cell, the band cost at mu 0.3 (the delivered raster) and at mu 0.1 (cache/cost_mu, for tracks) and the
   move length. Hand-off cells for relay fractions f are the first path cells whose cumulative mu-0.3 cost
   reaches f x total.
Checks printed: face 0 cost == the multi-source baseline haul_flatm for every reachable site; additivity of legs.
Writes cache/alliance/kbest.npz.
"""
import heapq
import os
import sys
import time

import numpy as np
import pandas as pd
import rasterio
from numba import njit
from scipy import ndimage

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import DIRS, load_config, peak_rss_mb, snapped_cell, step_lengths  # noqa: E402


@njit(cache=True)
def reverse_kbest(cost, label, code, allowed, sr, sc, k, max_settle, dist, nxt, plen, touched):
    """Returns arrays (region, cell, cost, plen) for up to k distinct regions, and the number of touched cells.
    dist (float32, flat, init inf) and nxt (int32, flat) are reused across calls; touched lists cells to reset."""
    _, H, W = cost.shape
    src = sr * W + sc
    nt = 0
    dist[src] = 0.0
    nxt[src] = -1
    touched[nt] = src; nt += 1
    plen[src] = 0.0
    regs = np.full(k, -1, np.int64); cells = np.full(k, -1, np.int64)
    costs = np.zeros(k); lens = np.zeros(k)
    nf = 0
    heap = [(0.0, src)]
    settled = 0
    sl = np.array([30.0, 42.42640687119285, 30.0, 42.42640687119285, 30.0, 42.42640687119285, 30.0, 42.42640687119285])
    while heap and nf < k and settled < max_settle:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        settled += 1
        r = u // W
        c = u - r * W
        lab = label[r, c]
        if lab > 0 and allowed[code[r, c]]:
            new = True
            for q in range(nf):
                if regs[q] == lab:
                    new = False
                    break
            if new:
                regs[nf] = lab; cells[nf] = u; costs[nf] = d; lens[nf] = plen[u]
                nf += 1
        for kk in range(8):
            pr = r - DIRS[kk, 0]
            pc = c - DIRS[kk, 1]
            if pr < 0 or pc < 0 or pr >= H or pc >= W:
                continue
            w = cost[kk, pr, pc]
            if w == 0:
                continue
            p = pr * W + pc
            nd = np.float32(d + w)
            if nd < dist[p]:
                if dist[p] == np.inf:
                    touched[nt] = p; nt += 1
                dist[p] = nd
                nxt[p] = u
                plen[p] = plen[u] + sl[kk]
                heapq.heappush(heap, (np.float64(nd), p))
    return regs[:nf], cells[:nf], costs[:nf], lens[:nf], nt


@njit(cache=True)
def reset(dist, touched, nt):
    for i in range(nt):
        dist[touched[i]] = np.inf


def main(cfg_path):
    t0 = time.time()
    cfg = load_config(cfg_path)
    A = cfg["alliance"]
    k = int(A["k_quarries"])
    P = cfg["paths"]
    out_dir = os.path.join(P["cache_dir"], "alliance")
    os.makedirs(out_dir, exist_ok=True)
    with rasterio.open(P["cost_raster"]) as r:
        H, W, T = r.height, r.width, r.transform
        cost = np.empty((8, H, W), np.uint8)
        for b in range(8):
            r.read(b + 1, out=cost[b])
    with rasterio.open(os.path.join(P["cache_dir"], "outcrop_code.tif")) as r:
        code = r.read(1)
    # regions = 8-connected components of each stone class separately (a face never spans two classes)
    with rasterio.open(os.path.join(P["cache_dir"], "outcrop_code.tif")) as r:
        tags = r.tags().get("codes", "")
    code_of = {v: int(kk) for kk, v in (t.split("=", 1) for t in tags.split(";") if t)}
    label = np.zeros(code.shape, np.int32)
    nreg = 0
    for c_ in sorted(code_of.values()):
        lab_c, n_c = ndimage.label(code == c_, structure=np.ones((3, 3), bool))
        m_ = lab_c > 0
        label[m_] = lab_c[m_] + nreg
        nreg += n_c
        del lab_c, m_
    ncode = max(code_of.values()) + 1
    ss = pd.read_csv(os.path.join(P["cache_dir"], "site_stone_sets.csv")).set_index("UID").stone_set
    print(f"outcrop regions (8-connected components of allowed outcrops): {nreg:,d}; RSS {peak_rss_mb():.0f} MB", flush=True)
    h = pd.read_csv(os.path.join(P["cache_dir"], "sites_haul.csv"))
    N = H * W
    dist = np.full(N, np.inf, np.float32)
    nxt = np.full(N, -1, np.int32)
    plen = np.zeros(N, np.float64)
    touched = np.empty(int(A["kbest_max_settle"]) * 8 + 16, np.int64)
    rows = []
    paths = []
    valid = None
    for i in range(len(h)):
        if str(h.snap_status[i]).startswith("snapped_") and valid is None:
            valid = cost.any(axis=0)                     # data cells (as preprocess.py), only if a site was snapped
        r0, c0 = snapped_cell(h.iloc[i], lambda ra, rb, ca, cb: valid[ra:rb, ca:cb],
                              int(cfg["nodata_snap_radius_cells"]), H, W, abs(T.a))   # item 11: the snapped cell
        allowed = np.zeros(ncode, np.bool_)
        for c_ in str(ss[h.UID[i]]).split("; "):
            allowed[code_of[c_]] = True
        regs, cells, cs, ls, nt = reverse_kbest(cost, label, code, allowed, r0, c0, k, int(A["kbest_max_settle"]),
                                                dist, nxt, plen, touched)
        for q in range(len(regs)):
            path = [int(cells[q])]
            while path[-1] != r0 * W + c0:
                path.append(int(nxt[path[-1]]))
            paths.append(np.array(path, np.int64))
            rows.append((i, q, int(regs[q]), int(cells[q]) // W, int(cells[q]) % W, float(cs[q]), float(ls[q])))
        reset(dist, touched, nt)
        if i % 1000 == 0:
            print(f"  site {i}/{len(h)}: {len(regs)} faces, {nt:,d} cells touched, {time.time() - t0:.0f} s", flush=True)
    meta = pd.DataFrame(rows, columns=["gid", "q", "region", "qrow", "qcol", "cost03", "len_m"])
    del dist, nxt, plen, touched
    # per-move arrays: from-cell, direction, cost at mu 0.3 and mu 0.1, length
    with rasterio.open(os.path.join(P["cache_dir"], "cost_mu", "drag_cost_8dir_mu0.1_int.tif")) as r:
        cost01 = np.empty((8, H, W), np.uint16)
        for b in range(8):
            r.read(b + 1, out=cost01[b])
    sl = step_lengths(abs(T.a))
    dlook = {(int(dr), int(dc)): kk for kk, (dr, dc) in enumerate(DIRS)}
    ptr = [0]; mv_cell = []; mv_c03 = []; mv_c01 = []; mv_len = []
    c01_tot = []
    for p in paths:
        rr, cc = p // W, p % W
        for a in range(len(p) - 1):
            kk = dlook[(int(rr[a + 1] - rr[a]), int(cc[a + 1] - cc[a]))]
            mv_cell.append(p[a]); mv_c03.append(cost[kk, rr[a], cc[a]]); mv_c01.append(cost01[kk, rr[a], cc[a]])
            mv_len.append(sl[kk])
        ptr.append(len(mv_cell))
    mv_c03 = np.array(mv_c03, np.int32); mv_c01 = np.array(mv_c01, np.int32)
    ptr = np.array(ptr, np.int64)
    meta["cost01"] = [int(mv_c01[ptr[j]:ptr[j + 1]].sum()) for j in range(len(paths))]
    sums = np.array([int(mv_c03[ptr[j]:ptr[j + 1]].sum()) for j in range(len(paths))])
    add_ok = bool(np.all(sums == meta.cost03.to_numpy()))
    # baseline check: face 0 == multi-source result
    f0 = meta[meta.q == 0].set_index("gid")
    reach = h.haul_flag != "unreachable_local"
    same = (f0.cost03.reindex(h.index[reach]).to_numpy() == h.haul_flatm[reach].to_numpy())
    lendiff = np.abs(f0.len_m.reindex(h.index[reach]).to_numpy() - h.haul_m[reach].to_numpy())
    nfaces = meta.groupby("gid").size().reindex(h.index, fill_value=0)
    np.savez_compressed(os.path.join(out_dir, "kbest.npz"), meta=meta.to_records(index=False), ptr=ptr,
                        mv_cell=np.array(mv_cell, np.int64), mv_c03=mv_c03, mv_c01=mv_c01,
                        mv_len=np.array(mv_len, np.float32), H=H, W=W, transform=np.array(T)[:6], nreg=nreg)
    print(f"faces per site: {dict(nfaces.value_counts().sort_index())}")
    print(f"CHECK face-0 cost == multi-source haul_flatm for {int(reach.sum())} reachable sites: {int(same.sum())} equal "
          f"-> {'ALL EQUAL' if same.all() else 'MISMATCH'}; face-0 path length differs from haul_m (equal-cost ties) "
          f"at {int((lendiff > 0.01).sum())} sites (max {lendiff.max():.1f} m)")
    print(f"CHECK sum of per-move costs == route cost for all {len(paths):,d} routes: {add_ok}")
    print(f"total moves {len(mv_cell):,d}; {time.time() - t0:.0f} s; peak RSS {peak_rss_mb():.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
