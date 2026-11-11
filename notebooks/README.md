# Notebooks

Six Jupyter notebooks that set up the environment, get and check the inputs, run scenarios, analyse them, audit
the runs step by step, and run the sensitivity designs, with the model's code (`code/`, `CODE_VERSION` 2026-11-09-v17:
lift, every lift rule, priced at the undiscounted rate; the learning factor and skill act on quarrying, dressing and
building only; ODD 7.9) and the configuration of the final runs, `config/v16_final/config_full_audited.yaml`. **Start with [HOW_TO_USE.md](HOW_TO_USE.md)** (Colab and Jupyter quick start,
software requirements, getting the data automatically or
[linking the data yourself](HOW_TO_USE.md#linking-the-data-yourself), the derived inputs, expected results).

**Data.** The Nurnet files (site list `nurnet_nuraghi.shp`, 7,167 nuraghi with tower counts, and the per-site
building stone) are Nurnet's data and are included in `data/nurnet/`; for the latest version and source information
contact Nurnet at nurnet.presidente@gmail.com. Every other raw input is public and is downloaded from its official
source by `fetch_data.py` (02, section 0). Derived inputs: rebuilt automatically by 02 when missing (`fetch_data.py --rebuild-derived`, about
30-45 min) or the prebuilt pack (`DERIVED_URL`, placeholder until the results package is public).

The folders are set at the top of each notebook's config cell (`REPO_DIR`, `DATA_DIR`, `DERIVED_DIR`, `CONFIG`,
`OUTPUTS_DIR`, `WORK_DIR`, `RESULTS_DIR`; defaults `data/`, `data/derived/cache/`,
`config/v16_final/config_full_audited.yaml`, `outputs/`); the base configuration is
`config/v16_final/config_full_audited.yaml` (the same values as the model's configuration
`config/config_full_audited.yaml`: audited parameters, minimum haul 15 m, near-site rule 1,000 m; only `cache_dir` /
`output_dir` differ); all outputs are cleared, and the
notebooks hold no model results (every number is computed when they run; the results of the full runs are a
separate data input). All six were executed end to end at demo size (03 preset `demo`, 05 with a 30-site subset,
06 `SIZE = "demo"`) with the model's code on Linux (Python 3.13.5, the pinned packages, 2 MPI ranks), and again in a
Colab-like clean room (10 Nov 2026: fresh clone of this repository from `/content`, Python 3.12, only the packages the
notebooks install themselves, a Drive-like folder shared by the six notebooks); not yet on Colab itself.
Clean-room test: 01-06 pass with derived inputs supplied (commit a2010ed); the automatic rebuild path is being tested end to end.

## How to audit in Colab (quick start)

1. Open the six notebooks below in Colab, **in order**: 01, 02, 03, 04, 05, 06.
2. In the config cell of each: `MOUNT_DRIVE = True` and the same Drive folders (each Colab notebook has its own
   runtime): `DATA_DIR = "/content/drive/MyDrive/Repast_Nuraghe/data"`, `DERIVED_DIR =
   "/content/drive/MyDrive/Repast_Nuraghe/data/derived/cache"`, `OUTPUTS_DIR = "/content/drive/MyDrive/Repast_Nuraghe/outputs"`.
3. Runtime > Run all. The setup cell clones the repository and installs OpenMPI and the pinned packages. Nothing else to
   set: the first time 02 rebuilds the derived inputs automatically (about 30-45 min; the prebuilt pack is
   not public yet) and prints a note saying so.
4. 05_audit prints PASS / FAIL / NOT YET AVAILABLE per step: (a) code checksums vs `CODE_V17_SHA256SUMS`, (b) inputs
   vs `inputs_manifest.csv`, (c) `config/v16_final/config_full_audited.yaml` vs `param_audit/PARAM_TRACE.csv`, (d) a
   rerun of the headline scenario on 300 sites, seeds 1-3, vs the fingerprint in `outputs/reference/` (placeholder),
   (e) island years and man-hours from the per-seed tables of the results (placeholder).
5. 06_sensitivity runs the A5 grid, a Morris screen and a Sobol design at demo size (minutes) and regenerates the
   full designs.
6. For a quick smoke test of the whole chain set `PRESET = "demo"` in 03 and `LABEL = "demo"` in 04.

## Open in Google Colab

- [01_setup.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/01_setup.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/01_setup.ipynb)
- [02_inputs.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/02_inputs.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/02_inputs.ipynb)
- [03_scenarios.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/03_scenarios.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/03_scenarios.ipynb)
- [04_analysis_report.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/04_analysis_report.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/04_analysis_report.ipynb)
- [05_audit.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/05_audit.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/05_audit.ipynb)
- [06_sensitivity.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/06_sensitivity.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/06_sensitivity.ipynb)

Colab needs the inputs in a folder every notebook can reach: Google Drive (`MOUNT_DRIVE = True` and the Drive folders above). 02 fills it (`fetch_data.py`).

| Notebook | What it does / reproduces |
|---|---|
| `01_setup.ipynb` | Installs OpenMPI and the pinned Python packages (`requirements-colab.txt`), checks the versions, runs a 2-rank MPI smoke test and imports the model code; checks that `code/` is byte-identical to the repository version (`inputs_manifest.csv`, group `code`) and carries the code version of the final runs; runs the lift unit tests (`code/tests/test_v17_lift.py`). |
| `02_inputs.ipynb` | Section 0 "Getting the data": every input, its source, the automatic fetch (`fetch_data.py`: copies the Nurnet files from `data/nurnet/`, downloads the public layers from the official sources, rebuilds the model files, checks SHA-256) and the manual alternative; section 0b the derived inputs (prebuilt pack `DERIVED_URL` or a full rebuild); preflight of every input (presence, size, SHA-256; files rebuilt from an official source are reported as such); a look at the sites and the cost raster; the stone rule (`hybrid`, the rule of the full audited run, by default); the work folder (`WORK_DIR/config.yaml` = the configuration of the final runs with only `data_dir`, `cache_dir`, `output_dir`, `stone_rule` set); an optional rebuild of the base haul table (`preprocess.py`). |
| `03_scenarios.ipynb` | Runs any scenario with `model.py` (repast4py + MPI), by default baseline, lit webster, A5_full, the headline MOST_REALISTIC_AUDITED_LIT_P10, MOST_REALISTIC_P10 and its `_alone` twin: presets `demo` (30 sites, seed 1), `quick` (300 sites, seeds 1-3), `full` (7,167 sites, seeds 1-100) or `custom`; resumable; island totals of the runs. The last section reruns a fixed reference subset and compares it exactly with a reference fingerprint (`OUTPUTS_DIR/reference/reference_sha256.csv`). No reference is shipped (a fingerprint holds only for the code version it was made with), so make one with `MAKE_REFERENCE = True` before using `RUN_REFERENCE_CHECK = True`. |
| `04_analysis_report.ipynb` | Tables per scenario and tower class, maps of man-hours per nuraghe, centrality of the help networks (`tools/centrality.py`), network need with vs without the network (`tools/network_need.py`). The PDF report builder of the project is not included. |
| `05_audit.ipynb` | The step-by-step audit, each step with its expected result: (a) `code/` vs `CODE_V17_SHA256SUMS` and `CODE_PROVENANCE.md`, and the code version; (b) raw and derived inputs vs `inputs_manifest.csv`; (c) every audited parameter of `param_audit/PARAM_TRACE.csv` vs `config/v16_final/config_full_audited.yaml` (every value equal; minimum haul 15 m, near-site face 1,000 m); (d) a fresh rerun of `MOST_REALISTIC_AUDITED_LIT_P10` on 300 sites, seeds 1-3, vs `outputs/reference/reference_audit_sha256.csv` (placeholder until generated with `code/`); (e) island years and man-hours recomputed from the per-seed tables of the results package (`per_seed_full_audited.csv` vs `summary_full_audited.csv`; placeholder). |
| `06_sensitivity.ipynb` | The sensitivity steps at demo size: the A5 alliance grid (`model.py --alliance sensitivity`, 27 cells + A0_alone, `sensitivity.csv` written by `report_alliance.sensitivity`); a Morris screen (32 factors) and a Sobol design / analysis (24 + R_m factors; `lift_learning` needs a code switch that is not published) of the headline (`sensitivity.py`, SALib); regenerates the full designs (Morris r = 10: 330 evaluations; Sobol N = 512: 14,336 evaluations) and compares them with the design files of the results package when given. |

Files: `HOW_TO_USE.md` (the guide), `fetch_data.py` (gets every input; standard library, calls the builders in
`tools_extra/`), `repro.py` (helpers used by the notebooks; standard library + pandas), `sensitivity.py` (Morris and
Sobol designs, the factor table, evaluation and indices; SALib), `requirements-colab.txt` (pinned tested environment,
Python 3.13.5), `inputs_manifest.csv` (paths, sizes and SHA-256 per group: `raw_input`, `derived`, `code`).

Notes:

- The results (100 seeds, every queued scenario) were produced with the queues in `config/queues/` and the chain
  scripts of `code/` (top-level README, "Run the queues"), not with these notebooks. The sensitivity results are in
  `outputs/sensitivity/` (the A5 grid now; Morris, Sobol and feasibility land with the final pass).
- The default stone rule is `hybrid`, the rule of the full audited run (the per-site file is included in
  `data/nurnet/`). With `stone_rule: stones7` the haul tables, and therefore all results, differ.
- A whole-island alliance run needs about 1-3 GB per MPI rank.
