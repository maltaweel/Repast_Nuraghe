# Derived inputs (cached)

Everything here is computed from the raw inputs (`data/README.md`) by code in this repository. None of it is
committed. Two ways to get it:

1. **Download** the cached derived inputs of the full audited run from the results package
   ("data file/nuraghe-build-abm-full-audited", Nurnet cloud; DOI pending) and put them in
   `data/derived/cache/` (notebooks) or in `<run folder>/outputs/caches/config_full_audited/` (the queue, see the
   top-level README, "Run the queue").
   When the pack is public: `python notebooks/fetch_data.py --derived-url URL` (or `DERIVED_URL` in
   `notebooks/02_inputs.ipynb`, section 0b) downloads and unpacks it (placeholder until then).
2. **Rebuild** them with the commands below; `python notebooks/fetch_data.py --rebuild-derived [--stone-rule
   hybrid|stones7]` (or 02, section 0b: automatic when any derived input is missing and no pack is available; `REBUILD_DERIVED = True` forces it) runs them all in this order into `data/derived/cache/`.

**How long a rebuild takes** (from the project's logs, 8 GB machine; one process at a time): cost rasters per
friction about 0.85 GB peak each (time not logged); base haul table 14 s with stones7, 249 s with hybrid (1.7-2.4 GB);
each further haul table about 12 s with stones7 (up to about 4 min with hybrid); k-best quarry routes 95 s (1.9 GB);
wider-literature inputs 13 s (2.2 GB); sea tables 192 s (1.1 GB); bichrome distances 15 s (1.5 GB); food catchments not
timed; the stones7 alternative set of the queue (3 haul tables, k-best routes, mu 0.38 and wider-literature inputs)
320 s. In total about 30-45 minutes with hybrid and 15-20 minutes with stones7 (an estimate from these component
times; the whole sequence has not been timed end to end).

In every command `CFG` is a configuration file whose `data_dir` points at the raw inputs and whose `cache_dir` is
the cache being built (`config/config_full_audited.yaml`: `outputs/cache` relative to the config folder). Run from
`code/`. All rasters are on the 30 m DEM grid in EPSG:25832.

**Provenance note.** In the project's runs, the base cache was not rebuilt in one go: its entries were reused
(linked) from earlier runs of the same project (haul tables, outcrop raster and per-friction tables of 29 Oct 2026;
k-best routes of 2 Nov 2026; food catchments of 1 Nov 2026; cost rasters per friction), the base haul tables were
rebuilt with the on-outcrop test of `code/preprocess.py`, and the sea tables were rebuilt per configuration. The
commands below are those the project used. A complete rebuild with `code/` has not been compared byte for byte with
the reused files
(`tools/build_cost_mu.py ... --check` does this for the base cost raster).

## Rasters in `data_dir/costsurface/`

| File | What | Rebuild |
|---|---|---|
| `sardinia_drag_cost_8dir_mu03_25832_int.tif` | sledge-drag cost per move, 8 bands (N, NE, E, SE, S, SW, W, NW), flat-metre equivalents at friction mu = 0.3: `t = clip((z_nb - z) / d, -1, 1)`, `cost = max(0.5, abs(mu + t) / mu) * d` (d = 30 or 42.43 m), rounded with `np.rint` | `python tools/build_cost_mu.py CFG 0.3 OUT.tif`; `python tools/build_cost_mu.py CFG 0.3 --check` compares a rebuild with the file in `data_dir` |
| `sardinia_slope_deg_25832.tif` | slope in degrees (beach rule of the sea landings) | `python ../tools_extra/build_slope.py DEM.tif OUT.tif` |

## Cache (`cache_dir`)

| Path | What | Built by |
|---|---|---|
| `sites_haul.csv`, `outcrop_code.tif`, `site_stone_sets.csv`, `materiale_use.csv` | base haul table (least drag cost and path length from the nearest permitted outcrop to every site, one multi-source directional Dijkstra per stone set), the outcrop raster (stone class per cell), each site's stone set, and the use of the recorded-stone tokens. With `stone_rule: hybrid` this step reads the per-site building-stone file (`data/README.md`, section 2) | `python preprocess.py CFG` (`--rule stones7` without that file) |
| `cost_mu/drag_cost_8dir_mu{0.05,0.1,0.38,0.5}_int.tif` | drag-cost rasters at other friction coefficients (tracks, wet sledges, dry ground) | `python tools/build_cost_mu.py CFG MU cache/cost_mu/drag_cost_8dir_muMU_int.tif` |
| `haul/sites_haul_mu*.csv`, `haul/outcrop_code_mu*.tif`, `haul/site_stone_sets_mu*.csv`, `haul/materiale_use_mu*.csv` | haul tables at the other frictions (literature scenarios) | `python preprocess.py CFG --tag muMU --cost-raster cache/cost_mu/drag_cost_8dir_muMU_int.tif` |
| `haul/*_buildstone*.{csv,tif}` | haul tables with any building stone allowed (S5b) | `python preprocess.py CFG --tag buildstone --stones BUILDSTONE` (and `--tag buildstone_mu0.1 ... --cost-raster` the mu 0.1 raster) |
| `haul/*_stones7.{csv,tif}` | haul tables with the 7-stone rule for every site | `python preprocess.py CFG --rule stones7 --tag stones7` |
| `haul/sites_haul_complexfar.csv` | complexes quarrying farther away (S5c) | `python tools/haul_far.py CFG` |
| `alliance/kbest.npz` | the k cheapest distinct quarry faces per site with their least-cost paths (alliance and MOST_REALISTIC scenarios) | `python tools/kbest_quarries.py CFG` (needs `cost_mu/..._mu0.1_int.tif`) |
| `alliance/kbest_mu038.npz` | per-move drag cost at mu 0.38 along those routes | `python tools/kbest_mu038.py CFG` |
| `alliance/kbest_wl.npz` | wider-literature inputs on the routes: costs at extra frictions and distance to streams (needs the rivers) | `python tools/wl_inputs.py CFG` |
| `sea/` (`sites_haul_sea{2,4,5,6}kn.csv`, `people_sea*kn.csv.gz`, `landings.csv`, `sea_meta.json`) | sea-aware haul tables and people travel times per boat speed | `python tools/sea_routes.py CFG` (about 1 GB peak, single process) |
| `food/site_food_r{1000,1500,2000,3000}.csv` | each site's catchment (Thiessen polygon clipped to radius R) by land-capability class (needs the soils) | `python tools/food_capacity.py CFG --soils DATA_DIR/soils/soils250k.geojson --radius R --out cache/food/site_food_rR.csv` |
| `census/bichrome_dist.csv` | distance from every site to the nearest basalt and limestone/marble outcrop (S23 bichrome) | `python tools/census_bichrome.py CACHE_DIR` |
| `stones4/` | base tables with the original 4 permitted stones (comparison in `tools/stone_rule.py` only) | `preprocess.py` with `--rule stones4` and a config whose `cache_dir` is `cache/stones4`, then `tools/kbest_quarries.py` on that config |

`code/run_all.sh` (steps 1-3 and the first line of step 8) runs the first rows of this table in order. Its last
lines call three tools that are not in this repository (`tools/components.py`, `tools/master_comparison.py`,
`report/make_report.py`; not published).

## Own caches of the queue (`outputs/caches/<config name>/`)

Every configuration of the queue (`config/scenarios/`) reads its own cache folder. Most link every entry of the base
cache; 35 variants (the header of each configuration says which) rebuild their sea tables (`sea/`, an empty real
folder: `tools/sea_routes.py` with that configuration), and `config_full_audited_alt_stones7` also its own haul
tables and k-best routes (`alliance/`, `haul/` and the base haul tables). The expected sea parameters of a build are
in `config/sea_expect/<config name>.json`; copy the file to `<cache>/sea_expect.json` and run
`config/check_sea_meta.py <cache>`. The top-level README ("Run the queue") lists the steps.
