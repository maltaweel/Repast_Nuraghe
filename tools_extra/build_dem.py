"""DEM input of the model from the Copernicus DEM GLO-30 tiles (open AWS bucket, no login).

    python tools_extra/build_dem.py TILES_DIR DATA_DIR/dem/sardinia_dem_GLO30_25832.tif \
        --mask region  REGION.shp          # public mask (default in notebooks/fetch_data.py), see below
        --mask basins  BASINS.shp          # the mask of the run (not public, see below)
        [--compare RUN_COPY.tif]

TILES_DIR holds the 8 GLO-30 tiles that cover Sardinia (1 x 1 degree, EPSG:4326, float32, 3600 x 3600 cells):

    Copernicus_DSM_COG_10_N{38,39,40,41}_00_E{008,009}_00_DEM.tif
    https://copernicus-dem-30m.s3.amazonaws.com/<name>/<name>.tif   (notebooks/fetch_data.py downloads and checks them)

Recipe (the steps that produced the run's copy on 14 Oct 2026, unchanged):
  1. rasterio.merge.merge of the tiles in sorted file-name order; written as an intermediate GeoTIFF with the
     profile of the first tile;
  2. reprojection to EPSG:25832 at 30 m: grid from rasterio.warp.calculate_default_transform(..., resolution=30) on
     the mosaic bounds, bilinear resampling, float32, nodata -9999;
  3. land mask: cells outside (mask polygons buffered by 300 m, unioned) set to -9999 (rasterio.mask.mask), and the
     raster cropped to the window of the run's grid: 4808 x 9080 cells, origin (426289.5532690119,
     4573835.402742416), i.e. columns 470.. and rows 2548.. of the step-2 grid.

The mask is the only step that cannot be repeated exactly from public sources. The run used the 317 regional river
catchments (RAS layer, as held in a project database; not distributed with this repository): `--mask basins` with
that layer gives the run's file. Public substitute (default): the regional boundary of Sardinia, RAS "Limite
amministrativo regionale CTR", https://webgis.regione.sardegna.it/scaricocartografiaETL/limitiAmministrativi/
limiteAmministrRegionale/limiteAmministrReg_CTR.zip. Both masks, buffered by 300 m, cover about 24,550-24,610 km2
and differ by about 75 km2, almost all sea cells next to the coast (z ~ 0, which the model already treats as
sea: land = z > 0). With the public mask the file is therefore NOT byte-identical to the run's copy (SHA-256 in
notebooks/inputs_manifest.csv); `--compare` reports how many cells differ and by how much.

Byte identity also needs the same GDAL / rasterio build (the run: rasterio 1.5.2, GDAL 3.12.2). Peak memory about
1.5 GB (the mosaic is 7200 x 14400 float32).
"""
import argparse
import glob
import hashlib
import os
import sys
import tempfile

import numpy as np

TILES = [f"Copernicus_DSM_COG_10_N{la}_00_E{lo}_00_DEM" for la in (38, 39, 40, 41) for lo in ("008", "009")]
URL = "https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"
RUN_GRID = dict(width=4808, height=9080, x0=426289.5532690119, y0=4573835.402742416, res=30.0, col_off=470,
                row_off=2548)


def mask_shape(kind, path):
    import geopandas as gpd
    g = gpd.read_file(path).to_crs(25832)
    return [g.buffer(300).union_all()]


