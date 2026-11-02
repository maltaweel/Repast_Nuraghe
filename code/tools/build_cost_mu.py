"""Rebuild the 8-direction sledge-drag cost raster for any friction coefficient mu, from the DEM.

  python tools/build_cost_mu.py config.yaml MU OUT.tif
  python tools/build_cost_mu.py config.yaml 0.3 --check      # prove the rebuild == delivered int raster

Same arithmetic as costsurface/build_drag8.py (float32 throughout):
  t = clip((z_nb - z) / d, -1, 1);  cost = max(0.5, |mu + t| / mu) * d;  d = 30 or 42.43 m
then rounded with np.rint (the rule that produced the delivered *_int.tif: 0 mismatches on test).
The float raster is never written: each band is built in memory, rounded, written, freed.
Output dtype: uint8 if the largest possible value (t = 1, diagonal) fits in 255, else uint16. Nodata = 0.
"""
import os
import sys

import numpy as np
import rasterio

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config, peak_rss_mb  # noqa: E402

DIRS = [("N", -1, 0), ("NE", -1, 1), ("E", 0, 1), ("SE", 1, 1), ("S", 1, 0), ("SW", 1, -1), ("W", 0, -1), ("NW", -1, -1)]


def band_cost(z, dr, dc, res, mu):
    H, W = z.shape
    nb = np.full_like(z, np.nan)
    rs = slice(max(0, -dr), H - max(0, dr)); cs = slice(max(0, -dc), W - max(0, dc))
    rd = slice(max(0, dr), H - max(0, -dr) if max(0, -dr) else H); cd = slice(max(0, dc), W - max(0, -dc) if max(0, -dc) else W)
    nb[rs, cs] = z[rd, cd]
    d = res * (2 ** 0.5 if dr and dc else 1.0)
    t = np.clip((nb - z) / d, -1, 1)
    del nb
    c = (np.maximum(0.5, np.abs(mu + t) / mu) * d).astype("float32")
    return c                                   # NaN where either cell is nodata


def build(cfg, mu, out):
    dem = os.path.join(cfg["data_dir"], cfg["lit_scenarios"]["dem"])
    with rasterio.open(dem) as r:
        z = r.read(1).astype("float32"); prof = r.profile; nod = r.nodata; res = r.res[0]
    z[(z == nod) | ~np.isfinite(z)] = np.nan
    vmax = max(0.5, (mu + 1) / mu) * res * 2 ** 0.5
    dtype = "uint8" if np.rint(vmax) <= 255 else "uint16"
    prof.update(dtype=dtype, nodata=0, count=8, compress="deflate", predictor=2, tiled=True, blockxsize=512,
                blockysize=512, BIGTIFF="IF_SAFER")
    with rasterio.open(out + ".tmp", "w", **prof) as w:
        for k, (name, dr, dc) in enumerate(DIRS, 1):
            c = band_cost(z, dr, dc, res, mu)
            ci = np.where(np.isfinite(c), np.rint(c), 0).astype(dtype)
            fin = np.isfinite(c)
            if not fin.any():                  # B11: clear error instead of .min() of an empty array
                raise ValueError(f"band {name}: no finite cost cells (DEM {dem} all nodata?)")
            assert ci[fin].min() >= 1
            w.write(ci, k)
            w.set_band_description(k, f"cost into {name} neighbour (flat-metre equivalents, mu={mu}, rounded)")
            del c, ci
        w.update_tags(mu=str(mu), recipe="max(0.5,|mu+t|/mu)*d, t clipped to [-1,1], np.rint")
    os.replace(out + ".tmp", out)
    print(f"built mu={mu} -> {out} ({dtype}, theoretical max {vmax:.1f}); peak RSS {peak_rss_mb():.0f} MB", flush=True)


def check(cfg, out):
    """Compare the rebuilt mu=0.3 raster with the delivered int raster, band by band."""
    with rasterio.open(out) as a, rasterio.open(cfg["paths"]["cost_raster"]) as b:
        assert a.shape == b.shape and a.transform == b.transform
        tot = mism = 0
        for k in range(1, 9):
            x = a.read(k); y = b.read(k)
            mism += int((x.astype(np.int32) != y.astype(np.int32)).sum()); tot += x.size
        print(f"CHECK mu=0.3 rebuild vs delivered {os.path.basename(cfg['paths']['cost_raster'])}: "
              f"{mism} mismatching cells of {tot:,d} (8 bands) -> {'IDENTICAL' if mism == 0 else 'DIFFERENT'}")
        return mism == 0


if __name__ == "__main__":
    cfg = load_config(sys.argv[1])
    mu = float(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3] == "--check":
        out = os.path.join(cfg["paths"]["cache_dir"], "check_mu0.3_rebuild.tif")
        build(cfg, mu, out)
        ok = check(cfg, out)
        os.remove(out)
        sys.exit(0 if ok else 1)
    build(cfg, mu, sys.argv[3])
