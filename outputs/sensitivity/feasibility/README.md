# feasibility: feasibility grid

**Lands with the final pass.** The grid had not been run on the model's code on 11 Nov 2026; this folder is empty until then.

Planned contents (exported by `../export.py` from the rerun harness, island level only):

- `grid.csv`: one row per grid point and seed (one model run) on the sourced ranges: pull per person (log-spaced
  levels, 20-60 kg) x drag speed (log-spaced levels, 0.19-1.0 m/s) x tonnes per tower (1,350, 1,909, 2,481), seed 1;
  finished or censored, island seasons and man-hours.
- `boundary_seeds.csv`: seeds 1-10 on the cells next to the feasibility boundary (only if a grid point is censored).

The README will then give the command, dates, the grid actually run and the censoring rule.
