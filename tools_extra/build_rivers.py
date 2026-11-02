"""River network input of the model from the official RAS download (PPR 2006, 'Fiumi torrenti e altri corsi d'acqua').

    python tools_extra/build_rivers.py fiumiTorrenti_ARC.zip DATA_DIR/water/sardinia_rivers_25832.shp [--compare RUN_COPY.shp]

Input: the zip served by Sardegna Geoportale (catalogue record "PPR06 - Fiumi torrenti e altri corsi d'acqua (Elementi
lineari)", R_SARDEG:PKLBJ): https://webgis.regione.sardegna.it/scaricocartografiaETL/ppr/fiumiTorrenti_ARC.zip
(fiumiTorrenti_ARC.shp, EPSG:3003, 41,877 line segments, fields idFeature, nome, lunghezza).

Output (data/README.md, section 6): EPSG:25832, fields ID (= idFeature) and LEN_M (segment length in EPSG:25832,
rounded to 0.1 m), rows in ID order. Deterministic; about 250 MB of memory.

Comparison with the copy used for the runs (notebooks/inputs_manifest.csv): NOT byte-identical. That copy was
exported on 14 Oct 2026 from the same RAS layer as held in a project database ('fiumitorrenti'): same 41,877
segments, same IDs, same vertices (the .shp and .shx have the same size), coordinates within 5 mm of this
reprojection (a different datum transformation at import) and rows in database order. The .cpg is byte-identical.
tools/wl_inputs.py only rasterises the distance to the nearest stream on the 30 m grid, so the difference is
immaterial; `--compare` reports it.
"""
import argparse
import os
import sys
import tempfile
import zipfile

import numpy as np

STEM = "fiumiTorrenti_ARC"


def build(zip_path, out):
    import geopandas as gpd
    tmp = tempfile.mkdtemp(prefix="rivers_")
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.startswith(STEM + "."):
                z.extract(n, tmp)
    g = gpd.read_file(os.path.join(tmp, STEM + ".shp"))
    g = g.sort_values("idFeature", kind="stable").reset_index(drop=True).to_crs(25832)
    o = gpd.GeoDataFrame({"ID": g["idFeature"].astype("int64").to_numpy(),
                          "LEN_M": g.geometry.length.round(1).to_numpy()}, geometry=g.geometry.values, crs=g.crs)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    o.to_file(out, encoding="utf-8")
    print(f"wrote {out}: {len(o):,d} segments, {o.LEN_M.sum() / 1e3:,.1f} km")
    return out


def compare(new, run_copy):
    import geopandas as gpd
    import shapely
    a = gpd.read_file(new).sort_values("ID").reset_index(drop=True)
    b = gpd.read_file(run_copy).sort_values("ID").reset_index(drop=True)
    print(f"segments: new {len(a):,d}, run copy {len(b):,d}; same IDs: {a.ID.tolist() == b.ID.tolist()}")
    ca, cb = shapely.get_coordinates(a.geometry.values), shapely.get_coordinates(b.geometry.values)
    if len(ca) != len(cb):
        print(f"vertex count differs: {len(ca):,d} vs {len(cb):,d}")
        return False
    print(f"vertices {len(ca):,d}; max coordinate offset {np.abs(ca - cb).max():.4f} m; "
          f"LEN_M max abs diff {np.abs(a.LEN_M - b.LEN_M).max():.1f} m; "
          f"total {a.LEN_M.sum() / 1e3:,.3f} vs {b.LEN_M.sum() / 1e3:,.3f} km")
    return bool(np.abs(ca - cb).max() < 0.05)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip")
    ap.add_argument("out")
    ap.add_argument("--compare", help="the run's copy of sardinia_rivers_25832.shp (optional check)")
    a = ap.parse_args()
    build(a.zip, a.out)
    if a.compare:
        sys.exit(0 if compare(a.out, a.compare) else 1)
