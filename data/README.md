# Input data

**Nurnet's data** (the site list and the building stone per site) is included in this repository, in
`data/nurnet/` (`data/nurnet/README.txt`). The other inputs are public layers that are **not** redistributed here
(`.gitignore` excludes everything under `data/` except `data/nurnet/`, the README files and the lookup table
`lithology_STONE_classes.csv`): `notebooks/fetch_data.py` downloads them from the providers below and rebuilds the
files the model reads; **the same steps by hand, with commands, the folder tree and the verification:
[notebooks/HOW_TO_USE.md, "Linking the data yourself"](../notebooks/HOW_TO_USE.md#linking-the-data-yourself)**. All
files go under one folder, the `data_dir` of the configuration (`config/*.yaml`, first lines). The default notebook
layout uses this `data/` folder:

```
data/
  nurnet/                                                  Nurnet's data, included (copied to sites/ and stone/)
  sites/nurnet_nuraghi.{shp,shx,dbf,prj,cpg}               nuraghe sites (copy of nurnet/nurnet_nuraghi.*)
  stone/nid_materiale_prod.csv                             building stone per site (copy of nurnet/nurnet_site_building_stone.csv)
  geology/sardinia_lithology_25832.{shp,shx,dbf,prj,cpg}   lithology with the STONE grouping
  dem/sardinia_dem_GLO30_25832.tif                         DEM
  costsurface/sardinia_drag_cost_8dir_mu03_25832_int.tif   derived from the DEM (data/derived/README.md)
  costsurface/sardinia_slope_deg_25832.tif                 derived from the DEM (data/derived/README.md)
  soils/soils250k.geojson                                  soil map 1:250,000
  water/sardinia_rivers_25832.{shp,shx,dbf,prj,cpg}        rivers and streams
  derived/cache/                                           cached derived inputs (data/derived/README.md)
```

Set `data_dir:` in the config to the **absolute** path of this folder (some tools join it to file names without
resolving it against the config folder). `paths.sites`, `paths.lithology`, `paths.cost_raster`,
`materiale.file`, `lit_scenarios.dem`, `sea.dem` and `sea.slope` are relative to it; `tools/wl_inputs.py` reads
`water/sardinia_rivers_25832.shp` under it, and `tools/food_capacity.py` takes the soil file as `--soils`.

**Coordinate system.** Every layer the model reads is in **EPSG:25832** (ETRS89 / UTM zone 32N, metres;
config key `crs`). The rasters share one 30 m grid (the DEM grid). Layers published in another CRS (the soil map
is EPSG:4326 on its WFS) must be reprojected to EPSG:25832 before use; rasters must be resampled to the DEM grid.

SHA-256 values and sizes of the copies used for the runs are in `notebooks/inputs_manifest.csv` (group
`raw_input`); `notebooks/fetch_data.py` and `notebooks/02_inputs.ipynb` check them. Files rebuilt from the official
sources that cannot be byte-identical to the run's copies (lithology and rivers `.shp/.shx/.dbf`, DEM, cost and slope
rasters) are listed with the reason in each section below and in `notebooks/HOW_TO_USE.md`.

## 1. Nuraghe sites

