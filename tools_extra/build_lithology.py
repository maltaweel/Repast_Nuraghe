"""Lithology input of the model from the official ARPAS download (Carta Litologica della Sardegna 1:25,000, 2019).

    python tools_extra/build_lithology.py carta_litologica_2019.zip DATA_DIR/geology/sardinia_lithology_25832.shp \
        [--classes data/lithology_STONE_classes.csv] [--chunk 4000]

Input: the zip served by Sardegna Geoportale
(https://webgis.regione.sardegna.it/scaricocartografiaETL/arpas/carta_litologica_2019.zip); the layer used is the
shapefile inside it, `Shapefile/carta_litologica2019.shp` (EPSG:3003, 47,780 polygons, fields OBJECTID, LIV_2,
Shape_Leng, Shape_Area), the same map units as the file geodatabase layer `Litologia_DUE_v02_2019`.

Output (the layout of data/README.md, section 3): EPSG:25832, fields
  ID          = OBJECTID (integer)
  CODE        = LIV_2 (map unit)
  DESC_IT, DESC_EN, STONE, BUILDSTONE  from data/lithology_STONE_classes.csv (the authors' STONE grouping, 36 units)
  AREA_KM2    = polygon area in EPSG:25832 / 1e6, rounded to 4 decimals
rows in ID order. Deterministic: chunked read -> reproject (pyproj default transformation EPSG:3003 -> EPSG:25832)
-> append. Memory stays below ~400 MB with the default chunk.

Comparison with the copy used for the runs (notebooks/inputs_manifest.csv): NOT byte-identical. That copy was
exported on 14 Oct 2026 from the same ARPAS map as held in a project database (same 47,780 polygons, same IDs and
map units, same vertex counts); its coordinates differ from this reprojection by about 4-5 mm (a different datum
transformation at import) and its rows are in database order. The .prj and .cpg files are byte-identical. On the
30 m grid of the model the difference is immaterial; `--compare RUN_COPY.shp` reports it.
"""
import argparse
import csv
import os
import sys
import tempfile
import zipfile

import numpy as np
import pyogrio

LAYER_IN_ZIP = "Shapefile/carta_litologica2019"


def read_classes(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["CODE"]: r for r in rows}


def build(zip_path, out, classes_csv, chunk=4000):
    import geopandas as gpd
    import pandas as pd
    cls = read_classes(classes_csv)
    tmp = tempfile.mkdtemp(prefix="lith_")
    with zipfile.ZipFile(zip_path) as z:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj"):
            n = LAYER_IN_ZIP + ext
            if n in z.namelist():
                z.extract(n, tmp)
    src = os.path.join(tmp, LAYER_IN_ZIP + ".shp")
    info = pyogrio.read_info(src)
    n = int(info["features"])
    ids = pyogrio.read_dataframe(src, columns=["OBJECTID"], read_geometry=False)["OBJECTID"].astype(int).to_numpy()
    order = np.argsort(ids, kind="stable")                         # rows in ID (= OBJECTID) order
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        p = os.path.splitext(out)[0] + ext
        if os.path.exists(p):
            os.remove(p)
    missing = set()
    for k in range(0, n, chunk):
        sel = order[k:k + chunk]
        # read the rows of this chunk (by FID) in ID order
        g = pyogrio.read_dataframe(src, fids=sel.tolist())
        g = g.set_index(g.OBJECTID.astype(int)).loc[ids[sel]].reset_index(drop=True)
        g = g.to_crs(25832)
        codes = g["LIV_2"].astype(str)
        missing |= set(codes) - set(cls)
        df = gpd.GeoDataFrame({
            "ID": g["OBJECTID"].astype("int64").to_numpy(),
            "CODE": codes.to_numpy(),
            "DESC_IT": [cls.get(c, {}).get("DESC_IT", "") for c in codes],
            "DESC_EN": [cls.get(c, {}).get("DESC_EN", "") for c in codes],
            "STONE": [cls.get(c, {}).get("STONE", "") for c in codes],
            "BUILDSTONE": [int(cls.get(c, {}).get("BUILDSTONE", 0) or 0) for c in codes],
            "AREA_KM2": (g.geometry.area / 1e6).round(4).to_numpy(),
        }, geometry=g.geometry.values, crs=g.crs)
        pyogrio.write_dataframe(df, out, encoding="utf-8", append=k > 0)
        print(f"  {min(k + chunk, n):,d} / {n:,d} polygons", flush=True)
        del g, df
    if missing:
        raise SystemExit(f"map units without a STONE class in {classes_csv}: {sorted(missing)}")
    print("wrote", out)
    return out


def compare(new, run_copy, chunk=4000):
    """Feature count, IDs/CODEs, vertex counts and coordinate offsets: new build vs the run's copy (matched by ID)."""
    import shapely
    a = pyogrio.read_dataframe(new, read_geometry=False)
    b = pyogrio.read_dataframe(run_copy, read_geometry=False)
    print(f"features: new {len(a):,d}, run copy {len(b):,d}")
    ja = a.set_index("ID"); jb = b.set_index("ID")
    same_ids = set(ja.index) == set(jb.index)
    print("same IDs:", same_ids)
    if not same_ids:
        return False
    jb = jb.loc[ja.index]
    for c in ("CODE", "STONE", "BUILDSTONE"):
        print(f"{c} equal per ID: {(ja[c].astype(str).to_numpy() == jb[c].astype(str).to_numpy()).mean():.6f}")
    print(f"AREA_KM2 max abs diff: {np.abs(ja.AREA_KM2.to_numpy() - jb.AREA_KM2.to_numpy()).max():.4f} km2")
    pos_b = {int(v): i for i, v in enumerate(b.ID.to_numpy())}
    worst, nv_bad = 0.0, 0
    for k in range(0, len(a), chunk):
        ga = pyogrio.read_dataframe(new, skip_features=k, max_features=chunk)
        fb = [pos_b[int(v)] for v in ga.ID.to_numpy()]
        gb = pyogrio.read_dataframe(run_copy, fids=fb)
        for x, y in zip(ga.geometry.values, gb.geometry.values):
            cx, cy = shapely.get_coordinates(x), shapely.get_coordinates(y)
            if len(cx) != len(cy):
                nv_bad += 1
                continue
            worst = max(worst, float(np.abs(cx - cy).max()))
    print(f"polygons with a different vertex count: {nv_bad}; max coordinate offset where equal: {worst:.4f} m")
    return nv_bad == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip")
    ap.add_argument("out")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--classes", default=os.path.join(here, "..", "data", "lithology_STONE_classes.csv"))
    ap.add_argument("--chunk", type=int, default=4000)
    ap.add_argument("--compare", help="the run's copy of sardinia_lithology_25832.shp (optional check)")
    a = ap.parse_args()
    build(a.zip, a.out, a.classes, a.chunk)
    if a.compare:
        sys.exit(0 if compare(a.out, a.compare, a.chunk) else 1)
