# Code provenance

## The run snapshot (frozen v12 code), the v13, v14 and v15 code

The full audited run (2-4 November 2026; configuration `config/config_full_audited.yaml`, queues
`config/queues/queue_full.tsv` and `queue_full_p23.tsv`) used ONE frozen copy of the code: every run started
before 2 November 2026, 22:00, used it. The SHA-256 checksums of that snapshot, written when it was frozen, are in
`CODE_SHA256SUMS` (copied unchanged; 107 files: every `.py`, `.sh` and `.yaml` file of the snapshot except
`full_chain.sh`).

**v13.** On 2 November the run's code folder was copied to a second folder, `code_v13/`, which adds three opt-in
social switches to `alliance.py` (`reputation`, `partner_choice`, `tie_imitation`, plus the bookkeeping switch
`social_log`; ODD section 7.15). They are off by default; with all of them off, the code path, the random draws and
the run signatures are those of the frozen code. `alliance.py` is the only changed model file; `code_v13/` also has
the side-chain script `v13_side_chain.sh` that runs the five v13 entries
(`config/queues/queue_v13_social_STAGED.tsv`, configs `config/config_v13_*.yaml`). **Only these five runs use the
v13 code**; the queue's commands run from `@RUN_DIR@/code_v13` (in a run folder laid out as in the README, link
`code_v13` to this repository's `code/` as well). `CODE_V13_SHA256SUMS` holds the v13 checksums of the same 107 files as
`CODE_SHA256SUMS` (only the `alliance.py` line differs). `v13_side_chain.sh` was written after the checksum file:
SHA-256 `96882435718a6408b4b94f338081b439c57c9409f6d3b5a9ce614c3ccb15af67`.

**Identity test (switches off).** The frozen code and the v13 code were run on `config_full_audited.yaml`, the
300-site subset `code/sites300_real.txt`, seeds 1-2, one rank, and the decompressed content of every part file was
hashed (gzip headers hold time stamps). All four scenarios are identical; combined hashes (frozen = v13):

| Scenario | Signature | Part files | Combined hash |
|---|---|---|---|
| `MOST_REALISTIC_AUDITED_LIT_P10` (headline) | `923bb4fc1f6c` | 20 | `a99866a2c58f38d0` |
| `A5_full_freerider` | `635bb6a0a447` | 18 | `1b390cc1e9749f5b` |
| `P_D7_G20_kmesh4_trust` (pre-existing ties) | `44815b219875` | 18 | `75fb5d033e32a5ee` |
| `MOST_REALISTIC_S20_lintels_3t0_P10` (census lintel path, which also calls `candidates` / `request`) | `803f9dd92a21` | 20 | `f962d1f48b491873` |

