# Nuraghe construction: an agentic agent-based model

An agent-based model (ABM) built to test archaeological ideas about **how nuraghi were built**: who quarried,
dressed, hauled and lifted the stone, how communities cooperated, formed alliances or relied on pre-existing
networks, and what each idea implies for labour and time. Bronze Age Sardinia (7,167 nuraghe sites) is the test
case; the method is the subject. Each community is an agent that plans its towers stage by stage, asks other
communities for help, learns from its own building and from trust built by reciprocity, and moves stone along
least-cost routes over the real terrain (and, in some scenarios, by sea). Literature-based scenarios set the
labour rates, block sizes, haul techniques, lifting methods, population and season length; every parameter is
traced to its source or labelled as an assumption (`param_audit/`).

The model is written in Python on **repast4py** (Collier, N. and Ozik, J. 2022. Distributed agent-based
simulation with Repast4Py. *Proceedings of the 2022 Winter Simulation Conference (WSC)*.
doi:[10.1109/WSC57314.2022.10015389](https://doi.org/10.1109/WSC57314.2022.10015389)) and MPI.

## How it works

- **Agents.** One community agent per nuraghe (7,167), with its residents, its work party and the towers it has to
  build (`code/alliance.py`; ODD section 2).
- **A season** (one tick: 90 working days of 8 hours, standing for one year). Each community works on its current
  tower as a chain of stage tasks: quarrying, dressing, hauling the blocks on sledges along least-cost routes from
  the chosen quarry face, and building (including lifting) (ODD sections 2-3).
- **Cooperation.** Communities ask others within 10 km for help (up to 3 requests); a request is accepted according
  to trust, which reciprocity raises or lowers. Each community learns which choices worked for it, imitates
  successful neighbours, and gains skill with experience (ODD sections 3-4). The 10 km help radius is the headline
  value; a sensitivity ran it at 5 and 15 km on the audited headline (`MOST_REALISTIC_AUDITED_LIT_R5_P10` /
  `_R15_P10`, `config/config_R5_audited.yaml` / `config_R15_audited.yaml`, ODD Appendix B).
- **Phasing.** In the headline scenario the island is built in cohorts of 10% of the communities, one cohort after
  the other (`_P10`; ODD section 7).
- **What is measured.** Man-hours per site and stage, start and finish of every tower; per seed, island man-hours
  and island years (the time until the last tower is finished), over 100 seeds per scenario (ODD section 4.11).
- **v13 social switches.** Three opt-in mechanisms (`reputation`, `partner_choice`, `tie_imitation`), off by default and in the headline, used only by five v13 scenarios; with them off the outputs are identical to the frozen code (ODD section 7.15; `CODE_PROVENANCE.md`). A rule key `reputation_rule` (`all`, the default, or `gentle`: only defectors' and ungrateful refusals cost standing) is used by three v13g scenarios (`config/config_v13g_*.yaml`); with the default the outputs and signatures of the v13 runs are unchanged. A further switch `trusted_nodist` (no distance penalty in the acceptance of help between reciprocal partners, after Kasper & Borgerhoff Mulder 2015, Fig. 2) is used by two v13kd scenarios (`config/config_v13k_*.yaml`; ODD section 7.16); with it absent the outputs and signatures of every earlier run are unchanged.
- **Parameters.** No parameter is calibrated: every value has an audited source (author, year, page) or is
  declared an assumption (`param_audit/`).

## Workflow

```mermaid
flowchart TD
    A["Raw inputs<br/>Nurnet site list + building stone: data/nurnet/<br/>ARPAS lithology, Copernicus DEM, soils, rivers"]
    B["Fetch / link<br/>notebooks/fetch_data.py<br/>notebooks/HOW_TO_USE.md"]
    C["Derived inputs<br/>code/preprocess.py, cost rasters: code/tools/build_cost_mu.py<br/>k-best quarry routes: code/tools/kbest_quarries.py<br/>sea tables: code/tools/sea_routes.py"]
    D["Configuration<br/>config/config_full_audited.yaml + scenario variants<br/>config/queues/"]
    E["Model runs<br/>code/model.py, repast4py + MPI<br/>100 seeds per scenario"]
    F["Outputs<br/>per-seed part files"]
    G["Summaries and checks<br/>code/tools/v12_summary.py and other *_summary.py<br/>code/tools/v12_checks.py"]
    H["Audit<br/>notebooks/05_audit.ipynb<br/>param_audit/, ODD/"]
    A --> B --> C --> E
    D --> E
    E --> F --> G --> H
```

## Start here

| Model description | Replicate the results |
|---|---|
| [ODD/ODD.md](ODD/ODD.md) (PDF: [ODD/ODD.pdf](ODD/ODD.pdf)): the ODD protocol of the full audited model | [notebooks/](notebooks/): start with [notebooks/HOW_TO_USE.md](notebooks/HOW_TO_USE.md), then run `01_setup`, `02_inputs`, `03_scenarios`, `04_analysis_report`, `05_audit` in order, in Jupyter or Google Colab |

Parameter audit and traceability: [param_audit/](param_audit/) (below).

### Replicate the results: quick start in Colab

1. Open [notebooks/README.md](notebooks/README.md) and use the "Open in Colab" links, 01 to 05 in order.
2. In the config cell of each notebook set `MOUNT_DRIVE = True` and the same Google Drive folders for `DATA_DIR`,
   `DERIVED_DIR` and `OUTPUTS_DIR` (each Colab notebook runs in its own runtime; values in
   [HOW_TO_USE.md](notebooks/HOW_TO_USE.md#run-in-google-colab)).
3. Run all cells. 01 installs OpenMPI and the pinned packages; 02 copies the Nurnet files from `data/nurnet/`,
   downloads every public input from its official source (`notebooks/fetch_data.py`) and gets the derived inputs;
   03 and 04 run and analyse scenarios; 05 is the step-by-step audit (code checksums, inputs, configuration, a fixed
   rerun, the headline numbers), each step with its expected result.

The Nurnet files (site list and per-site building stone) are included in `data/nurnet/`; for the latest version and
source information contact Nurnet at nurnet.presidente@gmail.com.

### Data availability

- **Nurnet's data** (7,167 nuraghe sites with tower counts; building stone per site): included in this repository,
  `data/nurnet/` (`data/nurnet/README.txt`). For the latest version and source information contact Nurnet at
  nurnet.presidente@gmail.com.
- **Public layers** (ARPAS lithology, Copernicus DEM GLO-30, AGRIS soil map, RAS rivers): not redistributed here;
  `notebooks/fetch_data.py` downloads them from the official sources and rebuilds the files the model reads, and
  `notebooks/HOW_TO_USE.md` gives the same steps by hand. Each file is checked against the SHA-256 of the copy used
  for the runs (`notebooks/inputs_manifest.csv`); the files that cannot be byte-identical, and why, are listed there
  and in `data/README.md`.
- **Derived inputs** (haul tables, quarry routes, sea tables, ...): rebuilt from the raw inputs by
  `python notebooks/fetch_data.py --rebuild-derived` (about 30-45 min), or the prebuilt pack of the full audited run
  in the results package (DOI pending).
- **Results** of the full audited run (per-seed tables, part files, logs): results package, DOI pending.

## Repository layout

```
code/            the model and its tools: the code of the full audited run + the v13 social switches (CODE_PROVENANCE.md)
  model.py         entry point (baseline, cooperation, literature, alliance and pre-network scenarios)
  alliance.py      adaptive alliances / MOST_REALISTIC; lit.py, sea.py, phasing.py, pre_networks.py, census_v12.py
  preprocess.py    haul tables (least-cost quarry -> site); nbcommon.py config loader + Dijkstra
  tools/ tests/    derived-input builders, post hoc analyses, verification
  full_chain.sh    the serialized chain that ran the full audited queue
config/          config_full_audited.yaml (+ 84 variants, tost_configs/), queues/, sea_expect/, check_sea_meta.py
data/            data/nurnet/ (Nurnet's data, included); the other inputs are fetched (data/README.md; data/derived/README.md)
notebooks/       01-05: setup, inputs (fetch_data.py), scenarios, analysis, audit; HOW_TO_USE.md; Jupyter or Colab
param_audit/     parameter audit and traceability (public-safe copies)
tools_extra/     build_slope.py, build_dem.py, build_lithology.py, build_rivers.py (input builders; not in the frozen snapshot)
outputs/         everything a run writes (NOT committed, except reference/ and summary/ for the audit)
CODE_SHA256SUMS  checksums of the run's code snapshot;  CODE_PROVENANCE.md  what differs and why
```

## Requirements / Installation

Linux or macOS (Windows: WSL2 with Ubuntu), Python 3.10 or later (the tested environment is Python 3.13.5).

| what | version (minimum in `code/requirements.txt`; tested in `notebooks/requirements-colab.txt`) |
|---|---|
| MPI with compiler wrappers | OpenMPI or MPICH. Ubuntu / Debian / Colab: `sudo apt-get install -y openmpi-bin libopenmpi-dev`; macOS: `brew install open-mpi`; conda: `conda install -c conda-forge openmpi mpi4py` |
| repast4py | >= 1.1.6; tested 1.3.1 (Collier & Ozik 2022, above; install guide https://repast.github.io/repast4py.site/) |
| mpi4py | >= 3.1; tested 4.1.2 |
| numpy / numba / pandas | >= 1.24 / >= 0.58 / >= 2.0; tested 2.5.4 / 0.68.0 / 3.0.6 |
| geopandas / pyogrio / rasterio | >= 0.14 / >= 0.7 / >= 1.3; tested 1.2.0 / 0.13.0 / 1.5.2 (the wheels include GDAL, tested 3.12.2; no system GDAL needed) |
| pyyaml | >= 6.0; tested 6.0.3 |
| also pinned for the tools and notebooks | scipy 1.18.1, shapely 2.2.0, pyproj 3.8.0, matplotlib 3.11.2, networkx 3.7, reportlab 5.1.0 and dependencies (33 pins) |

1. Install MPI (above).
2. Install the Python packages; repast4py and mpi4py compile against MPI:
   ```
   CC=mpicc CXX=mpicxx python -m pip install -r notebooks/requirements-colab.txt     # exact tested versions
   CC=mpicxx CXX=mpicxx python -m pip install -r code/requirements.txt              # or: minimum versions
   ```
   `torch` is not pinned: repast4py imports it, the model never uses it.
3. Get the input data: `python notebooks/fetch_data.py` (or by hand: `notebooks/HOW_TO_USE.md`); set `data_dir:` in
   the config you use to the **absolute** path of the data folder (the configs in `config/` hold a placeholder).

Resources (measured on the 8 GB machine of the runs): one 100-seed run of the headline scenario on 6 MPI ranks takes
about 6 minutes and peaks at about 6 GB (proportional set size 5.9 GB; resident 7.6 GB; largest rank 2.8 GB); the
derived-input rebuild peaks at about 2.5 GB (one process at a time). Disk: about 0.5 GB of raw inputs, 0.75 GB of
derived inputs, about 0.25 GB of part files per 100-seed scenario.

`code/full_chain.sh` (the full queue) also needs `flock` and Linux cgroup v2 (it reads
`/sys/fs/cgroup/memory.events` to stop on an out-of-memory kill).

Environment variables used by the scripts (only where a path was hard-wired in the project):

| Variable | Meaning |
|---|---|
| `PYTHON` | the Python interpreter of the environment above (shell scripts; default `python3`) |
| `NURAGHE_RUN_DIR` | the run folder of `code/full_chain.sh` (below) |
| `NURAGHE_PROJECT` | the project folder of the earlier runs, for the historical chain/test scripts and some post hoc tools (`code/*_chain.sh`, `code/tests/*.sh`, `tools/v11_*`, `tools/v12_*`, ...); not needed for the model itself |
| `NURAGHE_DATA` | the data folder, for `tools/v12_checks.py` (default `data`) |

## Rebuild the derived inputs

The model reads cached derived inputs (haul tables, k-best quarry routes, sea tables, food catchments, drag-cost
rasters per friction). Download them from the results package or rebuild them with the commands in
`data/derived/README.md` (in order: cost and slope rasters, `preprocess.py`, haul tables per friction,
`tools/kbest_quarries.py`, `tools/kbest_mu038.py`, `tools/wl_inputs.py`, `tools/sea_routes.py`,
`tools/food_capacity.py`, `tools/census_bichrome.py`); `python notebooks/fetch_data.py --rebuild-derived` runs them
all in order (about 30-45 min with the hybrid stone rule, peak about 2.5 GB).

The stone rule of the full audited configuration is `hybrid`: the recorded building stone of each site where it is
known, else the nearest outcrop of the 7 permitted classes. That per-site file is **Nurnet's data (site building
stone)**, included as `data/nurnet/nurnet_site_building_stone.csv` (`fetch_data.py` copies it to
`stone/nid_materiale_prod.csv` under the data folder). `stone_rule: stones7` ignores it (results then differ).

## Run one scenario

From `code/`, with a configuration whose `data_dir` and `cache_dir` point at the inputs:

```
cd code
mpirun -n 6 $PYTHON model.py /path/to/run/config_full_audited.yaml --seeds 1-100 --no-shapefile \
       --alliance MOST_REALISTIC_AUDITED_LIT_P10
```

`MOST_REALISTIC_AUDITED_LIT_P10` is the headline scenario of the full audited run (6 ranks; about 6 min and up to
~8 GB on the machine that ran it). Other families: `--scenario NAME` (cooperation), `--lit NAME` (literature),
`--alliance NAME` (alliances, MOST_REALISTIC and its variants), `--pre NAME` (pre-existing networks); no flag =
baseline. `--sites UID1,UID2,...` (e.g. the contents of `code/sites300_real.txt`) runs a subset. Runs are resumable:
finished seeds are kept as part files under `cache_dir/runs/<signature>/` (the signature hashes every parameter and
the site list) and skipped on restart. Field meanings and the model rules: `code/METHODS.md`. The notebooks
(`notebooks/`) wrap the same commands.

## Run the full audited queue

The full audited run is `config/queues/queue_full.tsv` (78 entries, priority 1) followed by
`config/queues/queue_full_p23.tsv` (370 entries, priorities 2-3): seeds 1-100 everywhere, one entry at a time,
each scenario on its named config. `code/full_chain.sh` runs it serially and is resumable (a finished entry leaves
`outputs/logs/q_<label>.ok`). It expects a run folder laid out as below:

```
REPO=/path/to/Repast_Nuraghe; RUN=/path/to/run_full_audited; DATA=/path/to/data; PYTHON=/path/to/python
mkdir -p $RUN/outputs/logs && ln -s $REPO/code $RUN/code
cp $REPO/config/config_full_audited*.yaml $REPO/config/check_sea_meta.py $RUN/ && cp -r $REPO/config/tost_configs $RUN/
sed -i "s|^data_dir: .*|data_dir: $DATA|" $RUN/config_full_audited*.yaml $RUN/tost_configs/*.yaml
for q in queue_full.tsv queue_full_p23.tsv; do
  sed -e "s|@RUN_DIR@|$RUN|g" -e "s|@PYTHON@|$PYTHON|g" $REPO/config/queues/$q > $RUN/$q; done
# base cache: download or rebuild into $RUN/outputs/cache (data/derived/README.md); sea/ must be an EMPTY real
# folder (the first queue entry, SEA_TABLES, rebuilds it)
# own caches of the variant entries: link every base-cache entry except the part each entry rebuilds
for d in $(grep -h '^  cache_dir:' $RUN/config_full_audited_*.yaml | awk '{print $2}' | sort -u | grep -vx outputs/cache); do
  D=$RUN/$d; mkdir -p $D/sea
  [ -f $REPO/config/sea_expect/$(basename $d).json ] && cp $REPO/config/sea_expect/$(basename $d).json $D/sea_expect.json
  if [ $(basename $d) = cache_alt_stones7 ]; then mkdir -p $D/alliance $D/haul; keep="census cost_mu food stones4"
  else keep=$(ls $RUN/outputs/cache | grep -vx -e sea -e runs -e sea_expect.json); fi
  for b in $keep; do [ -e $D/$b ] || ln -s $RUN/outputs/cache/$b $D/$b; done
done
cd $RUN && NURAGHE_RUN_DIR=$RUN PYTHON=$PYTHON CUTOFF="2099-12-31 23:59" \
  nohup bash code/full_chain.sh > outputs/logs/chain_full.out 2>&1 &
```

`CUTOFF` stops the chain from starting an entry whose estimated end falls after that time (the run used a fixed
deadline; dropped entries are listed in `outputs/logs/dropped.tsv`). Progress lines go to `$RUN/FULL_NOTES.md`.
The queue was estimated at about 34 hours of wall time on the 8 GB machine that ran it.

## Parameter audit and traceability

- `param_audit/PARAM_AUDIT.md` (+ `PARAM_AUDIT_ADDENDUM.md`): every parameter that acts on the headline scenario
  and every behaviour of the model, with value, role, source (author, year, page) or assumption label, evidence
  status before and after the audit, and the action taken. The audited values form `AUDITED_LIT`, the parameter set
  of `config_full_audited.yaml`.
- `param_audit/TRACEABILITY.md`, `PARAM_TRACE.csv`: each audited parameter -> config key -> code line -> queued
  scenarios that vary it.
- `param_audit/IDEA_TRACE.csv`, `census.csv`: the census of construction ideas from the literature (author, year,
  page, evidence type, testability, the scenario that implements each idea, and a field prediction). Quotations
  are not reproduced; see the cited works.
- Results, per-scenario tables, logs and the derived inputs of the full audited run: results package
  "data file/nuraghe-build-abm-full-audited" (Nurnet cloud), DOI pending. Files referred to in the audit documents
  but not in this repository (e.g. `SCENARIO_PROVENANCE_v2.csv`, `GAPS.md`, `PARAM_NOT_IN_AUDIT.csv`,
  `LIT_ALT_COVERAGE.csv`) are in that package.

## Data credits

Nuraghe sites: Nurnet's data — a Nurnet merge and deduplication of various sources; included in `data/nurnet/`.
Building stone per site: Nurnet's data; included in `data/nurnet/`. For the latest version and source information
contact Nurnet at nurnet.presidente@gmail.com. Lithology: ARPAS 2019, Carta Litologica della
Sardegna 1:25,000, © Regione Autonoma della Sardegna / ARPAS, CC BY 4.0. DEM: Copernicus DEM, © DLR e.V.
2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA.
Soils: Aru, Baldaccini & Vacca 1991, RAS/AGRIS, CC BY. Rivers: Regione Autonoma della Sardegna, PPR 2006 layer
'Fiumi torrenti e altri corsi d'acqua' ('fiumitorrenti'), see provider. Details and links: `data/README.md`.

## Citation

Paper in preparation. Please cite the paper when it is published; until then, cite this repository and the
results package (DOI pending).

## Licence

Licence: to be decided by the authors.
