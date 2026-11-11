# sensitivity/coop_sobol: cooperation-model Sobol

Sobol sensitivity analysis of the cooperation model on code v17, repeating the design of an earlier (28 October
2026) cooperation-model Sobol with the final code and sourced ranges. Results:
[`outputs/sensitivity/coop_sobol/`](../../outputs/sensitivity/coop_sobol/). Placeholders and the run-folder layout:
[`sensitivity/README.md`](../README.md).

## What it runs

- **Model:** engine B (`code/model.py`, the day engine, numba kernel), the cooperation scenarios `none`, `mixed`
  and `full` of `scenarios.list` (p_coop 0.0 / 0.5 / 1.0; no inter-site help, no phasing, no literature stages).
  Code: `code/` as published (`@RUN_DIR@/code_v17`), imported read-only.
- **Design:** Saltelli, SALib 1.6.0 `sobol.sample(N=512, calc_second_order=False, scramble=True, seed=20261110)`,
  k = 11 factors, N (k + 2) = 6,656 rows, run in each of the 3 scenarios: 19,968 evaluations.
- **Factors (11):** pull per person, drag speed, other man-days per tower, block median and sigma, builders
  multiplier, tonnes per tower, load/unload time, hours per day, minimum haul, household size; ranges, distributions
  and sources in `factors.csv` (written by `design`).
- **Level mapping:** continuous lo + u (hi - lo); log-uniform exp(ln lo + u (ln hi - ln lo)); integer factors in
  equal-probability bins.
- **One evaluation** = one design row x one scenario x one seed, whole island (7,167 sites), one process (MPI
  singleton). Seed = base row + 1, shared by the A, AB_i and B rows of a base row and by the 3 scenarios.
- **Outputs:** `island_total_mh`, `island_transport_mh`, `island_days_max`, `median_site_total_mh_TWR1..7`
  (median over the sites with that tower count; TWR6 and TWR7 have very few sites, so their medians are noisy),
  and `island_days_p95`, `median_site_days_TWR1..7`, `n_splits`, `n_blocks`.
- `COOPSOBOL_MAX_DAYS=200000` (set in `chain.sh`; export it yourself otherwise) raises the model's safety stop so
  that the slowest corner of the design finishes instead of being cut off. It only stops runs; finished runs are
  unchanged by it.

## Files

| file | what |
|---|---|
| `coopsobol_v17.py` | the harness: `design`, `check` (dry mapping check), `ids` (pending evaluation ids, gid = scenario index x 6,656 + row, order none, mixed, full), `eval --gid G` (-> `evals/<scenario>/NN/eval_RRRRR.csv` + `.ok`), `eval --baseline --scenario S --seed s` |
| `analyse.py` | S1 and ST with 95% bootstrap confidence intervals per scenario and output (SALib `sobol.analyze`, 1,000 resamples, seed 1), the same on the first 256 base rows, and an optional comparison with the 28 October indices (not published); `--partial` for a look before the end |
| `analyse_n256.py` | indices from a prefix of the design (base rows 0..N-1, N a power of 2), e.g. `--n 256` once the first half is done; `--complete-only` uses the largest complete prefix |
| `chain.sh` | the driver used on the project's machine (worker pool read from `WORKERS`, memory guard, resume, code checksum check, then `analyse.py`) |
| `chain_halves.sh` | the same driver with the halves-first order (base rows 0-255 in all scenarios first, so that a complete N = 256 design exists half way); it takes over from a paused `chain.sh` |

The code checksum check in the chain scripts compares `code_v17` with `CODE_V17_SHA256SUMS`; the published `code/` has
scrubbed comments in some files (`CODE_PROVENANCE.md`), so on a copy of `code/` use `notebooks/repro.py`'s
`code_audit` instead, or the commands below.

## How to run

```
# after copying this folder to $WORK and replacing the placeholders (../README.md); $RUN/code_v17 = a copy of code/
cd $WORK
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 OMPI_MCA_btl=self
export COOPSOBOL_MAX_DAYS=200000
python coopsobol_v17.py design                  # design.csv, factors.csv, problem.json
gzip -dc $REPO/outputs/sensitivity/coop_sobol/design.csv.gz | cmp - design.csv && echo "same design as published"
python coopsobol_v17.py check                   # dry mapping check
python coopsobol_v17.py eval --baseline --scenario mixed --seed 1   # smoke test -> checks/
python coopsobol_v17.py ids | xargs -P 2 -I{} python coopsobol_v17.py eval --gid {}   # all evaluations
python analyse.py                               # indices_coopsobol.csv, indices_coopsobol_N256.csv, per_eval.csv
python analyse_n256.py --n 256                  # optional: indices on the first half only
```

Evaluations with an `.ok` file are skipped, so the `xargs` line can be rerun after an interruption. For the
halves-first order, feed the ids with base row < 256 first. Regenerating the design from the published files gives
a `design.csv` identical to `outputs/sensitivity/coop_sobol/design.csv.gz` (checked).

## Runtime and memory (from the project's logs)

- One evaluation (one whole-island run): 28 s median, 45 s 95th percentile, 476 s maximum (3,235 evaluations,
  several sharing the CPUs).
- Peak memory per evaluation: 2.0 GB median, 4.1 GB 95th percentile, 6.6 GB maximum (resident set size of the
  process tree). Size the number of parallel evaluations by the maximum, not the median.
- Whole design: 19,968 evaluations, about 100-170 core-hours.
- `analyse_n256.py`: seconds, under 1 GB (it reads only the design and the evaluation files).

## How the outputs map to outputs/sensitivity/coop_sobol/

| harness output | published file |
|---|---|
| `design.csv`, `factors.csv`, `problem.json` | `design.csv.gz`, `factors.csv`, `problem.json` (paths removed) |
| `evals/<scenario>/NN/eval_RRRRR.csv` (one row per evaluation) | `per_eval.csv.gz` (all scenarios; process columns dropped) |
| `indices_coopsobol.csv` | `indices.csv` (column `scenario`; recomputed by `outputs/sensitivity/export.py` and checked against the run's file to 1e-9) |
| `indices_coopsobol_N256.csv` | `indices_N256.csv` |
| `analyse_n256.py --n 256` (first half only) | `indices_N256.csv` / `per_eval_N256.csv.gz` when exported with `export.py --coop-prefix 256` |
