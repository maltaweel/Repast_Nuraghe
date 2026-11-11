# sensitivity/sobol2: Sobol run 2 (headline scenario)

Sobol sensitivity analysis of the headline scenario `MOST_REALISTIC_AUDITED_LIT_P10` on code v17. Results:
[`outputs/sensitivity/sobol2/`](../../outputs/sensitivity/sobol2/). Placeholders and the run-folder layout:
[`sensitivity/README.md`](../README.md).

## What it runs

- **Design:** Saltelli, SALib 1.6.0 `sobol.sample(N=512, calc_second_order=False, scramble=True, seed=20261110)`,
  k = 26 factors, N (k + 2) = 14,336 evaluations. Rows in SALib order (per base row: A, AB_1..AB_26, B).
- **Factors:** the 24 candidates retained by the Morris screen (ranges from `morris_v16f/factors.csv`, the screen's
  factor table), the neighbour radius `R_m` (5-15 km) and `lift_learning` (two levels: lift undiscounted = the v17
  headline; lift discounted by learning and skill = the v16_final rule). Fixed at the headline: the eight factors
  the Morris screen dropped and the A5 alliance threshold. `python sobol2_v17.py design` writes the full list
  (`factors.csv`, `problem.json`).
- **Level mapping** of the uniform sample u: continuous lo + u (hi - lo); binary u < 0.5 -> the headline level,
  else the alternative; integer factors in equal-probability bins, lo + floor(u (hi - lo + 1)).
- **One evaluation** = one design row x seeds 1, 2, 3 (common random numbers), whole island (7,167 sites), one
  process. The configuration is read once and each factor is applied to an in-memory copy (no file is written).
- **Outputs per seed:** island years = (max finish day + 1) / season days; island man-hours = sum of `mh_total`;
  transport share = sum of `mh_transport` / sum of `mh_total`. The evaluation's value is the mean over the 3 seeds.
- **Code:** `code_v17s` = `code/` (v17) + one configuration flag, `sobol.lift_learning`, for the factor
  `lift_learning`. With the flag absent or false the variant is code v17 exactly (same CODE_VERSION; the flag is
  hashed into the run signature only when on). On the project's machine the flag-off variant gave byte-identical
  per-site results to code v17 on the headline (seeds 1-2), and the flag-on variant reproduced the v16_final lift.

## Files

| file | what |
|---|---|
| `sobol2_v17.py` | the harness: `design`, `check` (dry mapping check, no simulation), `ids` (pending evaluations), `eval --id N` (one evaluation -> `evals/NN/eval_NNNNN.csv` + `.ok`), `eval --id headline [--seeds 1,2,3]` |
| `analyse.py` | S1 and ST with 95% bootstrap confidence intervals (SALib `sobol.analyze`, 1,000 resamples, seed 1) per output, and the same on the first 256 base rows (convergence check); refuses to run before all evaluations are done unless `--partial` |
| `chain.sh` | the driver used on the project's machine (worker pool read from `WORKERS`, memory guard, resume); its start condition waits for the project's own v17 rerun chain, so elsewhere use the commands below |
| `morris_v16f/factors.csv` | the Morris screen's factor table, read by the harness (ranges and justifications) |
| `code_v17s.patch` | patch that turns `code/` into `code_v17s` (5 files) |
| `code_v17s/` | the 5 changed or new files themselves: `alliance.py`, `lit.py`, `model.py`, `tests/test_v17_lift.py`, `tests/test_v17s_lift_learning.py` (8 tests of the flag) |
| `code_v17s/SHA256SUMS_RUN` | SHA-256 of these 5 files in the run's code folder. `model.py` and `tests/test_v17s_lift_learning.py` match byte for byte; `alliance.py`, `lit.py` and `tests/test_v17_lift.py` differ only in comments and paths, scrubbed as in `code/` (`CODE_PROVENANCE.md`) |

## How to run

```
# code variant (from the repository root)
cp -r code $RUN/code_v17s && (cd $RUN/code_v17s && git apply $REPO/sensitivity/sobol2/code_v17s.patch)
# tests of the flag (test_v17s_lift_learning.py also needs the v16_final code next to it, as $RUN/code_v16_final:
#   git -C $REPO archive 987a345~1 code | tar -x -C /tmp && mv /tmp/code $RUN/code_v16_final)
# NURAGHE_PROJECT: a folder holding runs/2026-11-02-v12-census/full_audited/v16_final/configs/config_full_audited.yaml
# (the layout the published tests expect; notebooks/repro.py builds it for test_v17_lift.py)
(cd $RUN/code_v17s && NURAGHE_PROJECT=/path/to/layout python tests/test_v17s_lift_learning.py)

# harness (after copying this folder to $WORK and replacing the placeholders, see ../README.md)
cd $WORK
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 OMPI_MCA_btl=self
python sobol2_v17.py design                     # design.csv, factors.csv, problem.json
gzip -dc $REPO/outputs/sensitivity/sobol2/design.csv.gz | cmp - design.csv && echo "same design as published"
python sobol2_v17.py check                      # dry mapping check
python sobol2_v17.py eval --id headline --seeds 1   # smoke test: all factors at the headline
python sobol2_v17.py ids | xargs -P 4 -I{} python sobol2_v17.py eval --id {}   # all evaluations, 4 in parallel
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
- `test_v17s_lift_learning.py`: light (fake models with the real methods, no simulation).

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
