# sobol2: Sobol run 2 on the headline

**Status: the inputs are here; the results land with the final pass** (the run was 6,343 of 14,336 evaluations
on 11 Nov 2026). Until then this folder holds only the design.

## Design (inputs, here now)

- Headline cell `MOST_REALISTIC_AUDITED_LIT_P10`, configuration `config/scenarios/config_full_audited.yaml`
  (read-only; each factor is applied to an in-memory copy).
- Code: `code/` with one added config flag, `sobol.lift_learning` (factor 26).
  Flag off = `code/` exactly (checked per site, bit for bit, on seeds 1-2); flag on = an earlier lift rule
  (lift discounted by learning and skill). The code variant (a patch on `code/`) and the run harness are in
  `sensitivity/sobol2/`.
- Saltelli design: SALib 1.6.0 `sobol.sample(N=512, calc_second_order=False, scramble=True, seed=20261110)`,
  k = 26, so N (k + 2) = **14,336 evaluations**. One evaluation = one design row x seeds 1, 2, 3 (common random
  numbers); its value is the 3-seed mean. 43,008 model runs. Started 10 Nov 2026.
- Outputs: island years = (max finish day + 1) / season days; island man-hours = sum of `mh_total`; transport share
  = sum `mh_transport` / sum `mh_total`.
- Level mapping of the uniform sample u: `unif` lo + u (hi - lo); `int` lo + floor(u (hi - lo + 1)) (equal-probability
  bins); `binary` u < 0.5 -> the first level (headline), else the second.
- Fixed at the headline: relay_fractions, delta_up, setup_mh, alpha, relay_min_flatm, block_min_kg, transfer_h,
  delta_down, the A5 alliance_threshold.

| factor | kind | range / levels | headline |
|---|---|---|---|
| season_days | unif | 40-120 | 90 |
| n_phases | int | 5-15 | 10 |
| stone_rule | binary | hybrid, stones7 | hybrid |
| hardness_hard | unif | 1-3 | 2 |
| dress_rule | binary | by_towers, webster_all | by_towers |
| help_mode | binary | join, handover | join |
| max_asks | int | 1-5 | 3 |
| long_min_haul_m | unif | 500-1,500 | 1,000 |
| specialisation | binary | true, false | true |
| bedrock_everywhere | binary | true, false | true |
| beta0 | unif | -1-1 | 0 |
| lift_share_of_build | unif | 0.25-0.75 | 0.5 |
| split_cost_mh | unif | 0-2 | 1 |
| p_imit | unif | 0.15-0.45 | 0.3 |
| beta3 | unif | 0.1-0.3 | 0.2 |
| trust0 | unif | 0.25-0.75 | 0.5 |
| lift_rule | binary | by_type, stair_all | by_type |
| beta1 | unif | 1-3 | 2 |
| beta2 | unif | 0.025-0.075 | 0.05 |
| stair_lever_last_m | unif | 0.5-1.5 | 1 |
| rho_limestone | unif | 2,420-2,711 | 2,600 |
| learning_rate | unif | 0.075-0.225 | 0.15 |
| near_site_fixed_face_m | unif | 500-1,500 | 1,000 |
| min_haul_flatm | unif | 10-20 | 15 |
| R_m | unif | 5,000-15,000 | 10,000 |
| lift_learning | binary | false, true | false |

Config keys, sources and the reason for each range: `factors.csv`.

| file | content |
|---|---|
| `design.csv.gz` | 14,336 rows: eval_id, base_row, block (A, AB_<factor>, B), the 26 uniform values `u_*` and the 26 mapped factor values |
| `factors.csv` | the 26 factors: config key, kind, range or levels, headline value, source and reason |
| `problem.json` | the SALib problem, N, sampler, seeds, scenario, code, configuration, level mapping |

## Results (with the final pass)

Exported by `../export.py` once all 14,336 evaluations have a result:

| file | content |
|---|---|
| `runs.csv.gz` | one row per model run (evaluation x seed): eval_id, base_row, block, seed, island_years, island_mh, mh_transport_share, seasons, status |
| `per_eval.csv.gz` | one row per evaluation: the 3-seed means (the values the indices use), status, number of seeds |
| `indices.csv` | S1 and ST with 95% bootstrap CIs per output and factor (N = 512) |
| `indices_N256.csv` | the same on the first 256 base rows (convergence check) |
