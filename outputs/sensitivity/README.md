# outputs/sensitivity

Sensitivity results of the model (`code/`), published as small island-level tables. This folder is the
only place in the repository that holds numeric model results (the authors' decision of 11 Nov 2026, for the
sensitivity runs only). The headline results and all raw per-site outputs (per-site man-hours, per-site
specialisation, part files) are not in the repository.

Code: `code/` of this repository (file checksums in `CODE_SHA256SUMS`). Configuration:
`config/scenarios/config_full_audited.yaml` (the runs use this file unchanged; only `data_dir`, `cache_dir` and `output_dir` differ locally). Each subfolder's README gives
the command, the dates, N, the factors and their ranges.

| folder | what | status |
|---|---|---|
| [a5_alliance/](a5_alliance/) | alliance-model grid on A5_full: 27 cells (R_m x b x track cost) + the A0_alone reference, seeds 1-100 each | complete |
| [sobol2/](sobol2/) | Sobol run 2 on the headline `MOST_REALISTIC_AUDITED_LIT_P10`: 26 factors, Saltelli N = 512 (14,336 evaluations x seeds 1-3) | design now; results land with the final pass |
| [coop_sobol/](coop_sobol/) | cooperation-model Sobol: 11 factors x scenarios none / mixed / full, Saltelli N = 512 (19,968 evaluations, one seed each) | design now; results land with the final pass |
| [morris/](morris/) | Morris screens on the model (32-factor screen; physical 5-factor screen) | lands with the final pass |
| [feasibility/](feasibility/) | feasibility grid (pull x drag x tonnage) on the sourced ranges | lands with the final pass |

`MANIFEST.csv`: every exported file with its size, number of rows, SHA-256, its source in the project's run
folder and the export date.

## How the files are produced

`export.py` (in this folder) builds every table from the project's run folders; it only reads them.

```
python outputs/sensitivity/export.py --project <project folder> --scrub <wording table>   # export what is complete
python outputs/sensitivity/export.py --project <project folder> --dry-run                 # report only, write nothing
```

- A set's results are written only when its run has finished (every evaluation present). Base rows with an error
  evaluation are dropped whole and reported, as in the runs' own analysis scripts. The inputs (design, factors,
  problem) are written as soon as they exist. `--dry-run` analyses unfinished runs on their complete base rows
  and labels them PARTIAL; such tables are never written here.
- Sobol indices: SALib 1.6.0 `sobol.analyze(calc_second_order=False, num_resamples=1000, conf_level=0.95, seed=1)`.
  `S1_conf` / `ST_conf` are the half-widths of the 95% bootstrap confidence intervals; `*_lo` / `*_hi` = value
  minus / plus the half-width. The exporter checks its indices against the run's own analysis output when that
  exists (they must agree to 1e-9).
- Morris: mu* with a 95% bootstrap interval of the mean |EE| (1,000 resamples).
- `*.csv.gz` are gzip-compressed CSV (`pandas.read_csv` reads them directly). Floats are written with 17
  significant digits.
- The exporter stops if a text holds an absolute path, a site identifier or a name from the local wording table.
