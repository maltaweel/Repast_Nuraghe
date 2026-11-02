"""Slope raster (degrees) on the DEM grid: the `sea.slope` input (beach rule of tools/sea_routes.py).

    python tools_extra/build_slope.py DATA_DIR/dem/sardinia_dem_GLO30_25832.tif DATA_DIR/costsurface/sardinia_slope_deg_25832.tif

Not part of the frozen code snapshot (code/): the slope band of the project's cost-surface script, with the input
and output paths as arguments. Same arithmetic: float32 DEM, nodata and non-finite cells masked, central-difference
gradient (numpy.gradient with the cell sizes), slope = degrees(arctan(|grad z|)), nodata -9999, deflate-compressed
512 x 512 tiles. Holds the whole island in memory (a few GB).
"""
import sys

import numpy as np
import rasterio

src, dst = sys.argv[1], sys.argv[2]
with rasterio.open(src) as r:
    z = r.read(1).astype("float32"); prof = r.profile; nod = r.nodata; res = r.res
mask = (z == nod) | ~np.isfinite(z)
zf = np.where(mask, np.nan, z)
gy, gx = np.gradient(zf, res[1], res[0])   # gy along rows (north -> south since row 0 is north)
t = np.hypot(gx, gy).astype("float32")
del gx, gy
slope_deg = np.degrees(np.arctan(t)).astype("float32")
prof.update(dtype="float32", nodata=-9999, compress="deflate", predictor=3, tiled=True, blockxsize=512, blockysize=512, count=1)
a = slope_deg.copy(); a[mask | ~np.isfinite(a)] = -9999
with rasterio.open(dst, "w", **prof) as w:
    w.write(a, 1); w.set_band_description(1, "slope, degrees")
print("wrote", dst)
