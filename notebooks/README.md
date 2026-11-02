# Notebooks

Five Jupyter notebooks that set up the environment, get and check the inputs, run scenarios, analyse them, and audit
the full audited run step by step. **Start with [HOW_TO_USE.md](HOW_TO_USE.md)** (Colab and Jupyter quick start,
software requirements, getting the data automatically or
[linking the data yourself](HOW_TO_USE.md#linking-the-data-yourself), the derived inputs, expected results).

**Data.** The Nurnet files (site list `nurnet_nuraghi.shp`, 7,167 nuraghi with tower counts, and the per-site
building stone) are Nurnet's data and are included in `data/nurnet/`; for the latest version and source information
contact Nurnet at nurnet.presidente@gmail.com. Every other raw input is public and is downloaded from its official
source by `fetch_data.py` (02, section 0). Derived inputs: rebuilt (`fetch_data.py --rebuild-derived`, about
30-45 min) or the prebuilt pack (`DERIVED_URL`, placeholder until the results package is public).

The folders are set at the top of each notebook's config cell (`REPO_DIR`, `DATA_DIR`, `DERIVED_DIR`, `CONFIG`,
`OUTPUTS_DIR`, `WORK_DIR`, `RESULTS_DIR`; defaults `data/`, `data/derived/cache/`, `config/config_full_audited.yaml`,
`outputs/`); the base configuration is `config/config_full_audited.yaml`; all outputs are cleared. Adapted from the
reproducibility notebooks of 31 October 2026 (code v8 package); they have not been executed end to end in this form.

## How to audit in Colab (quick start)

1. Open the five notebooks below in Colab, **in order**: 01, 02, 03, 04, 05.
2. In the config cell of each: `MOUNT_DRIVE = True` and the same Drive folders (each Colab notebook has its own
   runtime): `DATA_DIR = "/content/drive/MyDrive/Repast_Nuraghe/data"`, `DERIVED_DIR =
   "/content/drive/MyDrive/Repast_Nuraghe/data/derived/cache"`, `OUTPUTS_DIR = "/content/drive/MyDrive/Repast_Nuraghe/outputs"`.
3. Runtime > Run all. The setup cell clones the repository and installs OpenMPI and the pinned packages.
4. 05_audit prints PASS / FAIL / NOT YET AVAILABLE per step: (a) code checksums vs `CODE_SHA256SUMS`, (b) inputs vs
   `inputs_manifest.csv`, (c) `config_full_audited.yaml` vs `param_audit/PARAM_TRACE.csv`, (d) a rerun of the
   headline scenario on 300 sites, seeds 1-3, vs the fingerprint in `outputs/reference/` (placeholder), (e) island
   years and man-hours from the per-seed tables in `outputs/summary/` (placeholder).

## Open in Google Colab

- [01_setup.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/01_setup.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/01_setup.ipynb)
- [02_inputs.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/02_inputs.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/02_inputs.ipynb)
- [03_scenarios.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/03_scenarios.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/03_scenarios.ipynb)
- [04_analysis_report.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/04_analysis_report.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/04_analysis_report.ipynb)
- [05_audit.ipynb](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/05_audit.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maltaweel/Repast_Nuraghe/blob/main/notebooks/05_audit.ipynb)

Colab needs the inputs in a folder every notebook can reach: Google Drive (`MOUNT_DRIVE = True` and the Drive folders above). 02 fills it (`fetch_data.py`).

| Notebook | What it does / reproduces |
|---|---|
| `01_setup.ipynb` | Installs OpenMPI and the pinned Python packages (`requirements-colab.txt`), checks the versions, runs a 2-rank MPI smoke test and imports the model code; checks that `code/` is byte-identical to the repository version (`inputs_manifest.csv`, group `code`). |
| `02_inputs.ipynb` | Section 0 "Getting the data": every input, its source, the automatic fetch (`fetch_data.py`: copies the Nurnet files from `data/nurnet/`, downloads the public layers from the official sources, rebuilds the model files, checks SHA-256) and the manual alternative; section 0b the derived inputs (prebuilt pack `DERIVED_URL` or a full rebuild); preflight of every input (presence, size, SHA-256; files rebuilt from an official source are reported as such); a look at the sites and the cost raster; the stone rule (`hybrid`, the rule of the full audited run, by default); the work folder (`WORK_DIR/config.yaml` = the base config with only `data_dir`, `cache_dir`, `output_dir`, `stone_rule` set); an optional rebuild of the base haul table (`preprocess.py`). |
| `03_scenarios.ipynb` | Runs any scenario with `model.py` (repast4py + MPI): presets `quick` (300 sites, seeds 1-3), `full` (7,167 sites, seeds 1-100) or `custom`; resumable; island totals of the runs. The last section reruns a fixed reference subset and compares it exactly with a reference fingerprint (`OUTPUTS_DIR/reference/reference_sha256.csv`). No reference is shipped: the 31 Oct 2026 reference belongs to an earlier code version, so make one with `MAKE_REFERENCE = True` before using `RUN_REFERENCE_CHECK = True`. |
| `04_analysis_report.ipynb` | Tables per scenario and tower class, maps of man-hours per nuraghe, centrality of the help networks (`tools/centrality.py`), network need with vs without the network (`tools/network_need.py`). The PDF report builder of the project is not included. |
| `05_audit.ipynb` | The step-by-step audit, each step with its expected result: (a) `code/` vs `CODE_SHA256SUMS` and `CODE_PROVENANCE.md`; (b) raw and derived inputs vs `inputs_manifest.csv`; (c) every audited parameter of `config_full_audited.yaml` vs `param_audit/PARAM_TRACE.csv`; (d) a fresh rerun of `MOST_REALISTIC_AUDITED_LIT_P10` on 300 sites, seeds 1-3, vs `outputs/reference/reference_audit_sha256.csv` (placeholder until generated after the full run); (e) island years and man-hours recomputed from `outputs/summary/per_seed_full_audited.csv` vs `summary_full_audited.csv` (placeholder). |

Files: `HOW_TO_USE.md` (the guide), `fetch_data.py` (gets every input; standard library, calls the builders in
`tools_extra/`), `repro.py` (helpers used by the notebooks; standard library + pandas), `requirements-colab.txt`
(pinned environment of the 31 Oct 2026 package, Python 3.13.5), `inputs_manifest.csv` (paths, sizes and SHA-256 per
group: `raw_input`, `derived`, `code`).

Notes:

- The full audited results (`config_full_audited.yaml`, 100 seeds, every queued scenario) were produced with the
  queue and `code/full_chain.sh` (top-level README), not with these notebooks.
- The default stone rule is `hybrid`, the rule of the full audited run (the per-site file is included in
  `data/nurnet/`). With `stone_rule: stones7` the haul tables, and therefore all results, differ.
- A whole-island alliance run needs about 1-3 GB per MPI rank.
