"""Shared helpers: config loading and the directional multi-source Dijkstra (numba).

Direction order (band k = 1..8): N, NE, E, SE, S, SW, W, NW, as (drow, dcol),
the same convention as stone-abm/stone_abm.py and the cost raster.
"""
import os
import resource

import numpy as np
import yaml
from numba import njit

DIRS = np.array([(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)], dtype=np.int64)


def load_config(path):
    """Read config.yaml and resolve paths: inputs against data_dir, cache/output against the config folder."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    base = os.path.dirname(os.path.abspath(path))
    data_dir = cfg["data_dir"]
    if not os.path.isabs(data_dir):
        data_dir = os.path.join(base, data_dir)
    p = cfg["paths"]
    for key in ("sites", "cost_raster", "lithology"):
        p[key] = p[key] if os.path.isabs(p[key]) else os.path.join(data_dir, p[key])
    for key in ("cache_dir", "output_dir"):
        p[key] = p[key] if os.path.isabs(p[key]) else os.path.join(base, p[key])
        os.makedirs(p[key], exist_ok=True)
    return cfg


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def step_lengths(res):
    """Horizontal length in metres of a move in each of the 8 directions."""
    return np.array([res * (np.sqrt(2.0) if (dr and dc) else 1.0) for dr, dc in DIRS], dtype=np.float64)


# ---------------------------------------------------------------- indexed binary min-heap (decrease-key)
@njit(cache=True, inline="always")
def _sift_up(heap, pos, key, i):
    v = heap[i]
    kv = key[v]
    while i > 0:
        p = (i - 1) >> 1
        u = heap[p]
        if key[u] <= kv:
            break
        heap[i] = u
        pos[u] = i
        i = p
    heap[i] = v
    pos[v] = i


@njit(cache=True, inline="always")
def _sift_down(heap, pos, key, i, n):
    v = heap[i]
    kv = key[v]
    while True:
        c = 2 * i + 1
        if c >= n:
            break
        if c + 1 < n and key[heap[c + 1]] < key[heap[c]]:
            c += 1
        u = heap[c]
        if key[u] >= kv:
            break
        heap[i] = u
        pos[u] = i
        i = c
    heap[i] = v
    pos[v] = i


@njit(cache=True)
def multi_source_dijkstra(cost, seeds, steplen, dist, origin, plen):
    """Forward directional Dijkstra from many sources at distance 0.

    cost   : (8, H, W) uint8, band k = cost of moving FROM a cell INTO neighbour k; 0 = impassable.
    seeds  : int64 flat indices (r*W + c) of source cells.
    steplen: (8,) metres per move (30 or 42.43).
    Outputs (flat, length H*W, filled in place):
      dist   float32 least summed band cost from any seed (inf = unreachable)
      origin int32   flat index of the seed the least-cost path starts at (-1 = unreachable)
      plen   float32 horizontal path length in metres along that least-cost path
    Edge u -> v (v = u + DIRS[k]) costs cost[k, u]: stone moves outcrop -> site.
    Returns the number of settled cells.
    """
    _, H, W = cost.shape
    N = H * W
    dist[:] = np.inf
    origin[:] = -1
    plen[:] = 0.0
    heap = np.empty(N, np.int32)
    pos = np.full(N, -1, np.int32)        # -1 never queued, -2 settled, >=0 heap slot
    n = 0
    for s in seeds:
        if pos[s] == -1:
            dist[s] = 0.0
            origin[s] = s
            heap[n] = s
            pos[s] = n
            n += 1                           # all keys 0 -> already a valid heap
    settled = 0
    while n > 0:
        u = heap[0]
        n -= 1
        if n > 0:
            heap[0] = heap[n]
            pos[heap[0]] = 0
            _sift_down(heap, pos, dist, 0, n)
        pos[u] = -2
        settled += 1
        r = u // W
        c = u - r * W
        du = dist[u]
        for k in range(8):
            w = cost[k, r, c]
            if w == 0:
                continue
            rr = r + DIRS[k, 0]
            cc = c + DIRS[k, 1]
            if rr < 0 or cc < 0 or rr >= H or cc >= W:
                continue
            v = rr * W + cc
            pv = pos[v]
            if pv == -2:
                continue
            nd = np.float32(du + np.float32(w))
            if nd < dist[v]:
                dist[v] = nd
                origin[v] = origin[u]
                plen[v] = np.float32(plen[u] + steplen[k])
                if pv == -1:
                    heap[n] = v
                    pos[v] = n
                    n += 1
                    _sift_up(heap, pos, dist, n - 1)
                else:
                    _sift_up(heap, pos, dist, pv)
    return settled


def snapped_cell(rec, valid_window, R, H, W, res):
    """BUGFIX_REPORT item 11 (fixed in v12): the search start cell of a site = its SNAPPED cell. sites_haul.csv keeps
    the unsnapped row/col plus snap_status and snap_dist_m; for a snapped site the snapped cell is recovered as in
    preprocess.py (nearest cell, by cell-centre distance, within R cells; ties: first in row order) among the cells
    of the cost raster that hold data (valid_window(ra, rb, ca, cb) -> bool array), at exactly snap_dist_m. For
    'ok' and '*_nosnap' sites (all 7,167 today) it returns row/col unchanged."""
    r0, c0 = int(rec["row"]), int(rec["col"])
    if not str(rec["snap_status"]).startswith("snapped_"):
        return r0, c0
    ra, rb, ca, cb = max(0, r0 - R), min(H, r0 + R + 1), max(0, c0 - R), min(W, c0 + R + 1)
    rr, cc = np.nonzero(valid_window(ra, rb, ca, cb))
    dd = np.hypot(rr + ra - r0, cc + ca - c0) * res
    k = np.flatnonzero(np.abs(dd - float(rec["snap_dist_m"])) < 1e-6 * max(1.0, res))
    if k.size == 0:
        raise ValueError(f"snapped_cell: no data cell at {rec['snap_dist_m']} m of site {rec.get('UID', '?')}")
    return int(rr[k[0]] + ra), int(cc[k[0]] + ca)
