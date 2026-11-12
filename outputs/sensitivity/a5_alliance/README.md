# a5_alliance: alliance-model sensitivity grid (complete)

Full factorial grid on scenario `A5_full` (requests, trust, specialisation, tracks, shared quarry), defined in
`config/scenarios/config_full_audited.yaml` under `alliance.sensitivity`:

| factor | config key | levels |
|---|---|---|
| neighbour radius `R_m` (m) | `alliance.sensitivity.R_m` | 5,000, 10,000, 20,000 |
| learning progress ratio `b` (per doubling; 1.0 = no learning) | `alliance.sensitivity.b` | 0.85, 0.95, 1.0 |
| track cost (man-hours per m) | `alliance.sensitivity.track_cost_mh_per_m` | 0.5, 2.0, 5.0 |

27 cells (`SENS_R<R_m>_b<b>_t<track cost>`) plus the reference `A0_alone` (no cooperation), each **N = 100 seeds
(1-100)**. All other parameters at the configuration's values.

## Provenance

- Code: `code/`, configuration `config/scenarios/config_full_audited.yaml`.
- Runs: the 27 cells, seeds 1-100, on 9 Nov 2026 (8 MPI ranks). That job stopped at its final report step only,
  because `A0_alone` had not yet been run with this code. On 10 Nov 2026 `A0_alone` was run (seeds 1-100), then the cell
  job was rerun on 4 ranks (it reused the finished per-seed results of the same code version: the run signature
  includes CODE_VERSION) and wrote the per-cell summaries and `sensitivity.csv`. Exit 0, no out-of-memory event.
- Commands (from `code/`; `CFG=../config/scenarios/config_full_audited.yaml` with `data_dir` set):

```
mpirun -n 4 python model.py $CFG --seeds 1-100 --no-shapefile --alliance sensitivity   # the 27 cells
mpirun -n 4 python model.py $CFG --seeds 1-100 --no-shapefile --alliance A0_alone      # the reference
python report_alliance.py $CFG --sensitivity                                            # sensitivity.csv
python outputs/sensitivity/export.py --project <project> --only a5 ...                  # the tables here
```

- Exported 11 Nov 2026 by `../export.py`.

## Files

| file | rows | content |
|---|---|---|
| `design.csv` | 28 | scenario name, base scenario, R_m, b, track_cost_mh_per_m, seeds |
| `sensitivity.csv` | 27 | the model's own grid summary (`report_alliance.sensitivity`), copied unchanged: island man-hours mean / min / max over the 100 seeds, `pct_vs_A0` (% change of the mean island man-hours against A0_alone), share of work received as help, share of track work, mean number and size of alliances, median man-hours and years of single-tower nuraghi |
| `cells.csv` | 28 | one row per scenario: every scalar of the scenario's `stats.json` (means, sd, min, max, p5, p95 over seeds of island man-hours by channel, island seasons and years, shares, alliance statistics, relay shares), `pct_vs_A0`, and the 95% t-interval of the mean island man-hours and island seasons (`*_mean_ci95_lo` / `_hi`, n = 100) |
| `island_by_seed.csv` | 2,800 | one row per scenario and seed (one model run): island seasons, `island_years_p95` (95th percentile of the sites' finish season; `_cohortsum` = the earlier per-cohort rule, kept for the record), island man-hours in total and by channel (quarry, dress, transport, build, lift, setup, track, walk) |
| `strategy_by_season.csv` | 532 | one row per scenario and 25-season bin: towers started, shares of strategies chosen (quarry face, requests by stage, relay, track, imitation) |

Island level only: the per-site files of the runs (`nuraghe_manhours_*.csv`, `specialisation.csv`) are not exported.
