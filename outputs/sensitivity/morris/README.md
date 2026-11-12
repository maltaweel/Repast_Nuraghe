# morris: Morris screens

**Lands with the final pass.** No Morris screen on the model's code had finished on 11 Nov 2026; this folder is empty
until then.

Planned contents (exported by `../export.py` from the rerun harness, island level only):

- 32-factor screen (r = 10 trajectories, 330 evaluations x seeds 1-3, the same design as the screen on the earlier
  code): `morris32_design.csv`, `morris32_factors.csv`, `morris32_problem.json`, `morris32_runs.csv` (one row per
  evaluation and seed), `morris32_ee.csv` (elementary effects), `morris32_indices.csv` (mu*, its 95% bootstrap CI
  `mu_star_conf`, mu, sigma, relative mu*, seed-noise floor, per factor and output).
- Physical screen (pull, drag, tonnage, load/unload time, minimum haul; k = 5, r = 10, 60 single-seed runs, drag
  range 0.19-1.0 m/s): `morris_phys_runs.csv` (one row per run), `morris_phys_indices.csv` (mu*, its 95% bootstrap
  CI, mu, sigma per factor and output).

The README will then give the commands, dates, N, factors and ranges of the runs actually made.
