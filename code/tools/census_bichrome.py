"""v12 S23_bichrome input: straight-line distance (m) from every site to the nearest outcrop cell of basalt (code 3) and
of limestone/marble (code 6) on the hybrid outcrop raster (cache/outcrop_code.tif, 30 m), by Euclidean distance
transform. Writes cache/census/bichrome_dist.csv (UID, dist_basalt_m, dist_limestone_m).
  python tools/census_bichrome.py CACHE_DIR"""
import os
import sys

import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import distance_transform_edt

C = sys.argv[1]
with rasterio.open(os.path.join(C, "outcrop_code.tif")) as r:
    a = r.read(1)
    tags = r.tags()
    res = r.transform[0]
assert "3=basalt" in tags["codes"] and "6=limestone/marble" in tags["codes"], tags
s = pd.read_csv(os.path.join(C, "sites_haul.csv"), usecols=["UID", "row", "col"])
out = {"UID": s.UID}
for code, nm in ((3, "dist_basalt_m"), (6, "dist_limestone_m")):
    d = distance_transform_edt(a != code).astype(np.float32) * res
    out[nm] = d[s.row.to_numpy(), s.col.to_numpy()]
    del d
os.makedirs(os.path.join(C, "census"), exist_ok=True)
pd.DataFrame(out).to_csv(os.path.join(C, "census", "bichrome_dist.csv"), index=False)
print(pd.DataFrame(out).describe())
