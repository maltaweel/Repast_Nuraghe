# Code provenance

## The run snapshot

The full audited run (2-4 November 2026; configuration `config/config_full_audited.yaml`, queues
`config/queues/`) used ONE frozen copy of the code. The SHA-256 checksums of that snapshot, written when it was
frozen, are in `CODE_SHA256SUMS` (copied unchanged; 107 files: every `.py`, `.sh` and `.yaml` file of the
snapshot except `full_chain.sh`). `code/` in this repository is that snapshot, scrubbed for publication.

Check: `cd code && sha256sum -c ../CODE_SHA256SUMS`. Result for this repository: **46 OK** (byte-identical to the
run), **56 FAILED** (scrubbed, listed below), **5 missing** (excluded, listed below).

## What the scrub changed

Only comments, docstrings, prose and paths; no model logic, parameter value or random draw. Concretely:

- **Comments / docstrings / prose**: internal names and operational notes removed; quotes and timestamps of
  messages replaced by "specified by the authors"; the per-site building-stone source cited as "Nurnet's data
  (site building stone)"; absolute paths in comments written as `$NURAGHE_PROJECT`, `$NURAGHE_RUN_DIR`,
  `$NURAGHE_DATA`, `$PYTHON`.
- **Functional absolute paths** (scripts and post hoc tools of the project's earlier runs) replaced by environment
  variables, with identical behaviour when the variables are set to the original folders:
  - shell: `W=<absolute project path>/runs/...` -> `W=${NURAGHE_PROJECT:?...}/runs/...` (the run folder of `full_chain.sh` is
    `${NURAGHE_RUN_DIR:?...}`); `PY=<project venv>/bin/python` -> `PY=${PYTHON:-python3}`;
  - Python: `"<absolute project path>/<x>"` -> `os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "<x>")`;
    the soil map path in `tools/v12_checks.py` -> `os.path.join(os.environ.get("NURAGHE_DATA", "data"), "soils", "soils250k.geojson")`.
- **Configuration values** in `code/config*.yaml`: `data_dir` -> a placeholder; `materiale.citation` (a metadata
  string, not read by any computation) -> "Nurnet's data (site building stone)". YAML-parsed, the three files
  are identical to the snapshot apart from these two keys.
- **Output label strings** (text written into summary tables, no effect on any number) in
  `tools/scenario_guide.py` (a personal name -> "the authors' ..."; a collaborator's name removed from one label),
  `tools/v11_summary.py` (one label) and `tools/v12_ranking.py` (one `rating_source` label).

**How this was confirmed.** For every changed `.py` file the token stream without comments and docstrings was
compared with the snapshot (Python `tokenize`/`ast`); for `.sh` and `.yaml` files the lines without their comment
part. The only non-comment differences are the edits listed in the last column below. Model core files that are
byte-identical to the run: `model.py`, `nbcommon.py`, `sea.py`, `census_v12.py`, `pre_networks.py`, `report.py`,
`report_alliance.py`, `memrun.py`, `tools/kbest_quarries.py`, `tools/kbest_mu038.py`, `tools/sea_routes.py`,
`tools/build_cost_mu.py`, `tools/wl_inputs.py`, `tools/food_capacity.py`, `tools/haul_far.py` and all
`tests/*.py` except `tests/verify_alliance_identity.py`. `alliance.py`, `lit.py`, `preprocess.py` and
`phasing.py` differ in comments/docstrings only. The configs in `config/` were checked the same way: YAML-parsed,
each equals its run copy apart from `data_dir`, `paths.sites`, `materiale.file`, `materiale.citation` and the
relative form of `cache_dir`/`output_dir` (which resolve to the same folders in the run-folder layout of the
README).

## Changed files (58; 206 lines in total)

| File | In CODE_SHA256SUMS | Lines changed | What changed |
|---|---|---|---|
| `METHODS.md` | no | 39 | prose (names, message quotes/timestamps, stone-data citation) |
| `alliance.py` | yes | 4 | comments/docstrings |
| `aud_chain.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `config.ship.yaml` | yes | 1 | comments/docstrings |
| `config.yaml` | yes | 20 | comments/docstrings; data_dir -> placeholder; materiale.citation string |
| `config_smallcrew_test.yaml` | yes | 15 | comments/docstrings; data_dir -> placeholder; materiale.citation string |
| `full_chain.sh` | no | 4 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `gaps_chain.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `lit.py` | yes | 1 | comments/docstrings |
| `night_chain.sh` | yes | 8 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `phasing.py` | yes | 1 | comments/docstrings |
| `pop_chain.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `preprocess.py` | yes | 1 | comments/docstrings |
| `rerun1030.sh` | yes | 4 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `rerun1030b.sh` | yes | 4 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `run_all.sh` | yes | 1 | comments/docstrings |
| `run_subset_real.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `run_subset_sea.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `season_alone_runs.sh` | yes | 1 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `season_runs.sh` | yes | 2 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/gaps_subset.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/identity_merged.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/identity_merged_nolock.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/identity_phase_off.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/most_realistic_subset.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/mr_join_subset.sh` | yes | 1 | functional path -> env variable |
| `tests/mr_join_subset_body.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/phase_subset.sh` | yes | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/v11_subset.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/v12_item11.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/v12_subset.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tests/verify_alliance_identity.py` | yes | 2 | comments/docstrings |
| `tests/wl_subset.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `tools/_scen.py` | yes | 1 | functional path -> env variable |
| `tools/alliance_networks.py` | yes | 2 | comments/docstrings |
| `tools/census.py` | yes | 2 | comments/docstrings |
| `tools/centrality.py` | yes | 4 | comments/docstrings; functional path -> env variable |
| `tools/check_independence.py` | yes | 1 | functional path -> env variable |
| `tools/family_summary.py` | yes | 1 | functional path -> env variable |
| `tools/fastest_params.py` | yes | 3 | comments/docstrings |
| `tools/formation.py` | yes | 2 | comments/docstrings |
| `tools/formation_plot.py` | yes | 1 | comments/docstrings |
| `tools/master_table.py` | yes | 1 | comments/docstrings |
| `tools/morris_mr.py` | yes | 6 | comments/docstrings |
| `tools/network_need.py` | yes | 2 | comments/docstrings |
| `tools/phased_posthoc.py` | yes | 1 | comments/docstrings |
| `tools/scenario_guide.py` | yes | 5 | output label text (names only) |
| `tools/stone_rule.py` | yes | 2 | comments/docstrings |
| `tools/v11_queue.py` | yes | 1 | comments/docstrings |
| `tools/v11_summary.py` | yes | 2 | functional path -> env variable; output label text (names only) |
| `tools/v12_checks.py` | yes | 2 | functional path -> env variable |
| `tools/v12_queue.py` | yes | 1 | comments/docstrings |
| `tools/v12_ranking.py` | yes | 3 | functional path -> env variable; output label text (names only) |
| `tools/v12_summary.py` | yes | 1 | functional path -> env variable |
| `tools/workforce_years.py` | yes | 2 | comments/docstrings |
| `v11_chain.sh` | yes | 4 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `v12_chain.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `wl_chain.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |

## Excluded from the repository, and why

| Item | Why |
|---|---|
| all working-note `.md` files of the snapshot except `METHODS.md` (bug reports, run notes, realism ratings, scenario plans, review notes, catalogue drafts, patch notes) | internal working notes with message quotes, timestamps and internal names. `METHODS.md` is kept, scrubbed; it still refers to some of these notes by name |
| `literature/` (two literature reviews, a scenario plan, a PDF of a published article) | verbatim passages of copyrighted works and a copyrighted PDF |
| `report/make_report.py` (+ two report notes) | PDF report builder that copies text verbatim from the excluded notes and literature reviews and credits internal agents; not needed to run the model |
| `tools/components.py`, `tools/master_comparison.py` | post hoc checks that read a collaborator's private output files by name (and write that name into their outputs); not needed to run the model |
| `gpu/` (`coop_kernel.py`, `coop_kernel_pr.py`, two `.diff` files) | GPU port that imports GPU modules not in the snapshot (a collaborator's code); not runnable here and not used by the full audited run |
| `v11_to_v12.patch`, `__pycache__/` | development patch with internal notes; bytecode |

`run_all.sh` still names `tools/components.py`, `tools/master_comparison.py` and `report/make_report.py` in its last
lines (step 8); those three calls fail in this repository. Nothing in `full_chain.sh` or the queues uses them.

## Not part of the snapshot

`tools_extra/build_slope.py` (the slope raster, see `data/derived/README.md`), `config/check_sea_meta.py` (run-level
check called by the queue; comments scrubbed) and `notebooks/repro.py` (adapted to the repository layout) are not
in `CODE_SHA256SUMS`.
