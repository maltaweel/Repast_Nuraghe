# How to use the notebooks and link the data

Six notebooks reproduce and audit the model, in this order. They run the v17 code (`code/`, `CODE_VERSION`
2026-11-09-v17: lift, every lift rule, priced at the undiscounted rate; the learning factor and skill act on
quarrying, dressing and building only; ODD 7.9) with the configuration of the v17 runs,
`config/v16_final/config_full_audited.yaml` (the audited `config/config_full_audited.yaml` with
`quarry.near_site_fixed_face_m: 1000` and `transport.min_haul_flatm: 15`). The notebooks contain no model results:
every number they show is computed when you run them; the results of the full runs are a separate data input (the
results package).

| # | notebook | what it does | expected result |
|---|---|---|---|
| 1 | `01_setup.ipynb` | installs OpenMPI and the pinned Python packages, checks the versions, runs a 2-rank MPI smoke test, imports the model code, checks the code version and runs the v17 lift unit tests | `pinned packages: 35; mismatches: 0`, `rank 0 of 2` / `rank 1 of 2`, `model code imports OK`, `code version 2026-11-09-v17`, `9 tests passed` |
| 2 | `02_inputs.ipynb` | gets every input (section 0: `fetch_data.py`), checks it against `inputs_manifest.csv`, sets the stone rule, gets the derived inputs (pack or rebuild), writes the work folder | a fetch table with `0 failed/differing`; `derived inputs ...: 68 of 68 present`; `work folder ready` |
| 3 | `03_scenarios.ipynb` | runs scenarios with `code/model.py` (repast4py + MPI), including the headline `MOST_REALISTIC_AUDITED_LIT_P10`: presets `demo` (30 sites, seed 1, about a minute), `quick` (300 sites, seeds 1-3), `full`, `custom` | island totals per scenario |
| 4 | `04_analysis_report.ipynb` | tables per tower class, maps of man-hours, centrality of the help networks, network need | tables and maps |
| 5 | `05_audit.ipynb` | the step-by-step audit: (a) code vs the run's v17 checksums (`CODE_V17_SHA256SUMS`), (b) inputs vs the manifest, (c) configuration vs the parameter trace (one documented change since the audit: minimum haul 100 -> 15 m), (d) a fixed rerun vs a fingerprint, (e) the headline numbers from the per-seed tables of the results | (a)-(c) PASS; (d), (e) NOT YET AVAILABLE until the fingerprint and the tables are supplied, then PASS |
| 6 | `06_sensitivity.ipynb` | the sensitivity steps at demo size: the A5 alliance grid (27 cells + A0_alone, `sensitivity.csv`), a Morris screen and a Sobol design / analysis of the headline (`notebooks/sensitivity.py`, SALib); regenerates the full designs (Morris 330 evaluations, Sobol 14,336) for comparison with the design files of the results package | a 27-row `sensitivity.csv`, mu* per factor and output, S1 / ST per factor and output (demo values: they only show that the chain works) |

