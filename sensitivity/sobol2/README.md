# sensitivity/sobol2: Sobol run 2 (headline scenario)

Sobol sensitivity analysis of the headline scenario `MOST_REALISTIC_AUDITED_LIT_P10` on the model's code. Results:
[`outputs/sensitivity/sobol2/`](../../outputs/sensitivity/sobol2/). Placeholders and the run-folder layout:
[`sensitivity/README.md`](../README.md).

## What it runs

- **Design:** Saltelli, SALib 1.6.0 `sobol.sample(N=512, calc_second_order=False, scramble=True, seed=20261110)`,
  k = 26 factors, N (k + 2) = 14,336 evaluations. Rows in SALib order (per base row: A, AB_1..AB_26, B).
- **Factors:** the 24 candidates retained by the Morris screen (ranges from `morris/factors.csv`, the screen's
  factor table), the neighbour radius `R_m` (5-15 km) and `lift_learning` (two levels: lift undiscounted = the
  headline; lift discounted by learning and skill = an earlier rule). Fixed at the headline: the eight factors
  the Morris screen dropped and the A5 alliance threshold. `python sobol2.py design` writes the full list
  (`factors.csv`, `problem.json`).
- **Level mapping** of the uniform sample u: continuous lo + u (hi - lo); binary u < 0.5 -> the headline level,
  else the alternative; integer factors in equal-probability bins, lo + floor(u (hi - lo + 1)).
- **One evaluation** = one design row x seeds 1, 2, 3 (common random numbers), whole island (7,167 sites), one
  process. The configuration is read once and each factor is applied to an in-memory copy (no file is written).
- **Outputs per seed:** island years = (max finish day + 1) / season days; island man-hours = sum of `mh_total`;
  transport share = sum of `mh_transport` / sum of `mh_total`. The evaluation's value is the mean over the 3 seeds.
- **Code:** `code_variant` = `code/` + one configuration flag, `sobol.lift_learning`, for the factor
  `lift_learning` (`code_variant.patch`). With the flag absent or false the variant is `code/` exactly (same
  CODE_VERSION; the flag is hashed into the run signature only when on). On the project's machine the flag-off variant
  gave byte-identical per-site results to `code/` on the headline (seeds 1-2), and the flag-on variant reproduced the
  earlier lift rule.

## Files

| file | what |
|---|---|
| `sobol2.py` | the harness: `design`, `check` (dry mapping check, no simulation), `ids` (pending evaluations), `eval --id N` (one evaluation -> `evals/NN/eval_NNNNN.csv` + `.ok`), `eval --id headline [--seeds 1,2,3]` |
| `analyse.py` | S1 and ST with 95% bootstrap confidence intervals (SALib `sobol.analyze`, 1,000 resamples, seed 1) per output, and the same on the first 256 base rows (convergence check); refuses to run before all evaluations are done unless `--partial` |
| `morris/factors.csv` | the Morris screen's factor table, read by the harness (ranges and justifications) |
| `code_variant.patch` | patch that turns a copy of `code/` into `code_variant` (`alliance.py`, `lit.py`, `model.py`) |

The driver script of the project's machine and the unit tests of the flag (which compare it with an earlier code
version) are in the git history.

## How to run

```
# code variant (from the repository root)
cp -r code $RUN/code_variant && (cd $RUN/code_variant && git apply $REPO/sensitivity/sobol2/code_variant.patch)

# harness (after copying this folder to $WORK and replacing the placeholders, see ../README.md)
cd $WORK
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 OMPI_MCA_btl=self
python sobol2.py design                     # design.csv, factors.csv, problem.json
gzip -dc $REPO/outputs/sensitivity/sobol2/design.csv.gz | cmp - design.csv && echo "same design as published"
python sobol2.py check                      # dry mapping check
python sobol2.py eval --id headline --seeds 1   # smoke test: all factors at the headline
python sobol2.py ids | xargs -P 4 -I{} python sobol2.py eval --id {}   # all evaluations, 4 in parallel
python analyse.py                               # indices_sobol2.csv, indices_sobol2_N256.csv, per_eval_means.csv
```

Evaluations with an `.ok` file are skipped, so the `xargs` line can be rerun after an interruption. Regenerating the
design from the published files gives a `design.csv` identical to `outputs/sensitivity/sobol2/design.csv.gz`
(checked).

## Runtime and memory (from the project's logs)

- One evaluation (3 whole-island runs): about 50 s on a free core (pilot and Morris screen); 91 s median, 155 s
  95th percentile, 546 s maximum as logged with several evaluations sharing the CPUs (6,400 evaluations).
- Peak memory per evaluation: 0.93 GB median, 0.98 GB maximum (resident set size of the process tree).
- Whole design: 14,336 evaluations, about 190-380 core-hours; with 4 workers about 2-4 days. Memory scales with the
  number of workers (about 1 GB each).

## How the outputs map to outputs/sensitivity/sobol2/

| harness output | published file |
|---|---|
| `design.csv`, `factors.csv`, `problem.json` | `design.csv.gz`, `factors.csv`, `problem.json` (paths removed) |
| `evals/NN/eval_NNNNN.csv` (one row per seed) | `runs.csv.gz` (process columns such as wall time and PID dropped) |
| 3-seed mean per evaluation (`per_eval_means.csv`) | `per_eval.csv.gz` |
| `indices_sobol2.csv` | `indices.csv` (recomputed by `outputs/sensitivity/export.py` and checked against the run's file to 1e-9) |
| `indices_sobol2_N256.csv` | `indices_N256.csv` |

`outputs/sensitivity/export.py` reads the run folders from the project's layout (constants at its top) and writes
these tables, `MANIFEST.csv` included.
