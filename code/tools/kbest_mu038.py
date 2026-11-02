"""MOST_REALISTIC (alliance tech rules): per-move drag cost at mu 0.38 (S3c sledge on dry ground) along the
k-best quarry routes of cache/alliance/kbest.npz (routes found at mu 0.3; geometry unchanged).

  python tools/kbest_mu038.py config.yaml

Each move's direction is recovered from its from-cell and the next cell of the path (the next move's from-cell,
or the site cell for the last move); the cost is band k of cache/cost_mu/drag_cost_8dir_mu0.38_int.tif at the
from-cell, exactly as kbest_quarries.py reads mu 0.3 / mu 0.1. Check: the recomputed mu 0.3 / mu 0.1 sums equal
the stored ones. Writes cache/alliance/kbest_mu038.npz (mv_c038 int32, cost038 per route). Reads one band at a
time (~45 MB).
"""
import os
import sys

import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import DIRS, load_config  # noqa: E402


def main():
    cfg = load_config(sys.argv[1])
    P = cfg["paths"]
    kb = np.load(os.path.join(P["cache_dir"], "alliance", "kbest.npz"))
    meta = pd.DataFrame(kb["meta"])
    W = int(kb["W"])
    ptr, cell = kb["ptr"], kb["mv_cell"]
    h = pd.read_csv(os.path.join(P["cache_dir"], "sites_haul.csv"))
    site_cell = (h.row.to_numpy().astype(np.int64) * W + h.col.to_numpy().astype(np.int64))
    nxt = np.empty_like(cell)
    nxt[:-1] = cell[1:]
    nonempty = ptr[1:] > ptr[:-1]
    last = (ptr[1:] - 1)[nonempty]                        # last move of each (non-empty) route -> the site cell
    nxt[last] = site_cell[meta.gid.to_numpy()[nonempty]]
    dr = nxt // W - cell // W
    dc = nxt % W - cell % W
    dlook = {(int(a), int(b)): k for k, (a, b) in enumerate(DIRS)}
    code = np.array([dlook[(int(a), int(b))] for a, b in zip(dr, dc)], np.int64)
    rr, cc = cell // W, cell % W

    def sample(path, dtype):
        out = np.zeros(cell.size, np.int32)
        with rasterio.open(path) as r:
            for k in range(8):
                m = code == k
                if m.any():
                    band = r.read(k + 1).astype(dtype)
                    out[m] = band[rr[m], cc[m]]
                    del band
        return out
    chk03 = sample(P["cost_raster"], np.int32)
    chk01 = sample(os.path.join(P["cache_dir"], "cost_mu", "drag_cost_8dir_mu0.1_int.tif"), np.int32)
    ok03 = bool(np.array_equal(chk03, kb["mv_c03"])); ok01 = bool(np.array_equal(chk01, kb["mv_c01"]))
    c038 = sample(os.path.join(P["cache_dir"], "cost_mu", "drag_cost_8dir_mu0.38_int.tif"), np.int32)
    cs = np.concatenate([[0], np.cumsum(c038.astype(np.int64))])
    cost038 = cs[ptr[1:]] - cs[ptr[:-1]]
    np.savez_compressed(os.path.join(P["cache_dir"], "alliance", "kbest_mu038.npz"), mv_c038=c038, cost038=cost038)
    r = cost038 / np.maximum(meta.cost03.to_numpy(), 1)
    print(f"CHECK recomputed directions: mu0.3 band costs equal stored mv_c03: {ok03}; mu0.1 equal mv_c01: {ok01}")
    print(f"routes {len(meta):,d}, moves {cell.size:,d}; route cost mu0.38 / mu0.3: median {np.median(r):.3f}, "
          f"p10 {np.percentile(r, 10):.3f}, p90 {np.percentile(r, 90):.3f}")
    if not (ok03 and ok01):
        sys.exit("direction recovery failed")


if __name__ == "__main__":
    main()
