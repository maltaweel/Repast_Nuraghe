# coop_sobol: cooperation-model Sobol on code v17

**Status: the inputs are here; the results land with the final pass.** On 11 Nov 2026 the run had 3,207 of
19,968 evaluations (scenario `none`, base rows 0-245 complete).

## Design (inputs, here now)

- The uncoupled cooperation scenarios `none`, `mixed`, `full` (p_coop 0.0, 0.5, 1.0) of
  `config/v16_final/config_full_audited.yaml`, in the day engine (`code/model.py`); configuration read-only, factors
  applied to an in-memory copy. Code: `code/` (CODE_VERSION `2026-11-09-v17`). Started 10 Nov 2026.
- The 11 factors of the earlier (28 Oct 2026) cooperation-model Sobol; four ranges changed to sourced values (see
  `factors.csv`, columns `old`, `changed`, `why`).
- Saltelli design: SALib 1.6.0 `sobol.sample(N=512, calc_second_order=False, scramble=True, seed=20261110)`,
  k = 11, so 512 x 13 = 6,656 rows, run in each of the 3 scenarios: **19,968 evaluations**, one seed each. Seed =
  base_row + 1 (the A, AB_i and B rows of a base row share their seed; the same seed in all 3 scenarios).
- Outputs: island total and transport man-hours, island days (max and p95 of the site finish days), median
  per-site man-hours and days by tower class TWR1-TWR7, number of splits and blocks. TWR6 has 7 sites and TWR7 one,
  so their medians are noisy.
- Level mapping: `unif` lo + u (hi - lo); `logunif` exp(ln lo + u (ln hi - ln lo)); `int` lo + floor(u (hi - lo + 1)).

| factor | kind | range | headline |
|---|---|---|---|
| pull_kg_per_person | logunif | 21-127 | 100 |
| drag_speed_ms | logunif | 0.19-1.0 | 0.27 |
| other_mandays_per_tower | unif | 1,200-8,000 | 2,500 |
| block_median_kg | unif | 300-1,000 | 450 |
| builders_mult | logunif | 0.5-2 | 1 |
| tonnes_per_tower | unif | 900-2,481 | 1,350 |
| block_sigma | unif | 0.3-0.9 | 0.6 |
| load_unload_h | logunif | 0.1-1.0 | 0.25 |
| hours_per_day | unif | 6-10 | 8 |
| min_haul_flatm | logunif | 10-20 | 15 |
| household_size | int | 3-8 | 5 |

| file | content |
|---|---|
| `design.csv.gz` | 6,656 rows: eval_id, base_row, block, seed, the 11 uniform values `u_*`, the 11 mapped values, `cost_proxy` (a rough relative run-time estimate used only for scheduling) |
| `factors.csv` | the 11 factors: config key, kind, range, the 28 Oct range, changed or not, reason, headline |
| `problem.json` | the SALib problem, N, sampler, seed rule, scenarios, outputs, code, configuration, level mapping |

## Run order: halves first (N = 256 is complete before N = 512)

Since 11 Nov 2026 the evaluations run in the order: base rows 0-255 in `none`, `mixed`, `full`, then base rows
256-511 in the same order. The first 256 base rows are a complete Saltelli design of N = 256: `sobol.sample(N=256)`
with the same seed gives exactly the first 3,328 rows of `design.csv`, each base row is a self-contained block (A,
AB_1..AB_11, B), and the first 256 A and B points each put one point in every 1/256 stratum of every dimension.
So indices at N = 256 are available for all three scenarios before the N = 512 run ends.

## Results (with the final pass)

Exported by `../export.py`:

| file | content |
|---|---|
| `per_eval.csv.gz` | one row per evaluation (= one model run): scenario, eval_id, gid, base_row, block, seed, status and the outputs above |
| `indices.csv` | S1 and ST with 95% bootstrap CIs per scenario, output and factor (N = 512) |
| `indices_N256.csv` | the same on base rows 0-255 (convergence check) |

If the final pass comes before N = 512 is complete, `export.py --coop-prefix 256` exports the complete N = 256
design instead (`per_eval_N256.csv.gz`, `indices_N256.csv`, labelled N = 256); the N = 512 files follow when the run
ends. The N = 256 indices are the same in both cases (same rows, same bootstrap seed).