**v14 (5 November 2026; superseded by v15).** The run's code folder `code_v14_nearface/` is a copy of the frozen
code with one changed model file, `alliance.py`: the near-site face rule (config key `quarry.near_site_fixed_face_m`;
`code/CHANGES_V14_NEARFACE.md`, `code/METHODS.md`, ODD 7.6). With the key absent, none or 0 the code path, the random
draws and the run signatures are those of the frozen code (identity test on the headline, seeds 1, 2, 3, 17, 64,
`A5_full_freerider` and `P_G20_system_kmesh4`, seeds 1-2: every part file identical in its decompressed
content). The v14 configs (`config/v14_nearface/`, queue `config/queues/queue_v14.tsv`) are the audited
configs with `near_site_fixed_face_m: 1000` and their `cache_dir`/`output_dir` moved to `v14_nearface/outputs`; the
queue holds the audited entries the rule affects (every entry with a face choice), run with `code/v14_chain.sh` (in a
run folder, link `code_v14_nearface` to this repository's `code/`). The v14 rerun was superseded by v15 and not
completed; its configs and queue are kept as a record. `CODE_V14_SHA256SUMS` holds the v14 checksums of the same 107 files as `CODE_SHA256SUMS` (only the
`alliance.py` line differs); `CHANGES_V14_NEARFACE.md`, `CODE_VERSION` and `v14_chain.sh` were added with the code and
are not in the checksum files.

The v14 code did not carry the v13 switches (it was built on the frozen code, not on `code_v13/`); v15 restores them.

**v15 (5 November 2026; the current `code/`).** The run's code folder `code_v15_haul15/` is `code_v13/` (the v13 social
switches, including the v13g `reputation_rule` and the v13kd `trusted_nodist`) plus, in `alliance.py`, exactly the lines
that the v14 change adds (the near-site rule; the set of added lines is identical, no line removed). Every other file is
byte-identical to `code_v13/` and `code_v14_nearface/`. With the near key absent / none / 0 and the social switches
off, the code path, the random draws and the run signatures are those of the frozen code; with the near key off, those
of the v13 code (identity test: the headline, seeds 1, 2, 3, 17, 64, `A5_full_freerider` and `P_G20_system_kmesh4`,
seeds 1-2, and all ten v13 / v13g / v13kd cells, seeds 1-2: every part file reproduced). The new minimum haul,
`transport.min_haul_flatm` 15 m instead of 100 m (the haul of a site on its outcrop and the floor of every whole
route), is a config value only: every floor in the code reads this key, and the only prepared tables that apply it,
the sea tables, are rebuilt per config by the first queue entries (`code/CHANGES_V15_HAUL15.md`). The v15 configs
(`config/v15_haul15/`, queue `config/queues/queue_v15.tsv`) are the audited and v13 configs with
`min_haul_flatm: 15` (the 200 / 210 / 300 m sensitivity configs keep theirs) and `near_site_fixed_face_m: 1000`, their
`cache_dir`/`output_dir` moved to `v15_haul15/outputs`, plus a 10 m sensitivity of the headline; the queue (every
audited, v13 and help-radius entry) is run with `code/v15_chain.sh` (in a run folder, link `code_v15_haul15` to this
repository's `code/`; the v13 queues' `@RUN_DIR@/code_v13` can be linked to it as well). The results in the paper are
being regenerated with v15. `CODE_V15_SHA256SUMS` holds the v15 checksums of the same 107 files as `CODE_SHA256SUMS`
(only the `alliance.py` line differs); `CHANGES_V14_NEARFACE.md`, `CHANGES_V15_HAUL15.md`, `CODE_VERSION`, the three v13
side-chain scripts and `v15_chain.sh` (kept in the run's `v15_haul15/` folder) are not in the checksum files.

`code/` in this repository is the v15 code, scrubbed for publication.

Check: `cd code && sha256sum -c ../CODE_SHA256SUMS`. Result for this repository: **46 OK** (byte-identical to the
run), **56 FAILED** (scrubbed, listed below; `alliance.py` also carries the v13 switches and the near-site rule), **5 missing** (excluded,
listed below). Against the v13 checksums (`sha256sum -c ../CODE_V13_SHA256SUMS`): **46 OK (v13)**,
**56 FAILED (v13)**, **5 missing (v13)**. Against the v14 checksums (`sha256sum -c ../CODE_V14_SHA256SUMS`):
**46 OK (v14)**, **56 FAILED (v14)**, **5 missing (v14)**. Against the v15 checksums
(`sha256sum -c ../CODE_V15_SHA256SUMS`): **46 OK (v15)**, **56 FAILED (v15)**, **5 missing (v15)**.

**Line numbers.** The ODD (`ODD/ODD.md`) cites the v13 `alliance.py`. The tables of `param_audit/` were written
on the frozen code and cite its line numbers (the v13 rows A10-A12 are marked "(v13)"). A frozen line n of
`alliance.py` is v13 line n + k: k = 0 for n <= 55, 9 for 56-492, 12 for 493-999, 90 for 1000-1069, 92 for
1070-1112, 94 for 1113-1182, 99 for 1183-1214, 100 for 1216-1218 (frozen line 1215 = v13 lines 1314-1315),
104 for 1219-1465, 107 for 1466-1778, 113 for 1779-1810, 116 for 1811-1923, 120 for 1924-2024. The v14 file:
a frozen line n is v14 line n + k: k = 0 for n <= 55, 15 for 56-174, 22 for 175-1211, 23 for 1212-1222, 25 for
1223-1232, 28 for 1233-1923, 32 for 1924-2023. The `alliance.py` in `code/` is now the v15 file: a v13 line n (as cited
by the ODD) is v15 line n + k: k = 0 for n <= 64, 15 for 65-183, 22 for 184-1310, 23 for 1311-1326, 25 for 1327-1336,
28 for 1337-2043, 32 for 2044-2216.

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
byte-identical to the run (frozen, v13, v14 and v15 alike): `model.py`, `nbcommon.py`, `sea.py`, `census_v12.py`, `pre_networks.py`, `report.py`,
`report_alliance.py`, `memrun.py`, `tools/kbest_quarries.py`, `tools/kbest_mu038.py`, `tools/sea_routes.py`,
`tools/build_cost_mu.py`, `tools/wl_inputs.py`, `tools/food_capacity.py`, `tools/haul_far.py` and all
`tests/*.py` except `tests/verify_alliance_identity.py`. `lit.py`, `preprocess.py` and `phasing.py` differ
in comments/docstrings only; `alliance.py` differs from the v15 copy in comments/docstrings only (and from the frozen
copy by the v13 switches and the near-site rule as well). The configs in `config/` were checked the same way: YAML-parsed,
each equals its run copy apart from `data_dir`, `paths.sites`, `materiale.file`, `materiale.citation` and the
relative form of `cache_dir`/`output_dir` (which resolve to the same folders in the run-folder layout of the
README).

## Changed files (65; 235 lines in total)

| File | In CODE_SHA256SUMS | Lines changed | What changed |
|---|---|---|---|
| `CHANGES_V14_NEARFACE.md` | no | 2 | prose (names, message quotes/timestamps, stone-data citation) |
| `CHANGES_V15_HAUL15.md` | no | 3 | prose (names, message quotes/timestamps, stone-data citation) |
| `METHODS.md` | no | 42 | prose (names, message quotes/timestamps, stone-data citation) |
| `alliance.py` | yes | 9 | comments/docstrings |
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
| `requirements.txt` | no | 5 | Python line 3.10+ -> 3.12+; packages appended (imported by the code, missing from the run's list) |
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
| `v13_side_chain.sh` | no | 3 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `v13g_side_chain.sh` | no | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `v13kd_side_chain.sh` | no | 2 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `v15_chain.sh` | no | 4 | comments/docstrings; functional path -> env variable; interpreter -> ${PYTHON:-python3} |
| `wl_chain.sh` | yes | 3 | functional path -> env variable; interpreter -> ${PYTHON:-python3} |

## Excluded from the repository, and why

| Item | Why |
|---|---|
| all working-note `.md` files of the snapshot except `METHODS.md` (bug reports, run notes, realism ratings, scenario plans, review notes, catalogue drafts, patch notes) | internal working notes with message quotes, timestamps and internal names. `METHODS.md` is kept, scrubbed; it still refers to some of these notes by name |
| `literature/` (two literature reviews, a scenario plan, a PDF of a published article) | verbatim passages of copyrighted works and a copyrighted PDF |
| `report/make_report.py` (+ two report notes) | PDF report builder that copies text verbatim from the excluded notes and literature reviews and credits internal agents; not needed to run the model |
| `tools/components.py`, `tools/master_comparison.py` | post hoc checks that read a collaborator's private output files by name (and write that name into their outputs); not needed to run the model |
| `gpu/` (`coop_kernel.py`, `coop_kernel_pr.py`, two `.diff` files) | GPU port that imports GPU modules not in the snapshot (a collaborator's code); not runnable here and not used by the full audited run |
| `v11_to_v12.patch`, `v12_to_v14_nearface.patch`, `v13_to_v15_haul15.patch`, `__pycache__/` | development patches with internal notes (the v15 change is the diff of `alliance.py` between the v13 and the v15 code, described in `CHANGES_V15_HAUL15.md`; the v14 change is the diff of `alliance.py` between the frozen and the v14 code, described in `CHANGES_V14_NEARFACE.md`); bytecode |

`run_all.sh` still names `tools/components.py`, `tools/master_comparison.py` and `report/make_report.py` in its last
lines (step 8); those three calls fail in this repository. Nothing in `full_chain.sh` or the queues uses them.

## Not part of the snapshot

Not in `CODE_SHA256SUMS`, `CODE_V13_SHA256SUMS`, `CODE_V14_SHA256SUMS` or `CODE_V15_SHA256SUMS`:
- `tools_extra/build_slope.py` (the slope raster, see `data/derived/README.md`), `tools_extra/build_dem.py`,
  `tools_extra/build_lithology.py` and `tools_extra/build_rivers.py` (builders of the public input layers from their
  official downloads);
- `notebooks/fetch_data.py` (downloads the public inputs and rebuilds the files the model reads; checks them against
  `notebooks/inputs_manifest.csv`) and `notebooks/repro.py` (helpers of the notebooks, adapted to the repository
  layout);
- `config/check_sea_meta.py` (run-level check called by the queue; comments scrubbed);
- `code/requirements.txt` is in the snapshot but not in the checksum files (only `.py`, `.sh`, `.yaml` are); the
  repository copy appends `scipy`, `matplotlib` and `networkx`, which the code imports but the run's list omitted,
  and states Python 3.12+ (the run's list says 3.10+; 3.12+ is needed for byte-identical reproduction, see README).

`notebooks/inputs_manifest.csv` (group `code`) holds the size and SHA-256 of every file of this repository's `code/`
(the copy that `notebooks/repro.py` expects).