Contents: [Run in Google Colab](#run-in-google-colab) - [Run in Jupyter](#run-in-jupyter-on-your-own-machine) -
[Software requirements](#software-requirements) - [Getting the data](#getting-the-data) -
[Linking the data yourself](#linking-the-data-yourself) - [Nurnet files](#nurnet-files) -
[Derived inputs](#derived-inputs) - [Troubleshooting](#troubleshooting)

## Run in Google Colab

1. Open the notebooks from the links in [README.md](README.md#open-in-google-colab) (01 to 06, in order).
2. In the **config cell** of every notebook (the only cell you edit) set the same Drive folders, because each
   Colab notebook runs in its own runtime (a file written by 02 in `/content` is not visible to 03):
   ```python
   MOUNT_DRIVE = True
   DATA_DIR = "/content/drive/MyDrive/Repast_Nuraghe/data"
   DERIVED_DIR = "/content/drive/MyDrive/Repast_Nuraghe/data/derived/cache"
   OUTPUTS_DIR = "/content/drive/MyDrive/Repast_Nuraghe/outputs"
   ```
3. Run all cells (Runtime > Run all). The setup cell clones the repository to `/content/Repast_Nuraghe` and installs
   OpenMPI and the pinned packages (several minutes the first time in each runtime). If it asks for a restart
   (a package changed version after it was imported): Runtime > Restart session, then run all again.
4. 02 downloads the public inputs into `DATA_DIR` on your Drive (about 400 MB) and copies the Nurnet files there; the
   next notebooks reuse them.
5. **Derived inputs (first time only, no setting needed):** the prebuilt pack (`DERIVED_URL`) is not public yet, so
   02 (section 0b) prints a note and rebuilds them automatically when they are missing from `DERIVED_DIR` (about
   30-45 min; see [Derived inputs](#derived-inputs)). Later runs reuse `DERIVED_DIR` on Drive. If 03 or 06 is opened
   in a runtime that does not see them (no Drive), it gets the inputs the same way before it starts.

Clean-room test: 01-06 pass with derived inputs supplied (commit a2010ed); the automatic rebuild path is being tested end to end.

Colab gives 2 vCPUs and about 12 GB of RAM: enough for the `demo` and `quick` presets, the audit, the demo
sensitivity designs and the derived-input rebuild; the `full` preset (7,167 sites, 100 seeds per scenario) takes
hours per scenario there, and the full Sobol design (43,008 whole-island runs) is not a Colab job.

## Run in Jupyter on your own machine

```bash
git clone <URL of this repository> Repast_Nuraghe
cd Repast_Nuraghe
# OpenMPI first (see Software requirements), then:
CC=mpicc CXX=mpicxx python -m pip install -r notebooks/requirements-colab.txt jupyter
jupyter notebook notebooks/
```

Open 01 to 06 in order. With the defaults (`"auto"`) the notebooks use `data/` for the raw inputs,
`data/derived/cache/` for the derived inputs and `outputs/` for everything they write. Headless:
`jupyter nbconvert --to notebook --execute notebooks/02_inputs.ipynb` (environment variables `NB_DATA_DIR`,
`NB_DERIVED_DIR`, `NB_OUTPUTS_DIR`, ... override the config cell; see the config cell of each notebook).

## Software requirements

From `code/requirements.txt` (minimum versions) and `notebooks/requirements-colab.txt` (exact versions of the tested
environment):

| what | version | notes |
|---|---|---|
| Python | 3.12 or later; tested with 3.13.5 | 3.12+ for byte-identical reproduction (built-in float `sum()` changed in 3.12); 3.10-3.11 differ in the last digits |
| MPI with compiler wrappers (`mpicc`, `mpicxx`) | OpenMPI or MPICH | Ubuntu / Debian / Colab: `sudo apt-get install -y openmpi-bin libopenmpi-dev`; macOS: `brew install open-mpi`; Windows: use WSL2 (Ubuntu) and the Ubuntu command; conda: `conda install -c conda-forge openmpi mpi4py` |
| repast4py | >= 1.1.6; tested 1.3.1 | Collier, N. and Ozik, J. 2022. Distributed agent-based simulation with Repast4Py. *Proceedings of the 2022 Winter Simulation Conference*. doi:[10.1109/WSC57314.2022.10015389](https://doi.org/10.1109/WSC57314.2022.10015389). Install guide: https://repast.github.io/repast4py.site/ (compiles against MPI: `CC=mpicxx CXX=mpicxx pip install repast4py`) |
| mpi4py | >= 3.1; tested 4.1.2 | compiles against MPI |
| numpy | >= 1.24; tested 2.5.4 | |
| numba | >= 0.58; tested 0.68.0 (llvmlite 0.50.0) | |
| pandas | >= 2.0; tested 3.0.6 | |
| geopandas | >= 0.14; tested 1.2.0 (shapely 2.2.0, pyproj 3.8.0) | |
| pyogrio | >= 0.7; tested 0.13.0 | |
| rasterio | >= 1.3; tested 1.5.2 | |
| pyyaml | >= 6.0; tested 6.0.3 | |
| SALib | 1.6.0 (multiprocess 0.70.19) | Morris and Sobol designs and indices (06_sensitivity) |
| also pinned in `requirements-colab.txt` | scipy 1.18.1, matplotlib 3.11.2, networkx 3.7, reportlab 5.1.0, cython 3.3.0 and their dependencies | used by the analysis tools and the notebooks |

- **GDAL**: no system installation needed; the pip wheels of rasterio and pyogrio include GDAL (the environment of the
  runs: GDAL 3.12.2 inside rasterio 1.5.2). The DEM rebuild is byte-identical only with the same GDAL / rasterio.
- **torch** is not pinned: repast4py imports it, the model never uses it (every random draw is numpy's PCG64,
  `default_rng([seed, site id, ...])`). On Colab the preinstalled torch is kept.
- **Install commands**: `CC=mpicc CXX=mpicxx python -m pip install -r notebooks/requirements-colab.txt` (exact) or
  `CC=mpicxx CXX=mpicxx python -m pip install -r code/requirements.txt` (minimum versions). `01_setup.ipynb` does the
  same in one cell (apt-get for OpenMPI when it runs as root, as on Colab) and then runs the 2-rank MPI smoke test.
- **Memory** (measured on the 8 GB machine of the runs): one 100-seed run of the headline scenario on 6 MPI ranks
  takes about 6 minutes and peaks at about 6 GB (proportional set size 5.9 GB; resident 7.6 GB; largest rank 2.8 GB).
  An alliance run holds the whole island on every rank: plan 1-3 GB per rank. The derived-input rebuild runs one
  process at a time with a peak of about 2.5 GB; the DEM build about 1.5 GB.
- **Disk**: raw inputs about 0.5 GB (plus about 0.4 GB of kept downloads), derived inputs about 0.75 GB, the part
  files of one 100-seed headline scenario about 0.25 GB; the full audited queue (448 entries) several GB.
- **Time**: the full audited queue was estimated at about 34 hours of wall time on that machine (top-level README).

## Getting the data

**Automatic** (recommended): `02_inputs.ipynb`, section 0, or from the repository folder

```bash
python notebooks/fetch_data.py                     # into data/ (DATA_DIR); --data-dir DIR for another folder
python notebooks/fetch_data.py --check-only        # only report what is there and whether it matches
```

It copies the Nurnet files from `data/nurnet/`, downloads every public input from its official source (streamed to
`DATA_DIR/_downloads/`, each download checked against the SHA-256 the provider served on 2 November 2026), rebuilds
the files the model reads, compares each file with `notebooks/inputs_manifest.csv` and writes
`DATA_DIR/fetch_provenance.json`. It needs about 1.5 GB of RAM for the DEM (`--no-rasters` skips the DEM, cost and
slope builds).

| input (file under `DATA_DIR`) | where it comes from | automatic | SHA-256 = the run's copy? |
|---|---|---|---|
| `sites/nurnet_nuraghi.{shp,shx,dbf,prj,cpg}` | Nurnet's data, included: `data/nurnet/nurnet_nuraghi.*` | copied | **yes** |
| `stone/nid_materiale_prod.csv` | Nurnet's data, included: `data/nurnet/nurnet_site_building_stone.csv` | copied (renamed) | **yes** |
| `geology/sardinia_lithology_25832.*` | ARPAS 2019 Carta Litologica 1:25,000 (zip, 243 MB) | download + `tools_extra/build_lithology.py` | `.prj`, `.cpg` yes; `.shp/.shx/.dbf` no (see below) |
| `dem/sardinia_dem_GLO30_25832.tif` | Copernicus DEM GLO-30, 8 tiles (AWS, 136 MB) + RAS regional boundary (mask) | download + `tools_extra/build_dem.py` | no (see below) |
| `costsurface/sardinia_drag_cost_8dir_mu03_25832_int.tif` | from the DEM | `code/tools/build_cost_mu.py` | only if the DEM is identical |
| `costsurface/sardinia_slope_deg_25832.tif` | from the DEM | `tools_extra/build_slope.py` | only if the DEM is identical |
| `soils/soils250k.geojson` | AGRIS WFS (24 MB) | download | **yes** |
| `water/sardinia_rivers_25832.*` | RAS PPR 2006 rivers (zip, 10 MB) | download + `tools_extra/build_rivers.py` | `.prj`, `.cpg` yes; `.shp/.shx/.dbf` no (see below) |

Why some files are not byte-comparable (all checked on 2 November 2026):

- **Lithology and rivers**: the run's copies were exported on 14 October 2026 from the same official layers as held in
  a project database. The rebuild has the same features (47,780 polygons / 41,877 segments), the same IDs, map units
  and vertex counts (the `.shp` and `.shx` files have exactly the same size), but the coordinates differ by up to
  5 mm (a different datum transformation at import) and the rows are in database order in the run's copies. On the
  30 m grid of the model this is immaterial. `--compare RUN_COPY.shp` in the two build scripts reports it.
- **DEM**: rebuilt with the run's recipe (mosaic, reprojection to EPSG:25832 at 30 m, bilinear) on exactly the run's
  grid (4808 x 9080 cells, checked). The run masked the sea with the regional river catchments as held in a project
  database, which are not public; the public mask is the RAS regional boundary. Both masks (buffered by 300 m) differ
  in about 75 km2, mostly coastal sea cells with z ~ 0 that the model treats as sea anyway (land = z > 0). With the
  run's mask (`fetch_data.py --basins FILE`) and the same GDAL the file should be byte-identical.
- **Soils**: GeoServer writes the time of the request into the file (`"timeStamp"`); `fetch_data.py` writes back the
  time stamp of the run's copy, after which the file is byte-identical (tested).

## Linking the data yourself

The same files by hand. Run the commands from the repository folder; `DATA_DIR` is the folder you will give the
notebooks (default `data/` in the repository). Expected layout:

```
DATA_DIR/
  sites/nurnet_nuraghi.{shp,shx,dbf,prj,cpg}               nuraghe sites (copy of data/nurnet/)
  stone/nid_materiale_prod.csv                             building stone per site (copy of data/nurnet/nurnet_site_building_stone.csv)
  geology/sardinia_lithology_25832.{shp,shx,dbf,prj,cpg}   lithology with the STONE classes
  dem/sardinia_dem_GLO30_25832.tif                         DEM, EPSG:25832, 30 m
  costsurface/sardinia_drag_cost_8dir_mu03_25832_int.tif   drag cost, 8 directions, mu 0.3 (from the DEM)
  costsurface/sardinia_slope_deg_25832.tif                 slope in degrees (from the DEM)
  soils/soils250k.geojson                                  soil map 1:250,000
  water/sardinia_rivers_25832.{shp,shx,dbf,prj,cpg}        rivers and streams
  derived/cache/                                           derived inputs (DERIVED_DIR; see Derived inputs)
```

```bash
D=data                      # DATA_DIR (absolute path recommended)
DL=$D/_downloads; mkdir -p $DL $D/sites $D/stone $D/geology $D/dem $D/costsurface $D/soils $D/water
```

1. **Nuraghe sites and building stone** (Nurnet's data, included; see [Nurnet files](#nurnet-files)):
   ```bash
   cp data/nurnet/nurnet_nuraghi.* $D/sites/
   cp data/nurnet/nurnet_site_building_stone.csv $D/stone/nid_materiale_prod.csv
   ```
2. **Lithology** (ARPAS 2019, CC BY 4.0):
   ```bash
   curl -L -o $DL/carta_litologica_2019.zip https://webgis.regione.sardegna.it/scaricocartografiaETL/arpas/carta_litologica_2019.zip
   python tools_extra/build_lithology.py $DL/carta_litologica_2019.zip $D/geology/sardinia_lithology_25832.shp
   ```
   (zip SHA-256 `547f64c41b4ee7268b35c45e1478a651c86fe13ba29dd0fcabbb796c6b681aa6`; the script reprojects the
   shapefile inside it from EPSG:3003 to EPSG:25832 and adds the STONE grouping of `data/lithology_STONE_classes.csv`.)
3. **DEM** (Copernicus DEM GLO-30, open AWS bucket, no login) and its land mask:
   ```bash
   mkdir -p $DL/dem_tiles
   for la in 38 39 40 41; do for lo in 008 009; do n=Copernicus_DSM_COG_10_N${la}_00_E${lo}_00_DEM
     curl -L -o $DL/dem_tiles/$n.tif https://copernicus-dem-30m.s3.amazonaws.com/$n/$n.tif; done; done
   curl -L -o $DL/limiteAmministrReg_CTR.zip https://webgis.regione.sardegna.it/scaricocartografiaETL/limitiAmministrativi/limiteAmministrRegionale/limiteAmministrReg_CTR.zip
   (cd $DL && python -m zipfile -e limiteAmministrReg_CTR.zip region)
   python tools_extra/build_dem.py $DL/dem_tiles $D/dem/sardinia_dem_GLO30_25832.tif --mask region $DL/region/limiteAmministrRegionale_CTR.shp
   ```
   (tile SHA-256 values: `DEM_TILES` in `notebooks/fetch_data.py`.)
4. **Drag cost and slope** (from the DEM; `CFG` = a copy of `config/v16_final/config_full_audited.yaml` with `data_dir:` set
   to the absolute path of `DATA_DIR`):
   ```bash
   (cd code && python tools/build_cost_mu.py CFG 0.3 $D/costsurface/sardinia_drag_cost_8dir_mu03_25832_int.tif)
   python tools_extra/build_slope.py $D/dem/sardinia_dem_GLO30_25832.tif $D/costsurface/sardinia_slope_deg_25832.tif
   ```
5. **Soils** (Aru, Baldaccini & Vacca 1991, RAS/AGRIS, CC BY):
   ```bash
   curl -o $D/soils/soils250k.geojson "https://geoserver.sardegnaportalesuolo.it/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature&typeNames=Agris:carta_dei_suoli_sardegna_scala_250000&outputFormat=application/json&srsName=EPSG:4326"
   ```
   (by hand the file differs from the run's copy only in its `"timeStamp"` field, see above.)
6. **Rivers** (RAS, PPR 2006 'Fiumi torrenti e altri corsi d'acqua'):
   ```bash
   curl -L -o $DL/fiumiTorrenti_ARC.zip https://webgis.regione.sardegna.it/scaricocartografiaETL/ppr/fiumiTorrenti_ARC.zip
   python tools_extra/build_rivers.py $DL/fiumiTorrenti_ARC.zip $D/water/sardinia_rivers_25832.shp
   ```

**Point the notebooks at it.** In the config cell of each notebook: `DATA_DIR = "/absolute/path/to/data"` and
`DERIVED_DIR = "/absolute/path/to/data/derived/cache"` (or the environment variables `NB_DATA_DIR`,
`NB_DERIVED_DIR`). On Colab, upload the folder to Google Drive and set `MOUNT_DRIVE = True` and the Drive paths
(see [Run in Google Colab](#run-in-google-colab)). For a model run outside the notebooks, set `data_dir:` in the
config you use to the absolute path of `DATA_DIR`. Set `FETCH = False` in 02 to use your files as they are
(02 then only checks them).

**Verify.** Save the block below as `DATA_DIR/SHA256SUMS` and run `cd DATA_DIR && sha256sum -c SHA256SUMS` (macOS:
`shasum -a 256 -c SHA256SUMS`). The values are those of `notebooks/inputs_manifest.csv` (the copies used for the runs).
Expect `OK` for the Nurnet files, the soils and the `.prj/.cpg` files, and `FAILED` for the files that are rebuilt and
not byte-comparable (lithology and rivers `.shp/.shx/.dbf`, DEM, cost, slope; see above), unless you use the run's
copies.

```
c5128744f17f9434fae69c26067837d332ed85d699a5c5503ba8fbd2fc3eb540  sites/nurnet_nuraghi.shp
ebcaa3d99664f05ff3e275d9a52c36e9b192abbfa84feaa3b55a775929619b21  sites/nurnet_nuraghi.shx
e411c159feaa18570da06954e5454ae0d54184c9a9224b0a46712199dcb3a569  sites/nurnet_nuraghi.dbf
2bfc323fa76efbd54e39e220c4d8f16ab79728c0eab137ab43fe7fee726e60dc  sites/nurnet_nuraghi.prj
3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824  sites/nurnet_nuraghi.cpg
08a1d36f7d57b95df58dd4e27d03d97435f3087d3cbcf97b86a91920fe198adb  stone/nid_materiale_prod.csv
4203246d73d713b3d029c3bb912bd494339bb374991b993f3d94b177f11e79fd  geology/sardinia_lithology_25832.shp
b2d73866acc04ab51c1cdd496b6518e5fc2f5b7d08a59d36417ea218aee47239  geology/sardinia_lithology_25832.shx
27934a5ae8c72669576f6a6739bb5e06f50f061ea031ef6f83480964bfc01489  geology/sardinia_lithology_25832.dbf
2bfc323fa76efbd54e39e220c4d8f16ab79728c0eab137ab43fe7fee726e60dc  geology/sardinia_lithology_25832.prj
3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824  geology/sardinia_lithology_25832.cpg
1f01213b688333152621033095a453cb2498dbe0a94ccac02bcb4a36f2389e91  dem/sardinia_dem_GLO30_25832.tif
69a9c1bb85ed6d857f2a7fdbc2f8eeef01746be48d7db944ebfc22923d8fd432  costsurface/sardinia_drag_cost_8dir_mu03_25832_int.tif
70a42c4621f145b71efe09d16ead7610a1e2b55646ac1b0dacdac6702d0f22ba  costsurface/sardinia_slope_deg_25832.tif
c6093d55da4fe84f1dd9371a7973e7496b5fe74c8d72c58bc5bdd485a2d9d830  soils/soils250k.geojson
2d9371e8810330b49861aa463b63b65372745de54ff40b181a1039a085ffe2c1  water/sardinia_rivers_25832.shp
70e4678d1b64e61b503e7fd936b75f830390215c4bdb39fceada7587ae43bb7d  water/sardinia_rivers_25832.shx
557fd395b75a05cb766b084412b4930bdb879f19a5c26cfca2869fc46083d394  water/sardinia_rivers_25832.dbf
2bfc323fa76efbd54e39e220c4d8f16ab79728c0eab137ab43fe7fee726e60dc  water/sardinia_rivers_25832.prj
3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824  water/sardinia_rivers_25832.cpg
```

### Nurnet files

The site list (nurnet_nuraghi.shp: 7,167 nuraghi with tower counts) and the per-site building stone file are
Nurnet's data; the files are included in `data/nurnet/`:

| file in `data/nurnet/` | copy it to (under `DATA_DIR`) | SHA-256 |
|---|---|---|
| `nurnet_nuraghi.{shp,shx,dbf,prj,cpg}` | `sites/nurnet_nuraghi.{shp,shx,dbf,prj,cpg}` | in the block above (`sites/...`) |
| `nurnet_site_building_stone.csv` | `stone/nid_materiale_prod.csv` | `08a1d36f7d57b95df58dd4e27d03d97435f3087d3cbcf97b86a91920fe198adb` |

For the latest version and source information contact Nurnet at nurnet.presidente@gmail.com. The site list is needed
by every run; the building-stone file is read only when the haul tables are rebuilt with the hybrid stone rule (the
rule of the full audited run, the default); without it, `stone_rule: stones7` (results then differ).

## Derived inputs

The model runs read cached derived inputs (haul tables, k-best quarry routes, sea tables, food catchments, cost
rasters per friction; 68 files, listed in `notebooks/inputs_manifest.csv`, group `derived`, and explained in
`data/derived/README.md`). Two ways to get them into `DERIVED_DIR`:

1. **Prebuilt pack** of the v17 runs: `DERIVED_URL` in 02 (or `python notebooks/fetch_data.py --derived-url
   URL`). Placeholder: the pack is part of the results package, which is not public yet (DOI pending).
2. **Rebuild** from the raw inputs: automatic in 02 (section 0b, `REBUILD_DERIVED = "auto"`, the default) when any
   derived input is missing and no pack is available; `REBUILD_DERIVED = True` always rebuilds, `False` never; or
   `python notebooks/fetch_data.py --rebuild-derived [--stone-rule hybrid|stones7]`. It runs the commands of
   `data/derived/README.md` in order, with the configuration of the v17 runs. Times and peak memory from the project's logs (8 GB machine): cost rasters per
   friction ~0.85 GB each; base haul table 14 s (stones7) / 249 s (hybrid), 1.7-2.4 GB; each further haul table about
   12 s with stones7 (up to ~4 min with hybrid); k-best routes 95 s, 1.9 GB; wider-literature inputs 13 s, 2.2 GB; sea
   tables 192 s, 1.1 GB; bichrome distances 15 s; food catchments not timed. **Total about 30-45 min with hybrid,
   15-20 min with stones7** (estimated from the component logs; the sequence has not been timed end to end).

The full audited run reused derived inputs built by earlier runs of the project (provenance note in
`data/derived/README.md`), so a rebuild is not guaranteed byte-identical to the pack; the rerun check of
`05_audit.ipynb` (step d) is defined on the pack.

## Troubleshooting

- *Repository not found*: set `REPO_DIR` in the config cell to the cloned folder (Colab clones it automatically).
- *RESTART NEEDED* after the install: restart the kernel / Colab session and run the notebook again from the top.
- *PREFLIGHT FAILED ... MISSING*: run 02, section 0 (`FETCH = True`), or link the file by hand (above).
- *WRONG ... SHA-256 differs*: a truncated download or another version; delete the file and fetch it again. Files
  rebuilt by `fetch_data.py` are reported as *REBUILT* (not an error).
- *Out of memory* during a run: fewer MPI ranks (`RANKS`), or the `demo` / `quick` preset.
- *code version ... expected 2026-11-09-v17*: `code/` is not the v17 code; check out the repository again. Part
  files of other code versions are never reused (the code version is part of every run signature).
- *stone_rule = stones7 needs the stones7 derived-input cache* (06): set `STONES7_CACHE`, or leave it unset (the
  factor is then fixed at hybrid).
