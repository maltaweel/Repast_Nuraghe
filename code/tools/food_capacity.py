"""S12 (1 Nov 2026) input: land of each nuraghe's catchment by land-capability class.

  python tools/food_capacity.py config.yaml --soils soils250k.geojson --radius 2000 --out CACHE/food/site_food.csv

Catchment = the site's Thiessen (Voronoi) polygon among all nuraghi, clipped to a circle of `radius` m (sites share
land with their nearest neighbours; isolated sites are limited by the radius). Land = the 1:250,000 soil map of
Sardinia (Aru, Baldaccini & Vacca 1991, RAS/AGRIS; field CLASSI = land-capability class(es) of the mapping unit).
A unit listing several classes ("VII - VI - IV") is split equally among them. Units without classes: 'urban'
(modern built-up land, unknown in prehistory) and 'water'. Sites at identical coordinates share their polygon equally.
Output: UID, catch_ha, ha_I .. ha_VIII, ha_urban, ha_water (hectares). The yields and shares that turn hectares into
food are scenario parameters (config alliance_extra ... food_cap), not baked in here.
"""
import argparse
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

CLASSES = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def unit_classes(classi, substrato):
    c = [x.strip() for x in str(classi).split("-") if x.strip()]
    if c:
        assert all(x in CLASSES for x in c), classi
        return c
    return ["water"] if str(substrato).strip().lower().startswith("acque") else ["urban"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--soils", required=True)
    ap.add_argument("--radius", type=float, default=2000.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    base = os.path.dirname(os.path.abspath(a.config))
    cache = cfg["paths"]["cache_dir"]
    cache = cache if os.path.isabs(cache) else os.path.join(base, cache)
    h = pd.read_csv(os.path.join(cache, "sites_haul.csv"))[["UID", "x", "y"]]
    crs = cfg["crs"]
    soils = gpd.read_file(a.soils).to_crs(crs)
    soils["cls"] = [unit_classes(c, s) for c, s in zip(soils.CLASSI, soils.SUBSTRATO)]
    # Thiessen polygons of the unique site locations, clipped to the radius around each location
    xy = h[["x", "y"]].round(3)
    key = list(zip(xy.x, xy.y))
    uniq = list(dict.fromkeys(key))
    pts = shapely.points(np.array(uniq))
    env = shapely.box(*shapely.bounds(shapely.multipoints(pts))).buffer(5 * a.radius)
    vor = shapely.get_parts(shapely.voronoi_polygons(shapely.multipoints(pts), extend_to=env))
    tree = shapely.STRtree(vor)
    pi, vi = tree.query(pts, predicate="within")
    owner = np.full(len(pts), -1)
    owner[pi] = vi
    assert (owner >= 0).all(), "a site without a Voronoi cell"
    cells = gpd.GeoDataFrame({"loc": np.arange(len(pts))},
                             geometry=shapely.intersection(vor[owner], shapely.buffer(pts, a.radius, quad_segs=32)),
                             crs=crs)
    ov = gpd.overlay(cells, soils[["cls", "geometry"]], how="intersection", keep_geom_type=True)
    ov["ha"] = ov.area / 1e4
    rows = np.zeros((len(pts), len(CLASSES) + 2))
    cols = CLASSES + ["urban", "water"]
    for loc, cl, ha in zip(ov["loc"], ov["cls"], ov["ha"]):
        for c in cl:
            rows[loc, cols.index(c)] += ha / len(cl)
    n_at = pd.Series(key).map(pd.Series(key).value_counts()).to_numpy()   # sites sharing a location
    loc_index = {k: j for j, k in enumerate(uniq)}
    loc_of = np.array([loc_index[k] for k in key])
    out = pd.DataFrame(rows[loc_of] / n_at[:, None], columns=["ha_" + c for c in cols])
    out.insert(0, "catch_ha", (cells.area.to_numpy() / 1e4)[loc_of] / n_at)
    out.insert(0, "UID", h.UID.to_numpy())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out.to_csv(a.out, index=False, float_format="%.4f")
    land_ha = out[["ha_" + c for c in cols]].sum(axis=1)
    print(f"wrote {a.out}: {len(out)} sites, radius {a.radius:.0f} m; catchment ha median {out.catch_ha.median():.1f} "
          f"(p5 {out.catch_ha.quantile(.05):.1f}, p95 {out.catch_ha.quantile(.95):.1f}); on the soil map "
          f"{land_ha.sum() / out.catch_ha.sum():.3f} of the catchment area; shared locations {int((n_at > 1).sum())}")
    print("island catchment ha by class:", {c: round(float(out['ha_' + c].sum())) for c in cols})


if __name__ == "__main__":
    main()
