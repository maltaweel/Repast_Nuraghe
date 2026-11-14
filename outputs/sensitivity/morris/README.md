# morris: Morris screens

**Not included.** This folder holds no results; `notebooks/06_sensitivity.ipynb` runs the Morris screen of the
headline (demo size, and regenerates the full design). `../export.py` exports a screen from its run harness (island
level only) into the files below:

- 32-factor screen (r = 10 trajectories, 330 evaluations x seeds 1-3): `morris32_design.csv`, `morris32_factors.csv`,
  `morris32_problem.json`, `morris32_runs.csv` (one row per evaluation and seed), `morris32_ee.csv` (elementary
  effects), `morris32_indices.csv` (mu*, its 95% bootstrap CI `mu_star_conf`, mu, sigma, relative mu*, seed-noise
  floor, per factor and output).
- Physical screen (pull, drag, tonnage, load/unload time, minimum haul; k = 5, r = 10, 60 single-seed runs, drag
  range 0.19-1.0 m/s): `morris_phys_runs.csv` (one row per run), `morris_phys_indices.csv` (mu*, its 95% bootstrap
  CI, mu, sigma per factor and output).