def build(tiles_dir, out, mask_kind, mask_path, workdir=None):
    import rasterio
    from rasterio.mask import mask
    from rasterio.merge import merge
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    files = sorted(glob.glob(os.path.join(tiles_dir, "Copernicus*.tif")))
    names = sorted(os.path.splitext(os.path.basename(f))[0] for f in files)
    if names != sorted(TILES):
        raise SystemExit(f"expected the 8 tiles {TILES} in {tiles_dir}, found {names}")
    work = workdir or tempfile.mkdtemp(prefix="dem_")
    mos, utm = os.path.join(work, "mosaic.tif"), os.path.join(work, "utm.tif")
    # 1. mosaic
    src = [rasterio.open(f) for f in files]
    m, t = merge(src)
    prof = src[0].profile
    prof.update(height=m.shape[1], width=m.shape[2], transform=t, driver="GTiff")
    with rasterio.open(mos, "w", **prof) as d:
        d.write(m)
    for s in src:
        s.close()
    del m
    print("1. mosaic", prof["width"], "x", prof["height"], flush=True)
    # 2. reprojection
    with rasterio.open(mos) as s:
        tr, w, h = calculate_default_transform(s.crs, "EPSG:25832", s.width, s.height, *s.bounds, resolution=30)
        p = s.profile.copy()
        p.update(crs="EPSG:25832", transform=tr, width=w, height=h, nodata=-9999, dtype="float32", compress="deflate",
                 tiled=True, predictor=3, BIGTIFF="IF_SAFER")
        with rasterio.open(utm, "w", **p) as d:
            reproject(rasterio.band(s, 1), rasterio.band(d, 1), resampling=Resampling.bilinear, dst_nodata=-9999)
    col = (RUN_GRID["x0"] - tr.c) / 30.0
    row = (tr.f - RUN_GRID["y0"]) / 30.0
    print(f"2. EPSG:25832 grid {w} x {h}; run window at column {col:.6f}, row {row:.6f}", flush=True)
    if abs(col - RUN_GRID["col_off"]) > 1e-6 or abs(row - RUN_GRID["row_off"]) > 1e-6:
        raise SystemExit("the reprojected grid is not aligned with the run's grid (different rasterio/GDAL?)")
    # 3. mask + crop to the run window
    shape = mask_shape(mask_kind, mask_path)
    with rasterio.open(utm) as s:
        if mask_kind == "basins":                       # the run's call: crop to the mask bounds
            o, ot = mask(s, shape, crop=True, nodata=-9999)
        else:                                           # public mask: same masking, crop to the run window
            o, ot = mask(s, shape, crop=False, nodata=-9999)
            r0, c0 = RUN_GRID["row_off"], RUN_GRID["col_off"]
            o = o[:, r0:r0 + RUN_GRID["height"], c0:c0 + RUN_GRID["width"]]
            ot = s.window_transform(rasterio.windows.Window(c0, r0, RUN_GRID["width"], RUN_GRID["height"]))
        p = s.profile
        p.update(height=o.shape[1], width=o.shape[2], transform=ot)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with rasterio.open(out, "w", **p) as d:
            d.write(o)
    if (o.shape[2], o.shape[1]) != (RUN_GRID["width"], RUN_GRID["height"]) or \
            abs(ot.c - RUN_GRID["x0"]) > 1e-6 or abs(ot.f - RUN_GRID["y0"]) > 1e-6:
        print("WARNING: the output grid differs from the run's grid", (o.shape, tuple(ot)[:6]))
    v = o[0][o[0] != -9999]
    print(f"3. wrote {out}: {o.shape[2]} x {o.shape[1]}, mask '{mask_kind}', z {v.min():.1f} .. {v.max():.1f} m")
    for f in (mos, utm):
        os.remove(f)
    return out


def compare(new, ref):
    import rasterio
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    same = sha(new) == sha(ref)
    print("byte-identical to the reference copy:", same)
    with rasterio.open(new) as a, rasterio.open(ref) as b:
        if (a.width, a.height, tuple(a.transform)) != (b.width, b.height, tuple(b.transform)):
            print("grid differs:", (a.width, a.height, tuple(a.transform)[:6]), (b.width, b.height, tuple(b.transform)[:6]))
            return False
        za, zb = a.read(1), b.read(1)
    na, nb = za == -9999, zb == -9999
    both = ~na & ~nb
    d = np.abs(za[both] - zb[both])
    print(f"cells: nodata only in new {int((na & ~nb).sum()):,d} (of which land z>0 in the reference "
          f"{int((na & ~nb & (zb > 0)).sum()):,d}); nodata only in reference {int((nb & ~na).sum()):,d} (land z>0 in new "
          f"{int((nb & ~na & (za > 0)).sum()):,d}); valid in both {int(both.sum()):,d}, max |dz| {d.max() if d.size else 0:.6f} m")
    return same


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tiles_dir")
    ap.add_argument("out")
    ap.add_argument("--mask", nargs=2, metavar=("KIND", "SHP"), required=True,
                    help="KIND = region (public RAS regional boundary) or basins (the run's catchment layer)")
    ap.add_argument("--workdir", help="folder for the two intermediate rasters (default: a temporary folder)")
    ap.add_argument("--compare", help="the run's copy of sardinia_dem_GLO30_25832.tif (optional check)")
    a = ap.parse_args()
    if a.mask[0] not in ("region", "basins"):
        ap.error("--mask KIND must be 'region' or 'basins'")
    build(a.tiles_dir, a.out, a.mask[0], a.mask[1], a.workdir)
    if a.compare:
        compare(a.out, a.compare)
