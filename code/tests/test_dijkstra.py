"""Verification (a): unit tests of the directional multi-source Dijkstra on tiny synthetic grids.

Run:  python tests/test_dijkstra.py
"""
import heapq
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import DIRS, multi_source_dijkstra, step_lengths  # noqa: E402

STEP = step_lengths(30.0)


def run(cost, seeds):
    _, H, W = cost.shape
    d = np.empty(H * W, np.float32); o = np.empty(H * W, np.int32); p = np.empty(H * W, np.float32)
    multi_source_dijkstra(cost, np.asarray(seeds, np.int64), STEP, d, o, p)
    return d.reshape(H, W), o.reshape(H, W), p.reshape(H, W)


def reference(cost, seeds):
    """Independent plain-Python heapq Dijkstra (lazy deletion), forward edges cost[k, u]."""
    _, H, W = cost.shape
    dist = {s: 0.0 for s in seeds}
    pq = [(0.0, s) for s in seeds]
    heapq.heapify(pq)
    done = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        r, c = divmod(u, W)
        for k in range(8):
            w = int(cost[k, r, c])
            rr, cc = r + DIRS[k, 0], c + DIRS[k, 1]
            if w == 0 or not (0 <= rr < H and 0 <= cc < W):
                continue
            v = rr * W + cc
            if d + w < dist.get(v, np.inf):
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    out = np.full((H, W), np.inf)
    for v, d in dist.items():
        out.flat[v] = d
    return out


def test_uphill_downhill_1d():
    """A 1x4 ramp rising to the east: moving E (uphill) costs 50 per step, moving W (downhill) 15.
    Stone from an outcrop at the WEST end must climb: 3 x 50 = 150 at the east end.
    Stone from an outcrop at the EAST end only descends: 3 x 15 = 45 at the west end.
    A Dijkstra that used the reverse edge direction would give 45 and 150 instead."""
    cost = np.zeros((8, 1, 4), np.uint8)
    cost[2, 0, :3] = 50          # band 3 = E
    cost[6, 0, 1:] = 15          # band 7 = W
    d, o, p = run(cost, [0])
    assert d[0, 3] == 150.0, d
    assert np.allclose(p[0], [0, 30, 60, 90])
    d, o, p = run(cost, [3])
    assert d[0, 0] == 45.0, d
    print("  1-D ramp: west outcrop -> east end = %.0f (expect 150); east outcrop -> west end = %.0f (expect 45)"
          % (run(cost, [0])[0][0, 3], d[0, 0]))


def test_two_sources_asymmetric():
    """Two outcrops at both ends of a 1x5 ramp rising to the east (E costs 50, W costs 15).
    The middle cell (col 2) is 2x50=100 from the west outcrop but only 2x15=30 from the east one,
    so it must be assigned to the EAST outcrop (origin = col 4) with cost 30 and path 60 m."""
    cost = np.zeros((8, 1, 5), np.uint8)
    cost[2, 0, :4] = 50
    cost[6, 0, 1:] = 15
    d, o, p = run(cost, [0, 4])
    assert d[0, 2] == 30.0 and o[0, 2] == 4 and abs(p[0, 2] - 60.0) < 1e-4, (d, o, p)
    # col 1: 50 from west vs 45 from east -> east wins
    assert d[0, 1] == 45.0 and o[0, 1] == 4
    print("  two outcrops: middle cell cost %.0f from origin col %d (expect 30 from col 4); "
          "col 1 cost %.0f from col %d (expect 45 from 4)" % (d[0, 2], o[0, 2], d[0, 1], o[0, 1]))


def test_diagonal_and_nodata():
    """3x3 grid, centre impassable (all bands 0). From corner (0,0) to (2,2) the path must go round."""
    cost = np.zeros((8, 3, 3), np.uint8)
    H = W = 3
    for r in range(H):
        for c in range(W):
            for k in range(8):
                rr, cc = r + DIRS[k, 0], c + DIRS[k, 1]
                if 0 <= rr < H and 0 <= cc < W and (rr, cc) != (1, 1) and (r, c) != (1, 1):
                    cost[k, r, c] = 42 if (DIRS[k, 0] and DIRS[k, 1]) else 30
    d, o, p = run(cost, [0])
    # cheapest detour: E,E,S,S = 120 or E,SE(into (1,2)),S... (0,0)->(0,1) 30 ->(1,2) 42 ->(2,2) 30 = 102
    assert d[2, 2] == 102.0, d
    assert abs(p[2, 2] - (30 + 42.426 + 30)) < 0.01
    assert np.isinf(d[1, 1]) and o[1, 1] == -1
    print("  diagonal detour around nodata: cost %.0f (expect 102), path %.2f m (expect 102.43), centre unreachable"
          % (d[2, 2], p[2, 2]))


def test_random_vs_reference():
    """Random asymmetric costs with nodata, 3 sources: compare with the independent heapq reference,
    and check that each cell's origin really gives that cost (single-source rerun from the origin)."""
    rng = np.random.default_rng(42)
    H, W = 40, 35
    cost = rng.integers(15, 200, size=(8, H, W)).astype(np.uint8)
    cost[:, rng.random((H, W)) < 0.1] = 0
    seeds = [5, 700, 1300]
    d, o, p = run(cost, seeds)
    ref = reference(cost, seeds)
    assert np.array_equal(np.isinf(d), np.isinf(ref))
    m = np.isfinite(ref)
    assert np.array_equal(d[m], ref[m].astype(np.float32))
    bad = 0
    for s in seeds:
        single = reference(cost, [s])
        sel = (o == s)
        bad += int(np.sum(single[sel] != d[sel]))
    assert bad == 0
    print("  random 40x35 grid, 3 sources, 10%% nodata: %d finite cells all equal the reference; origins consistent"
          % m.sum())


if __name__ == "__main__":
    print("Verification (a): Dijkstra unit tests")
    test_uphill_downhill_1d()
    test_two_sources_asymmetric()
    test_diagonal_and_nodata()
    test_random_vs_reference()
    print("ALL DIJKSTRA TESTS PASSED")
