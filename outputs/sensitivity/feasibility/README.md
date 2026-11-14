# feasibility: feasibility grid

**Not included.** This folder holds no results. `../export.py` exports the grid from its run harness (island level
only) into the files below when it has been run:

- `grid.csv`: one row per grid point and seed (one model run) on the sourced ranges: pull per person (log-spaced
  levels, 20-60 kg) x drag speed (log-spaced levels, 0.19-1.0 m/s) x tonnes per tower (1,350, 1,909, 2,481), seed 1;
  finished or censored, island seasons and man-hours.
- `boundary_seeds.csv`: seeds 1-10 on the cells next to the feasibility boundary (only if a grid point is censored).