| | |
|---|---|
| What | 7,167 nuraghe sites (points), with tower counts read from each record |
| File | included as `data/nurnet/nurnet_nuraghi.shp` (+ `.shx .dbf .prj .cpg`); read as `sites/nurnet_nuraghi.shp` under `data_dir` (`fetch_data.py` copies it; SHA-256 = the run's copy) |
| Fields read | `UID` (Nurnet ID, the site key everywhere), `TWR_N` (towers, mastio included), `TWR_FILL` (1 = tower count assumed), `NAME`, `COMUNE`, `TYPE` (site type), point geometry (config `site_fields`) |
| CRS | EPSG:25832 |
| How it feeds the model | one Site agent per point; the tower count sets the stone tonnage, the work party and the tower class; the point is the end of every haul and walk |
| Credit | **Nurnet's data — a Nurnet merge and deduplication of various sources** |
| Licence | see provider |
| Contact | for the latest version and source information contact Nurnet at nurnet.presidente@gmail.com |

## 2. Building stone per site (hybrid stone rule)

| | |
|---|---|
| What | the recorded building stone of each nuraghe (where known) |
| File | included as `data/nurnet/nurnet_site_building_stone.csv`; read as `stone/nid_materiale_prod.csv` under `data_dir` (`fetch_data.py` copies it; SHA-256 = the run's copy). UTF-8 CSV; the code reads the columns `codice` (= Nurnet `UID`) and `sa_materiale` (recorded stone, e.g. `Basalto`, `Granito`, `Trachite e Calcare`) |
| How it feeds the model | only `preprocess.py` reads it (stone rule `hybrid`, the rule of `config_full_audited.yaml`): a site with a recorded stone quarries that stone class (token map `materiale.map` in the config); the others the nearest outcrop of the 7 permitted classes. Model runs never read it; they read the haul tables built from it |
| Credit | **Nurnet's data** |
| Availability | included in this repository (`data/nurnet/`); for the latest version and source information contact Nurnet at nurnet.presidente@gmail.com |

`stone_rule: stones7` (nearest outcrop of the 7 permitted classes for every site) does not use this file; results
then differ from the hybrid runs.

## 3. Lithology

| | |
|---|---|
| What | ARPAS 2019, *Carta Litologica della Sardegna* 1:25,000, 47,780 polygons |
| File | `geology/sardinia_lithology_25832.shp` (+ `.shx .dbf .prj .cpg`) |
| Fields | `CODE`, `DESC_IT`, `DESC_EN` (original map units); `STONE` (the authors' grouping into potential building stones) and `BUILDSTONE` (1 unless `STONE` = none) |
| CRS / scale | EPSG:25832; 1:25,000 |
| How it feeds the model | outcrops of the permitted `STONE` classes (`allowed_stones`; field set by `lithology_field`) are rasterised on the 30 m cost grid; every haul starts at an outcrop cell |
| Credit | © Regione Autonoma della Sardegna / ARPAS |
| Licence | CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) |
| Links | Sardegna Geoportale page: https://www.sardegnageoportale.it/index.php?xsl=2420&s=40&v=9&c=94082&es=6603&na=1&n=100&esp=1&tb=14401 ; metadata record: https://webgis2.regione.sardegna.it/geonetwork/srv/api/records/R_SARDEG:7a2ce3e7-2686-4c10-8df9-3a3c0ad013f2 ; direct download (zip, ~243 MB): https://webgis.regione.sardegna.it/scaricocartografiaETL/arpas/carta_litologica_2019.zip |

The published layer has the original map units only. `lithology_STONE_classes.csv` (in this folder) lists the
mapping of each map unit (`CODE`) to `STONE` and `BUILDSTONE` as used in the runs (36 units).
`tools_extra/build_lithology.py ZIP OUT.shp` reads `Shapefile/carta_litologica2019.shp` inside the zip (EPSG:3003,
47,780 polygons, fields `OBJECTID`, `LIV_2`), reprojects it to EPSG:25832 and writes `ID` (= `OBJECTID`), `CODE`
(= `LIV_2`), `DESC_IT`, `DESC_EN`, `STONE`, `BUILDSTONE` and `AREA_KM2`. Compared with the run's copy (exported on
14 Oct 2026 from the same map as held in a project database): same polygons, IDs, map units and vertex counts, `.prj`
and `.cpg` identical, coordinates within 5 mm, rows in another order; so `.shp/.shx/.dbf` are not byte-identical.

## 4. DEM

| | |
|---|---|
| What | Copernicus DEM GLO-30 (about 30 m), mosaicked, reprojected to EPSG:25832 at 30 m and clipped to Sardinia; one band, float32, nodata −9999 |
| File | `dem/sardinia_dem_GLO30_25832.tif` |
| CRS / resolution | EPSG:25832, 30 m |
| How it feeds the model | the drag-cost rasters for every friction coefficient and the slope raster (data/derived/README.md); land/sea and landings for sea transport (`tools/sea_routes.py`); route checks (`tests/verify_hauls.py`); the island outline in maps |
| Credit | **Copernicus DEM, © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA** |
| Licence | Copernicus DEM licence (see provider) |
| Link | https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM ; open AWS bucket (no login): `https://copernicus-dem-30m.s3.amazonaws.com/<tile>/<tile>.tif` for the 8 tiles `Copernicus_DSM_COG_10_N{38,39,40,41}_00_E{008,009}_00_DEM` |
| Rebuild | `tools_extra/build_dem.py TILES_DIR OUT.tif --mask region limiteAmministrRegionale_CTR.shp`: the run's recipe (mosaic, reprojection to EPSG:25832 at 30 m, bilinear, sea masked outside the land polygons buffered by 300 m, the run's 4808 x 9080 grid). The run masked with the regional river catchments as held in a project database (not public); the public mask is the RAS regional boundary (https://webgis.regione.sardegna.it/scaricocartografiaETL/limitiAmministrativi/limiteAmministrRegionale/limiteAmministrReg_CTR.zip), so the file is not byte-identical (about 75 km2 of mostly coastal sea cells differ) |

## 5. Soils (land capability)

| | |
|---|---|
| What | Aru, A., Baldaccini, P. and Vacca, A. 1991. *Carta dei suoli della Sardegna* 1:250,000 (RAS/AGRIS); field `CLASSI` = land-capability class(es) of each mapping unit |
| File | `soils/soils250k.geojson` (WFS layer `Agris:carta_dei_suoli_sardegna_scala_250000`, published in EPSG:4326; GetFeature request, `outputFormat=application/json&srsName=EPSG:4326`, in `notebooks/HOW_TO_USE.md`). Byte-identical to the run's copy once the GeoServer `"timeStamp"` field is set back to that of the run's copy (`fetch_data.py` does it) |
| CRS / scale | 1:250,000; reprojected to EPSG:25832 by the tools that read it |
| How it feeds the model | `tools/food_capacity.py` builds each site's catchment by land-capability class (`derived/cache/food/site_food_r*.csv`), used by the food-capacity scenarios (S12) and the work-feast variant; `tools/pattern_checks.py` reads it for a post hoc check |
| Credit | Aru, Baldaccini & Vacca 1991, Regione Autonoma della Sardegna / AGRIS |
| Licence | CC BY (see provider) |
| Links | https://www.sardegnaportalesuolo.it/ ; WFS: https://geoserver.sardegnaportalesuolo.it/geoserver/wfs?service=WFS&request=GetCapabilities |

## 6. Rivers

| | |
|---|---|
| What | Regione Autonoma della Sardegna river and stream network, layer `fiumitorrenti` (41,877 line segments; the modern network, used as a proxy for Bronze Age water courses) |
| File | `water/sardinia_rivers_25832.shp` (+ `.shx .dbf .prj .cpg`), fields `ID`, `LEN_M` |
| CRS | EPSG:25832 |
| How it feeds the model | `tools/wl_inputs.py`: distance of every route move and site to the nearest stream (rasterised on the DEM grid), for the wet-ground haul variants (M3) of the wider-literature scenarios (`derived/cache/alliance/kbest_wl.npz`) |
| Credit | Regione Autonoma della Sardegna |
| Licence | see provider |
| Link | Sardegna Geoportale, catalogue record "PPR06 - Fiumi torrenti e altri corsi d'acqua (Elementi lineari)" (R_SARDEG:PKLBJ, https://webgis2.regione.sardegna.it/geonetwork/srv/ita/catalog.search); direct download (zip, 10 MB): https://webgis.regione.sardegna.it/scaricocartografiaETL/ppr/fiumiTorrenti_ARC.zip |
| Rebuild | `tools_extra/build_rivers.py ZIP OUT.shp` (EPSG:3003 -> EPSG:25832, `ID` = `idFeature`, `LEN_M`). Compared with the run's copy (exported on 14 Oct 2026 from the same layer as held in a project database): same 41,877 segments, IDs and vertices, `.prj` and `.cpg` identical, coordinates within 5 mm, rows in another order; so `.shp/.shx/.dbf` are not byte-identical |

## 7. Derived inputs

The cost and slope rasters above and everything under `derived/cache/` are computed from these datasets by the
code in this repository: see `derived/README.md`.

## URL check

Every link above was checked on 2 November 2026 with `curl -sIL` (HTTP 200 after redirects); every download of
`notebooks/fetch_data.py` was tested the same day (the soils, rivers, lithology and the 8 DEM tiles in full).
