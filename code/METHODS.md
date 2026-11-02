# Nuraghe build ABM: methods

**Question.** How many man-hours did it take to build each of the 7,167 nuraghi in the Nurnet inventory, counting stone transport from the nearest permitted outcrop plus quarrying, dressing and building?

**Framework.** Python with repast4py 1.3.1 (MPI), numba and numpy. Every number below is a parameter in `config.yaml`. Every figure in "Verification" and "Results" is copied from printed output, and the logs are in `cache/logs/`.

---

## 1. What was done, step by step

### Step 1: Inputs (all EPSG:25832)
- **Sites.** `nurnet_nuraghi.shp` has 7,167 points. The model uses `TWR_N` (number of towers, 1–7) and carries `TWR_FILL` (1 = tower count assumed) through to the outputs.
- **Cost raster.** `sardinia_drag_cost_8dir_mu03_25832_int.tif` is 9,080 × 4,808 cells at 30 m, 8 uint8 bands, nodata 0. Band k (1..8 = N, NE, E, SE, S, SW, W, NW) is the cost of dragging a sledge FROM a cell INTO its neighbour in direction k. It is in flat-ground-metre equivalents: `max(0.5, |0.3 + t| / 0.3) × d`, where t is the signed gradient (+ uphill) and d is 30 m or 42.43 m. I confirmed these semantics in `costsurface/build_drag8.py`, `drag_cost_recipe.md` and section 7a of `data-file-README.md`. They were also checked independently against the DEM (Verification b).
- **Lithology.** `sardinia_lithology_25832.shp`, field `STONE`. The allowed quarry stones are exactly `limestone/marble`, `metamorphic`, `basalt` and `granite` (the authors' list). All other classes are excluded: schist, acid volcanic, andesite, tuff, dyke, trachyte, other intrusive and none.

### Step 2: Preprocessing (`preprocess.py`, run once, about 15 s)
1. Read the 8 cost bands into one uint8 array (about 350 MB). A band value of 0 means that move is impossible.
2. Rasterize the allowed outcrop polygons onto the same grid. A cell gets a stone code (1 limestone/marble, 2 metamorphic, 3 basalt, 4 granite) if the polygon covers the cell centre (`rasterize_all_touched: false`). Saved as `cache/outcrop_code.tif`. Printed: limestone/marble 2,327,851 cells, metamorphic 1,004,012, basalt 1,626,812, granite 6,759,551, for 11,718,226 seed cells in total.
3. **One multi-source directional Dijkstra.** Every allowed-outcrop cell is a source at cost 0. Stone moves outcrop → site, so the search moves forward: the edge from cell u to its neighbour in direction k costs band k *at u*. For every cell the search records:
   - the least summed cost from any allowed outcrop (`haul_flatm`, flat-metre equivalents),
   - the outcrop cell where that cheapest path starts (giving the quarry x/y and stone type),
   - the real horizontal length of that path in metres (`haul_m`). This is accumulated during relaxation as +30 m per orthogonal move and +42.43 m per diagonal move.

   Implementation: numba with an indexed binary heap (decrease-key, at most one heap entry per cell), using float32 and int32 arrays. Costs are whole numbers, so the float32 sums are exact. Printed: 27,212,159 cells settled in 9.8 s, **peak RSS 1,687 MB**. The model ranks never load the raster.
4. **Sampling at the sites.** Each site point is mapped to its grid cell. If the cell had no finite cost, the code searched up to 20 cells away (`nodata_snap_radius_cells`) for the nearest cell with a finite cost and flagged the site. **No site fell on nodata.** **6 sites were unreachable (cost inf).** All six are on Isola di San Pietro (Carloforte): NID0243400, NID0243500, NID1064500, NID0247000, NID0248700, NID9220200. The island carries only `acid volcanic` and `none` polygons, and an allowed outcrop can't be reached over land. Under `unreachable_policy: local_min_haul` they are kept with a local quarry at the minimum haul, `quarry_stone = local_unlisted` and `haul_flag = unreachable_local`. Setting `exclude` drops them instead.
5. Output: `cache/sites_haul.csv`, with UID, x, y, TWR_N, haul_flatm, haul_m, quarry_x, quarry_y, quarry_stone, on_outcrop, plus grid row/col, snapping status and haul_flag. 3,637 sites sit on an allowed outcrop (haul 0).

### Step 3: The agent-based model (`model.py`, repast4py)
- **Agents.** `Site` and `Builder` are subclasses of `repast4py.core.Agent` and are added to a `repast4py.context.SharedContext` on each MPI rank. Sites are dealt to ranks round-robin (site i goes to rank i mod n). Each Site owns its Builders.
- **Schedule.** `repast4py.schedule.init_schedule_runner` repeats one event every tick, and **one tick = one working day of `hours_per_day` = 8 h**. After each tick the ranks `allreduce` the number of unfinished sites and the runner stops when it reaches 0. There is a safety stop at `max_days` = 20,000; the longest site took 499 days.
- **Random numbers.** Every site in run i has its own stream, `numpy.random.default_rng([i, uid_int])`, where `uid_int` is the numeric part of UID (e.g. NID9067800 → 9067800). Results therefore do not depend on the rank count or the order in which sites are processed.
- **Per site, at the start of each run:**
  1. Builders: `B = clamp(round(round(50 + 25·(TWR_N−1)) × U(0.9, 1.1)), 50, 200)`.  Observed range 50–200; the 7-tower site averages 195.16.
  2. Stone needed: `1,350 t × TWR_N`. Blocks are drawn from lognormal(median 450 kg, σ 0.6) clipped to [60, 2,400] kg until the cumulative mass reaches the target (the block that crosses the target is included). Printed: 2,513 blocks per tower on average (range 2,340–2,668), mean block 537 kg. There are fewer than Webster's ~3,000 because the mean of a lognormal is above its median.
  3. Crew per block: `ceil(mass / 100 kg)`, i.e. 1 to 24 people.
  4. Trip time (h): `haul_flatm_eff / 0.6 / 3600 + haul_m_eff / 1.4 / 3600 + 0.25`. Here `haul_flatm_eff = max(haul_flatm, 100)` and `haul_m_eff = max(haul_m, 100)`. The first term drags the loaded sledge at 0.6 m/s per flat-metre equivalent (v12 relabel: ASSUMPTION, a sustained mean below the reported 1 m/s peak, Harris 2016, AAM p. 4; press reports ~0.6 m/s; upper bound 1.0 m/s = MR_P10_v12_drag10), the second walks back empty along the same path at 1.4 m/s, and the third is load/unload. A block's transport man-hours are crew × trip time.
  5. Quarry/dress/build pool: `2,500 man-days × 8 h × TWR_N`.
- **Each day (numba kernel `site_day`, event-driven inside the day):**
  1. Blocks whose trip ends at or before the current hour are delivered.
  2. Free builders form crews for waiting blocks in queue order. The queue order is the random draw order. A block is dispatched only if its **full crew** is free. If the next block's crew does not fit, the first later block whose crew fits is taken instead (first-fit). A crew is busy for the whole trip, and trips that run past hour 8 carry over into the next day.
  3. Builders not in a crew work on the pool. **Coupling:** cumulative pool work may not exceed (delivered mass / total mass) × pool. Free builders who hit that cap are idle.
  4. Time jumps to the next crew return or the end of the day, and the loop repeats. When a crew returns mid-day its members are free again in the same day, so short hauls make many trips per day.
  5. The site is complete when every block has been delivered and the pool is finished. The finishing moment is calculated exactly, in fractional hours.
- **Recorded per site per run:**
  - `mh_total = B × elapsed working hours to completion`. The whole workforce counts as committed, idle time included, and only the hours actually worked on the final day are counted.
  - `mh_transport` = Σ crew × trip time.
  - `mh_other` = pool hours.
  - `mh_idle = total − transport − other`.
  - `days` = working days, with the final partial day counted as a whole day.
  - Also `builders`, `n_blocks` and `stone_kg`.
- **Replicates:** 100 runs, where run i uses seed i (1..100).
- **Incremental, resumable output (the authors' request).** After each run, every rank writes its rows to `cache/runs/<signature>/seed_NNNN.rankRRRofNNN.csv`. The file is written to a `.tmp` and renamed, so a crash cannot leave half a file. After a barrier, rank 0 writes `seed_NNNN.done`. Nothing is held in memory across runs. On restart, seeds with a `.done` marker are skipped. The `<signature>` is a hash of the model parameters and the site inputs, so changing `config.yaml` never reuses stale runs. At the end, rank 0 merges the parts from disk into the outputs. `--fresh` ignores existing parts. Tested by deleting seeds 98–100 and rerunning: only those 3 seeds ran, and the merged outputs were byte-identical to before (md5 OK, `cache/logs/resume_test.log`).

### Step 4: Outputs (`output/`, written by `report.py`)
- `nuraghe_manhours_runs.csv.gz`: long format, one row per run × site. Columns: seed, UID, TWR_N, elapsed_h, days, mh_total, mh_transport, mh_other, mh_idle, builders, n_blocks, stone_kg.
- `nuraghe_manhours_summary.csv`: one row per site. UID, NAME, COMUNE, TWR_N, TWR_FILL, x, y, haul_flatm, haul_m, quarry_stone, quarry_x, quarry_y, on_outcrop, haul_flag; mean/min/max/sd of total MH; mean/min/max transport MH; other and idle MH; mean/min/max days; mean builders and blocks.
- `nuraghe_manhours.shp` (+ .prj, .cpg = UTF-8): the summary as points. Field names: MH_MEAN, MH_MIN, MH_MAX, MH_SD, TR_MEAN, TR_MIN, TR_MAX, OTH_MH, IDLE_MEAN, DAY_MEAN, DAY_MIN, DAY_MAX, BLD_MEAN, BLK_MEAN, HAUL_FM, HAUL_M, Q_STONE, Q_X, Q_Y, ON_OUTCR, HAUL_FLAG, TWR_N, TWR_FILL, UID, NAME, COMUNE.
- `quarry_sources.shp`: the 6,150 distinct quarry cells used, each with STONE, N_SITES (sites served) and MH_SUM.

## 2. Parameters and sources

| Parameter | Value | Source / reasoning |
|---|---|---|
| allowed_stones | limestone/marble, metamorphic, basalt, granite | The authors |
| cost raster μ | 0.3 | drag_cost_recipe.md (sledge friction; an assumption) |
| hours_per_day | 8 | assumption (a standard working day; Webster counts in man-days) |
| builders | 50 + 25·(TWR_N−1), ×U(0.9,1.1), clamp [50, 200] | The authors' spec |
| tonnes_per_tower | 1,350 | Webster 1991, *Antiquity* 65(249): 840–856: ~3,000 blocks/tower × ~450 kg |
| block_median_kg / sigma / clip | 450 / 0.6 / [60, 2,400] | 0.19 m³ × 2,386 kg/m³ ≈ 450 kg (Webster); σ and clip are the modellers' assumptions (roughly Webster's 0.06–1 m³ block range) |
| pull_kg_per_person | 100 | UCL 2016 Stonehenge sledge experiment: ~10 people per ~1 t |
| drag_speed_ms | 0.6 | same experiment |
| return_walk_ms | 1.4 | normal walking speed |
| load_unload_h | 0.25 | the modellers' assumption |
| min_haul_flatm | 100 | quarry face to the site when the site sits on the outcrop; Webster's local hauls are ≤ 200 m |
| other_mandays_per_tower | 2,500 | Webster Table 1: ~3,600 man-days per tower, minus ~1,100 for transport |
| seeds | 1..100 | The authors' spec |

## 3. Verification

**(a) Dijkstra unit tests** (`tests/test_dijkstra.py`, `cache/logs/verify_a.log`):
- 1-D ramp, where uphill moves cost 50 and downhill moves cost 15: west outcrop → east end = 150 (expect 150); east outcrop → west end = 45 (expect 45). A Dijkstra running edges the wrong way round would swap these.
- Two outcrops on the same ramp: the middle cell costs 30 from the east outcrop (expect 30, from col 4), not 100 from the west.
- Diagonal detour around a nodata cell: cost 102 (expect 102), path 102.43 m (expect 102.43), and the nodata cell is unreachable.
- Random 40×35 grid with 3 sources and 10% nodata: all 1,400 finite cells equal an independent plain-Python heapq Dijkstra, and every cell's cost equals a single-source run from its reported origin. **ALL DIJKSTRA TESTS PASSED.**

**(b) Spot-check on 3 real sites** (`tests/verify_hauls.py`, `cache/logs/verify_b.log`). A separate lazy-deletion heapq Dijkstra was run from the reported quarry cell on a raster window padded by 15 km:

| Site | haul_flatm (multi-source) | single-source from quarry | path length vs haul_m | DEM recomputation |
|---|---|---|---|---|
| NID1830000 (basalt) | 481 | 481 MATCH | 499.7 m vs 499.7 m | 483.1 (−0.43%) |
| NID0459600 (limestone/marble) | 1,826 | 1,826 MATCH | 2,004.3 m vs 2,004.3 m | 1,828.4 (−0.13%) |
| NID1548400 (limestone/marble) | 5,678 | 5,678 MATCH | 6,015.8 m vs 6,015.8 m | 5,687.9 (−0.17%) |

The DEM column recomputes the cost of the same path from `sardinia_dem_GLO30_25832.tif` with the recipe formula. Agreement within 0.5% is the expected rounding error of the integer raster. It confirms the band direction: uphill moves cost more and the floor applies downhill. All three quarry cells carry the allowed stone code. **SPOT CHECK PASSED.**

**(c) Webster sanity check** (`tests/verify_webster.py`, `cache/logs/verify_c.log`). The test site is NID1501300 (Silius): 1 tower, 200 m haul (167 flat-m) from metamorphic rock, 0.367 h trip, 2,427–2,601 blocks, 50–55 builders.
- Total: **25,415 man-hours = 3,177 man-days** (range 3,174–3,180) against Webster's ~3,600 man-days = 28,800 man-hours, a ratio of 0.88.
- Transport: **5,415 man-hours = 677 man-days** (range 674–680) against Webster's ~1,100.
- Other: 2,500 man-days. Idle: 0.0. Days to completion: 62.2 (58–64).
- Across all 215 single-tower sites with 150–250 m hauls: median total 3,193 man-days, median transport 693 man-days.
- In range: **WEBSTER CHECK PASSED.** Transport is lower than Webster's because the UCL sledge rate (0.6 m/s, 10 people per t; both ASSUMPTION since v12: press figures, not in the primary Harris 2016) is faster than Erasmus's 1,200 kg per man-day over 200 m.

**(d) Reproducibility** (`tests/test_reproducibility.py --full`, `cache/logs/verify_d.log`):
- 3 sites × seeds 1–3: `-n 1` vs `-n 4` identical at full precision: True.
- `-n 4` rerun identical: True.
- Different seeds give different results: True.
- All sites × seeds 1–5: `-n 8` vs `-n 3` identical: True.
- Seeds 1–5 rerun vs `output/nuraghe_manhours_runs.csv.gz`: identical.
- **REPRODUCIBILITY PASSED.**

**(e) Code review against the spec.** Every item is implemented as specified except the points below.
1. **Random order.** The block queue is the random draw order, fixed for the run, and is not reshuffled every day. The blocks are i.i.d., so the draw order is already a random order. With first-fit, skipped heavy blocks keep their place in the queue.
2. **Crew reuse within a day.** The spec says each day builders form crews. I let crews re-form whenever a crew returns, within the same day. Without this, a 100 m haul (0.32 h trip) would make one trip per crew per day and the site would sit idle for over 90% of the day.
3. **First-fit.** If a waiting block's full crew isn't free, the next block that does fit is dragged. A block is never dragged with a partial crew.
4. **Return walk.** The return walk uses `haul_m_eff` (the 100 m minimum applies to both legs), following the spec's definition of `haul_m_eff`.
5. **Final day.** Man-hours count to the completion hour on the last day, and `days` counts that last day as a whole day.
6. **Idle column.** `mh_other` is the pool total. Idle time is a separate column (`mh_idle`) and is included in `mh_total`.
7. **Builder state.** Builder agents are real repast4py agents, but their state (the hour each builder is next free) lives in the Site's numpy array, which the numba kernel updates. Running the scheduling in Python agent by agent would be far slower. No simplification was needed for speed: 100 runs take 1 min 50 s on 8 ranks.
8. **Unreachable sites.** The 6 San Pietro sites use a local, non-listed stone at 100 m. This is configurable and flagged.
9. **Overlapping polygons.** If allowed polygons overlap, the one drawn last sets the stone code. A cell is a source either way.

## 4. Results (100 runs, `cache/logs/model_run.log`)
- **Island total man-hours** (sum over sites, per run): mean **286,466,319** (= 35,808,290 man-days), min 286,460,203, max 286,472,953, sd 2,601.
- **Share of total:** transport 35.2%, quarry/build 64.8%, idle 0.0%.
- **Median per-site man-hours by TWR_N** (median of per-site means):

  | TWR_N | Sites | Median man-hours | Median transport man-hours | Median days |
  |---|---|---|---|---|
  | 1 | 5,902 | 24,666 | 4,666 | 61 |
  | 2 | 788 | 49,331 | 9,331 | 84 |
  | 3 | 230 | 73,995 | 13,995 | 94 |
  | 4 | 128 | 98,658 | 18,658 | 100 |
  | 5 | 111 | 129,942 | 29,942 | 109 |
  | 6 | 7 | 179,847 | 59,847 | 130 |
  | 7 | 1 | 401,794 | 261,794 | 258 |

- **Hauls (per site).** haul_m: p25 0, p50 0, p75 781, p90 2,329, p99 6,480, mean 697, max 11,656 m. 3,637 sites are on an allowed outcrop, 5,610 are within 1 km, and 154 are beyond 5 km.
- **Quarries.** 6,150 distinct quarry cells. Sites per stone: limestone/marble 2,840, basalt 2,024, granite 1,812, metamorphic 485, local_unlisted 6.

**What drives the variation.**
- Idle time is 0 in every site-run. First-fit crew formation and crews as small as one person leave almost no free builders, so pool work never hits the delivery cap.
- As a result, total man-hours ≈ transport + pool, and the builder count changes only days to completion, not man-hours.
- Run-to-run variation is tiny (median per-site coefficient of variation 0.03%). Almost all spread between sites comes from tower count and haul distance.

## 5. Limitations
- **Modern lithology map.** It is a present-day geological map, so small or quarried-out outcrops may be missing or added. An outcrop that covers no 30 m cell centre is not seeded.
- **Nearest permitted outcrop ≠ the real quarry.** The model picks the cheapest-to-drag allowed outcrop. Real builders may have used a specific stone, an older quarry, or rubble from the site itself. Half the sites sit on an outcrop and get the 100 m minimum haul.
- **The cost surface** comes from a surface model (trees, buildings) with an assumed μ = 0.3, rounded to whole flat-metres. It has no ramps, tracks, rivers or levering on steep slopes.
- **Constant labour rates.** Pull per person, speeds, load time and the 2,500 man-days/tower for quarrying and building are fixed. There is no fatigue, seasonality, food supply or skill difference. Webster's figures are themselves estimates.
- **Tower count.** `TWR_N` is assumed for 3,764 sites (`TWR_FILL = 1`). Mass scales linearly with towers, with no allowance for bastions, walls or villages.
- **No chronology.** Every site is built independently with its own workforce, with no shared labour, competition for quarries, or phasing. The island total is a sum of labour, not a duration.

## 6. How to run it locally
1. Install OpenMPI (e.g. `brew install open-mpi`, or `sudo apt install libopenmpi-dev openmpi-bin`).
2. Install the Python packages: `CC=mpicxx CXX=mpicxx pip install repast4py`, then `pip install -r requirements.txt`.
3. Edit `data_dir` in `config.yaml` to point at your data folder.
4. Run:
   ```
   python preprocess.py config.yaml          # ~15 s, ~1.7 GB RAM, writes cache/
   mpirun -n 4 python model.py config.yaml   # 100 runs; resumable; writes output/
   python tests/test_dijkstra.py             # (a)
   python tests/verify_hauls.py config.yaml  # (b)
   python tests/verify_webster.py config.yaml   # (c)
   python tests/test_reproducibility.py config.yaml --full   # (d)
   ```
   Useful options: `--seeds 1-10`, `--sites UID1,UID2`, `--first-n 200`, `--fresh`, `--out DIR`.

---

## 7. Cooperation scenarios (added 28 Oct 2026, at the authors' request)

Specified by the authors: scenarios with more cooperation, with none, and with a mixture of cooperating and non-cooperating builders. Cooperation is an attribute of each Builder agent. All numbers are in the `scenarios:` block of `config.yaml`.

### 7.1 Definitions
| Scenario | Rule |
|---|---|
| `none` | p_coop = 0: no builder cooperates |
| `low` | p_coop = 0.25 |
| `mixed` | p_coop = 0.5 |
| `mostly` | p_coop = 0.75 |
| `full` | p_coop = 1.0: identical to the baseline in sections 1–4 |
| `high` | p_coop = 1.0 plus inter-site help |
| `patchwork` | per SITE: with probability 0.5 the whole site cooperates (p = 1), otherwise none of it does (p = 0) |

Run with `mpirun -n 8 python model.py config.yaml --scenario NAME` or `--scenario all`. With no `--scenario` you get the baseline.

### 7.2 Mechanics
1. **Draw order.** Each site in each run still uses `default_rng([seed, uid_int])`, in this order:
   - the builder factor,
   - the block masses (unchanged, so every scenario has the same blocks as the baseline),
   - for `patchwork` only, one site-level draw,
   - one uniform draw per builder: the builder is a cooperator if the draw is < p_coop.
2. **Households.** Builders are packed consecutively into households of `household_size` = 5; the last household can be smaller.
3. **Cooperators** pool freely into crews of any size, exactly as in the baseline.
4. **Non-cooperators** work only inside their household. The non-cooperating members of a household form one fixed crew of size n. That crew:
   - can drag only blocks with mass ≤ n × 100 kg,
   - always drags with all n members (transport man-hours = n × trip time),
   - never joins other groups and never lends members,
   - spends its free time on the quarry/build pool, under the existing delivered-stone cap.

   It is idle only when the cap binds and no block it can move is waiting.
5. **Heavy blocks are split at the quarry, before the run.** The largest available crew is the larger of the site's cooperator pool (n_coop, since cooperators pool into crews of any size) and its largest non-cooperating household (max hh_n, since a household drags as one fixed crew): c_max = max(n_coop, max hh_n). A block needing more than c_max is cut into the fewest equal pieces k whose crew fits. The pieces take the block's place in the queue.
   - **30 Oct (b) fix, BUGFIX_REPORT B22 (the authors' N1).** Before, c_max was n_coop whenever n_coop > 0, so a bigger household was ignored and some blocks were cut into more pieces than needed. This can change a site-run only when 0 < n_coop < max hh_n ≤ household_size (5), which with ≥ 50 builders happens only in `low` (982 of 716,700 site-runs in 100 seeds, all TWR 1; measured on seeds 1-10: 82 site-runs, island MH −0.007%, site MH up to −27% and −77 days at single sites; 100-seed rerun: island MH −0.0095%, site MH up to −56%, −118 days); `mixed` and `mostly` never have fewer than 5 cooperators in any delivered run and are unchanged, as are `none` (n_coop = 0), `full`, `high`, `patchwork` and every literature run (p_coop = 1 at every site).
   - **n_splits** counts the cuts (k − 1 per block).
   - Each cut adds `split_cost_mh` = 1.0 man-hour to the pool.
   - **Lifting is per piece (30 Oct fix, BUGFIX_REPORT B14).** Where lifting is charged per block (S4a lever, S4c internal stair), every piece is lifted separately at the full per-block rate (specified by the authors: the conservative upper end). `n_blocks` reports the pieces; `n_splits` and the cut cost are separate. With full cooperation (every literature run) no block splits, so this changes nothing there.
6. **Scheduling.** At every event the earliest waiting block (in queue order) that any free crew can move is assigned:
   - first choice: the first free household (in household order) big enough for it,
   - otherwise: free cooperators.

   This keeps cooperators for the heavy blocks. It is first-fit and deterministic. With no households it is exactly the baseline kernel.
7. **Inter-site help (`high`).**
   - When a site finishes, all cooperators working there (its own and any helpers) walk to the nearest unfinished site within `help_radius_m` = 10,000 m, measured in a straight line (ties broken by site index).
   - The walk costs n × distance / 1.4 m/s in man-hours, charged to the helped site. The helpers join its cooperator pool at the start of the next working day.
   - They keep re-targeting each time the site they are at finishes. When no unfinished site is within 10 km of their current site they go home.
   - A site's man-hours = own builders × hours until it finishes + helper hours while they are there + walk. `mh_help` reports the helper part, walk included.
8. **Parallelism.**
   - Uncoupled scenarios: sites are dealt round-robin across ranks, as before.
   - `high`: sites interact, and at a 10 km radius the island is effectively one connected cluster. Spatial partitioning with halos would not separate it, so each rank simulates the whole island for its own subset of seeds, on `MPI.COMM_SELF`. This is option (b) of the brief, parallelised over seeds.
   - Each whole-island model needs about 2 GB. `coupled_max_ranks: 2` caps how many ranks take seeds; the peak was 4,722 MB for the container. A first attempt with 3 ranks was killed by the 8 GB memory cap.
   - In all scenarios, results do not depend on the rank count.
9. **Outputs.**
   - `output/scenarios/<name>/`: `nuraghe_manhours_runs.csv.gz` (new columns n_coop, n_splits, mh_help, n_helpers), `nuraghe_manhours_summary.csv` (new n_split_mean, help_mean, coop_mean), `nuraghe_manhours.shp` (new SPL_MEAN, HLP_MEAN, COOP_MEAN).
   - `quarry_sources.shp` is not repeated, because quarries do not depend on the scenario.
   - `output/scenarios/scenario_comparison.csv`.
   - `output/scenarios/nuraghe_manhours_scenarios.shp`: one point per site with MH_NONE, MH_LOW, MH_MIX, MH_MOST, MH_FULL, MH_HIGH, MH_PATCH and DAY_* for each.
   - Part files go to `cache/runs/<scenario>/<signature>/` and are resumable, as before.

### 7.3 Verification (`tests/verify_scenarios.py`, `cache/logs/verify_scenarios.log`)
1. **`full` == baseline.** The full scenario's part files were compared with the original baseline's (716,700 rows: elapsed_h, days, mh_total, mh_transport, mh_other, mh_idle, builders, n_blocks, stone_kg). They are identical at full precision: True. mh_total in the runs file is identical for all 100 seeds: True.
2. **Split hand-check (`none`, seed 1).** The RNG was replayed by hand in plain Python:
   - NID9067800: B = 50, so the largest household is 5 (500 kg). 2,596 blocks drawn, 1,081 heavier than 500 kg. Pieces per block {1: 1515, 2: 876, 3: 169, 4: 29, 5: 7}. Hand count 1,329 splits / 3,925 pieces; model 1,329 / 3,925: MATCH.
   - NID0168700: B = 71. 5,039 blocks, 2,152 heavier than 500 kg. Hand count 2,734 splits / 7,773 pieces; model 2,734 / 7,773: MATCH.
3. **Rank independence.** 300 spatially clustered sites (within 11.4 km of the island median), seeds 1–8, `-n 1` vs `-n 8`:
   - `high`: identical, True, with 6,064,853 help man-hours inside the cluster. Under `-n 8` the cap of 2 makes 2 ranks do the work, but the seeds land on different ranks than with `-n 1`.
   - `patchwork`: identical, True, with 1,218 of 2,400 site-runs cooperating.
4. **Monotone in p_coop? No.** Island mean man-hours: none (p = 0) 330,215,034; low (0.25) 384,979,110; mixed (0.5) 294,459,597; mostly (0.75) 286,873,442; full (1.0) 286,466,319. The curve is monotone only for p ≥ 0.25: `low` is the most expensive scenario. Section 7.5 explains why.
5. **Code review against the brief.** Deviations and interpretations:
   1. n_splits counts cuts (k − 1), not split blocks.
   2. Helpers arrive at the start of the next working day; their walk is charged but does not take up working time on the day they leave.
   3. When a block could go to several free households, it goes to the first in household order, not the smallest that fits.
   4. The split rule uses "crew > largest available crew". This equals the brief's "crew > total cooperators" whenever cooperators exist; when there are none, the largest household is the limit.
   5. Summary CSV columns are lowercase (n_split_mean, help_mean) to match the existing columns; the shapefile uses SPL_MEAN and HLP_MEAN as asked, plus COOP_MEAN.
   6. `high` runs seed-parallel on at most 2 ranks for memory reasons.
   7. The files in `output/` (baseline) were written by the pre-scenario code. They equal `full` in every column, and a baseline rerun under the new code adds the new columns.

### 7.4 Results (100 seeds each; copied from `cache/logs/scenario_comparison.log`)

| | none | low | mixed | mostly | full | high | patchwork |
|---|---|---|---|---|---|---|---|
| Island MH mean | 330,215,034 | 384,979,110 | 294,459,597 | 286,873,442 | 286,466,319 | 292,578,195 | 308,295,204 |
| Island MH min | 330,138,585 | 382,369,199 | 293,550,946 | 286,778,393 | 286,460,203 | 290,617,155 | 307,261,456 |
| Island MH max | 330,333,321 | 388,618,392 | 295,220,170 | 286,998,042 | 286,472,953 | 297,050,930 | 309,481,842 |
| % vs full | +15.27 | +34.39 | +2.79 | +0.14 | 0 | +2.13 | +7.62 |
| Transport share | 39.9% | 26.8% | 34.3% | 35.2% | 35.2% | 34.4% | 37.7% |
| Idle share | 0.0% | 24.7% | 2.6% | 0.1% | 0.0% | 1.2% | 0.0% |
| Help share | 0 | 0 | 0 | 0 | 0 | 19.9% | 0 |
| Median MH, 1 tower | 27,499 | 24,991 | 24,692 | 24,673 | 24,666 | 24,683 | 26,235 |
| Median MH, 2 towers | 54,914 | 49,963 | 49,359 | 49,341 | 49,331 | 49,903 | 52,442 |
| Median MH, 3 towers | 82,423 | 74,466 | 74,023 | 74,007 | 73,995 | 75,162 | 78,714 |
| Median days, 1 tower | 67.69 | 61.67 | 60.95 | 60.94 | 60.94 | 60.73 | 64.53 |
| Median days, 2 towers | 92.79 | 84.45 | 83.70 | 83.69 | 83.69 | 71.79 | 88.41 |
| Median days, 3 towers | 104.42 | 94.28 | 93.83 | 93.83 | 93.83 | 73.92 | 99.45 |
| Mean splits per site | 1,792.7 | 145.6 | 3.2 | 0.0001 | 0 | 0 | 895.9 |
| % site-runs with ≥ 1 split | 100 | 93.4 | 23.3 | 0.0008 | 0 | 0 | 50.0 |
| Max single-site days | 636 | 2,266 | 891 | 527 | 499 | 324 | 628 |

Runtimes on 8 ranks: none 159 s, low 216 s, mixed 122 s, mostly 122 s, full 112 s, patchwork 166 s. `high` took 542 s on 2 ranks.

### 7.5 Why the scenarios differ
- **`none` (+15%): over-manned trips.** Every block over 500 kg is cut so a 5-person household can move it (1,793 cuts per site). Every household drags with all 5 members, even a 60 kg piece that one person could pull. The result is more trips and more people per trip, so transport rises to 39.9% of the total. Nobody is ever idle.
- **`low` (+34%, the worst): a bottleneck of too few cooperators.** With about 13–15 cooperators (median 12.9, mean 14.6), only blocks needing more than that many people get split. Blocks of roughly 400–1,300 kg are too heavy for the partly non-cooperating households (1–4 members, 100–400 kg) but can only be moved by that small cooperator pool. The households soon run out of light blocks they can move. They then hit the delivered-stone cap on the pool and stand idle (24.7% of all hours), and one site takes 2,266 days. A little cooperation is worse than none, because under `none` everything is cut down to household size.
- **`mixed` and `mostly`: the bottleneck fades.** With about 26–29 cooperators (`mixed`: median 25.7, mean 29.2) or more, the heavy blocks clear quickly, idle drops to 2.6% and then 0.1%, and costs converge on `full`.
- **`patchwork` (+7.6%): roughly the average of `none` and `full`,** since half the sites behave like each.
- **`high` (+2.1% man-hours, much faster): help buys speed at a small labour cost.** The extra cost is the walking plus the idle time of helpers at sites where the delivered-stone cap already binds (idle 1.2%). In return the median 3-tower site finishes in 74 days instead of 94, and the slowest site in 324 days instead of 499.

The labour sum barely changes under `high` because, as in the baseline, man-hours are almost entirely transport plus the fixed pool. What cooperation mainly changes is how efficiently the transport crews are sized.

---

## 8. Literature-based chaîne opératoire / logistics scenarios (added 28 Oct 2026)

The scenarios come from `literature/SCENARIOS_PLAN.md`, using the two reviews in `literature/`:
- `general_energetics_logistics.md`, cited below as **GEN**,
- `nuraghe_specific.md`, cited below as **NUR**.

Line numbers refer to those files. Every number sits in `config.yaml → lit_scenarios` with its source line. A value marked **FREE** has no empirical basis in either review: it is a stated assumption, and its effect is the point of the scenario.

Run with `mpirun -n 8 python model.py config.yaml --lit all` (or `--lit NAME`). Outputs go to `output/scenarios_lit/`. All scenarios use full cooperation, with 100 seeds (1..100).

### 8.1 The stage-explicit baseline (`webster`)
- The old single pool of 2,500 man-days per tower is split into Webster's 1991 Table 1 stages for a single tower (NUR 181): quarrying 500, dressing 1,300 and building 700 man-days. Transport (1,100 man-days in Webster) stays simulated by the ABM.
- The building stage is split again: half walling/setting (`MH_BLD`) and half lifting (`MH_LIFT`). The 50% lifting share is **FREE**; it comes from the plan.
- The model reports a stage breakdown per site: `MH_QUA`, `MH_TRA`, `MH_DRE`, `MH_BLD` and `MH_LIFT`.
- All stages still form one pool, coupled to delivered stone exactly as before. Stone volume = mass / 2,386 kg/m³ (NUR 155), which gives 565.8 m³ per tower.
- Webster's totals are kept as they are. Each scenario replaces one stage with a rate from the literature.

### 8.2 Scenario definitions and sources

| Scenario | Change from `webster` | Values and source |
|---|---|---|
| S1a_scree | quarrying = 2 ph/m³ (collecting fallen and field stone) | GEN 48 (Boswinkel 2021 Table 7.2; Turner 2020: 88); field clearance as stone source in Sardinia, NUR 20–21 |
| S1b_joints_low / _high | quarrying = 11 / 17.5 ph/m³ (breaking along joints with wedge and lever) | GEN 45, 200; Duos Nuraghes knoll quarry, NUR 27–31 |
| S2a_unworked | dressing = 0 (cyclopean blocks set as quarried) | GEN 57; NUR 39, 58 |
| S2b_fine | complex sites (TWR_N ≥ 2): extra cost = facing volume × (131.5 − 40.85) ph/m³ (v11 citation fix: these are Boswinkel's TOTAL all-stage costs per m³ of conglomerate facades and cyclopean walls, Boswinkel 2021: 144, Table 8.3, NOT dressing rates; the difference is the extra total cost of facade masonry; Boswinkel's dressing rates proper, 57–62 ph/m³, pp. 120–121, Table 7.8, are variant C3_dress) | GEN 57, 199 (Table 8.3 facade and cyclopean midpoints); isodomic masonry, NUR 61. Facing = outer face of a 15 m truncated cone (475.2 m²) × 0.5 m × TWR_N; the 0.5 m is **FREE** |
| S3a / S3b / S3c / S3d | μ = 0.1 tallowed rails / 0.05 greased rails / 0.38 dry ground / 0.5 rough ground. Cost raster rebuilt from the DEM per μ; crew = ceil(m·μ / 30 kg-force) | GEN 64–65, 201; 30 kgf = 300 N per person, GEN 202 (30 / 0.3 = 100 kg per person in the baseline). v11 note: 300 N is a PEAK, short-burst draught effort (Cotterell & Kamminga 1990: 219, de Haan 2009, via Boswinkel 2021: 47 n. 25, 52, 111); a sustained effort is ~125 N (Boswinkel 2021: 52): sensitivity MR_P10_v11_pull125 |
| S3e_oxen | an ox team per block: 2 men (drover + helper), with yokes as needed at 520 N per ox in v10 (v11: 515 N, see section 12) and 95/80/63% efficiency for 1/2/3 pairs, at 0.75 m/s. Oxen-hours are reported separately (not man-hours). Surface μ stays 0.3 | GEN 69, 203 (v11 citation fix: Boswinkel 2021: 52 prints 491–549 N, but its footnote 37 computes 350 × 14% × 9.81 ≈ 481 N and 400 × 14% × 9.81 ≈ 549 N; 491 is a misprint, midpoint 515 N); LBA only, since cattle may be rare before the LBA (NUR 54). Return speed 0.75 and 63% for more than 3 pairs are **FREE** |
| S4a_lever | lifting = Σ blocks × courses climbed × 0.37 ph (blocks = lifted pieces after any split, 30 Oct) | GEN 77, 204. Geometry **FREE**: 15 m tall, 0.9 m courses (17), truncated cone 12 → 8 m; mean 6.745 courses climbed per block |
| S4b_ramp | lifting = single-sided earth ramp to 15 m at 20%, 3 m wide (1,687.5 m³): (dig 4.2 ph/m³ + compaction ρ/1,000 kg/ph + carrying 50 kg loads × 0.000444 h/m × 50 m) × 2 (build + remove) = 21,973 ph per tower | GEN 68, 78, 205. Width, earth density 1,600 kg/m³ and carrying distance 50 m are **FREE** |
| S4c_internal_stair | lifting = blocks above the ground course × 0.37 × (1 m / 0.9 m) (blocks = lifted pieces after any split, 30 Oct) | Laner's internal stair, NUR 79–81. The "last metre only" rule is **FREE** |
| S5a_onsite | haul = 100 m (the minimum) everywhere | NUR 27, 45–46, 195–196 |
| S5b_any_buildstone | quarries may be any BUILDSTONE class (all 11 non-"none" classes) | shows what the authors' four-stone rule costs |
| S5c_complex_far | TWR_N ≥ 3: the cheapest allowed outcrop cell ≥ 3 km away (straight line, measured cell centre to site) | S'Urachi about 3 km (NUR 49, 198); "some km" (NUR 50, 199). The TWR_N ≥ 3 mapping is **FREE** |
| S6_density | block volume held, so mass × ρ/2,386 (basalt 2,950, granite 2,650, limestone/marble 2,600, metamorphic 2,750 kg/m³). Quarrying and dressing × hardness: basalt and granite 2, others 1 | Turner's critique of Webster (GEN 136, 212). Densities and multipliers are **FREE** (standard values; GEN 212 gives basalt ~2.9–3.0 and limestone ~2.5) |
| S7_webster_classes | Webster's class totals in place of "× TWR_N": single 1,350 t, 500/1,300/700 md; multi-tower 3,100 t, 1,200/3,000/1,600; bastioned 6,700 t, 2,500/6,400/3,500 | NUR 156–158, 181–183. The mapping TWR_N 1 / 2–3 / ≥ 4 is **FREE** |
| S8_learning | tower i (counting from 0) costs 0.85^i in quarrying, dressing and building | **FREE** (GEN 91: no archaeological learning rate) |
| LOW | S1a + S2a + S3a + S4c + S5b (any buildstone at μ 0.1) | see deviation 6 |
| HIGH | S1b_high + S2b + S3d + S4b + S6 | |

**Duration.** Each site's mean man-days is divided by workforce × days per year:
- Workforces: a household of 6 (NUR 205), Trump's 15 (NUR 130, 206), and a canton of 500 (GEN 26).
- Calendars: 40 or 90 days (NUR 185), or 255 days (GEN 36, 206: the midpoint of 220–290).
- The "community" row uses the ABM's own 50–200 builders and simulated working days.

**Threshold.** The percentage of sites whose mean exceeds 30,000 ph (GEN 26, 207).

### 8.3 Mechanics
1. **Cost rasters per μ.** `tools/build_cost_mu.py` repeats the float32 arithmetic of `costsurface/build_drag8.py` and rounds with `np.rint`, which is the rule behind the delivered int raster.
   - The float raster is never written: each band is built in memory, rounded, written and freed.
   - Output is uint8 when the largest possible value fits in 255, otherwise uint16: μ 0.05 needs up to 891, μ 0.1 up to 467.
   - Builds ran one at a time, with a peak RSS of 843–868 MB each.
2. **Hauls per scenario.** `preprocess.py --cost-raster / --stones / --tag` reruns the multi-source Dijkstra and writes `cache/haul/sites_haul_<tag>.csv`.
   - A rebuild at the baseline settings reproduces `cache/sites_haul.csv` byte for byte.
   - With BUILDSTONE quarries, no site is unreachable: San Pietro's acid volcanic rock becomes a source.
3. **S5c** (`tools/haul_far.py`). A reverse directional Dijkstra runs from each of the 477 complex sites and stops at the first allowed outcrop cell ≥ 3 km away.
   - The window grows until the answer provably doesn't depend on it, i.e. no open window edge is settled first.
   - Result: straight-line distance median 3,008 m; haul_m median 3,100 m (max 9,139); haul_flatm median 2,834 against a baseline median of 0 for these sites.
   - 3 forward single-source checks: all MATCH.
4. **Transport technology.**
   - S3 changes the crew per block (`pull = 30/μ` kg per person) and the drag cost. A lower μ makes slopes relatively costlier, so haul_flatm rises (mean 687 at μ 0.3, 778 at μ 0.1, 960 at μ 0.05), while crews shrink by μ/0.3.
   - S3e gives every block a 2-man crew, with the number of yokes needed to overcome m·g·0.3.
5. **S6 density** scales the block median, the clip limits and the site's total mass by ρ/2,386, using the stone type of the site's quarry.
6. **Stage costs** (`lit.py: stage_hours`) are deterministic per site, except lifting under S4a and S4c, which uses the site's simulated block count. They feed the ABM pool. Transport, days and idle time come from the ABM as before.

### 8.4 Verification (`tests/verify_lit.py`, `cache/logs/verify_lit.log`)
1. **`webster` == `full`.** All 716,700 site-runs; all 15 shared columns identical at full precision: True. Max |mh_total difference| 0 h. Island totals identical for all 100 seeds: True. Quarry + dress + build + lift == pool in every row: True. One 1-tower site-run splits as quarry 4,000 / dress 10,400 / build 2,800 / lift 2,800 = 20,000 ph.
2. **Raster rebuild.** μ = 0.3 rebuild against the delivered `sardinia_drag_cost_8dir_mu03_25832_int.tif`: 0 mismatching cells of 349,253,120 (8 bands): IDENTICAL.
3. **Ramp.** Boswinkel's 6 m and 9 m ramp volumes (354 and 796 m³) imply a width of 3.93 m at 20%. A 3 m ramp costs 879 ph at our 3.0 m width (below his range) and 1,152 ph at his implied width. Boswinkel gives 971–1,208 ph, so the formula is IN RANGE. Tower ramp to 15 m: 1,687.5 m³, 21,973 ph per tower.
4. **Calibration.** NID1501300 (1 tower, 200 m haul): 3,177 man-days, against Webster's 3,600 (ratio 0.88). Stages: quarry 500, transport 677, dressing 1,300, walling 350, lifting 350.
5. **Rank independence.** 300 clustered sites × seeds 1–4, `-n 1` vs `-n 8`, all columns at full precision: S3e_oxen True, S6_density True, HIGH True.
- **Result: LIT VERIFICATION PASSED.** S5c's own checks are in `cache/logs/lit_haul_far.log`.

### 8.5 Deviations from the plan (fixed after reading the sources)
1. **Stage man-days.** The plan's 504 / 1,296 / 684 (shares × 3,600) sum to 2,484. Webster's Table 1 values 500 / 1,300 / 700 (NUR 181) sum to the model's 2,500 and were used, which keeps `webster` == `full` exactly.
2. **Dressing rate.** Webster's 0.40 m³/man-day would give 1,415 man-days for 565.8 m³, but Table 1 has 1,300 (NUR 156, 178, 181). The Table 1 totals are kept as the baseline. Per-m³ rates are used only for the replacement stages.
3. **S2b.** The 96–167 ph/m³ is Boswinkel's *all-stage* cost of facade masonry (GEN 57, 199), not a dressing rate. Only the increment over cyclopean masonry is added (131.5 − 40.85 = 90.65 ph/m³, both Table 8.3 midpoints), to avoid double counting quarrying, transport and setting.
4. **Calendar.** The midpoint of 220–290 days is 255, not 250.
5. **Oxen.** GEN 203 also gives 95% efficiency for a single pair, which the plan omitted, and it is used. More than 3 pairs keep 63% (Boswinkel caps the loss at 36%; **FREE**). Teams return at ox pace (**FREE**).
6. **LOW used S4c instead of S4a.** Levering costs 6,272 ph per tower (lever = 0.37 × 6.745 courses × ~2,513 blocks), more than Webster's 2,800 ph lifting share. A lower bound should take the cheapest lifting option, so LOW uses the internal stair (S4c, 947 ph per tower).
7. **S7.** Webster's tonnages are used directly (3,100 and 6,700 t; NUR 157–158), rather than scaling 1,350 t by the block ratio (which would give 3,150 and 6,750 t).
8. **Ramp check.** The plan's "3 m ramp ≈ 1,000 ph" is matched only at Boswinkel's implied 3.93 m width. Our tower ramp keeps the plan's 3 m width.
9. **Household duration.** The "household of 6" is the whole household (NUR 205 gives 5–6 people, of whom about 1 in 5 is an adult man, NUR 207). The household row is therefore an optimistic (short) duration.
10. **S5c distance.** The 3 km is measured from the site point to the quarry cell centre, so the nearest accepted source is 2,985 m away.
11. **Not modelled.** Hauling blocks up the S4b ramp. Carrying stone up the internal stair in S4c (only the last metre is levered). Oxen availability, fodder and the ploughing season (GEN 88).

### 8.6 Results (100 seeds each; copied from `cache/logs/lit_scenarios_run.log` = `output/scenarios_lit/scenario_comparison_lit.csv`)

Island totals are in man-hours. Stage shares (quarry, transport, dress, build, lift) are % of all man-hours; idle was 0.0% in every scenario. Median MH is the median of per-site means.

| Scenario | Island mean | Island min | Island max | % vs webster | Quarry | Transport | Dress | Build | Lift | Median MH 1 tower | Median MH 2 towers | Median MH 3 towers | % sites > 30k | Max days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| webster | 286,466,319 | 286,460,203 | 286,472,953 | +0.00 | 13.0 | 35.2 | 33.7 | 9.1 | 9.1 | 24,666 | 49,331 | 73,995 | 40.2 | 499 |
| S1a_scree | 259,836,102 | 259,829,986 | 259,842,736 | −9.30 | 4.0 | 38.8 | 37.2 | 10.0 | 10.0 | 21,798 | 43,594 | 65,389 | 36.4 | 485 |
| S1b_joints_low | 307,112,129 | 307,106,013 | 307,118,763 | +7.21 | 18.8 | 32.8 | 31.4 | 8.5 | 8.5 | 26,890 | 53,778 | 80,666 | 44.5 | 509 |
| S1b_joints_high | 341,255,926 | 341,249,810 | 341,262,560 | +19.13 | 26.9 | 29.5 | 28.3 | 7.6 | 7.6 | 30,568 | 61,134 | 91,699 | 100.0 | 526 |
| S2a_unworked | 189,912,719 | 189,906,603 | 189,919,353 | −33.71 | 19.6 | 53.1 | 0.0 | 13.7 | 13.7 | 14,266 | 28,531 | 42,795 | 22.7 | 450 |
| S2b_fine | 359,341,396 | 359,335,280 | 359,348,030 | +25.44 | 10.3 | 28.0 | 47.1 | 7.2 | 7.2 | 24,666 | 92,426 | 138,638 | 40.2 | 598 |
| S3a_rails_tallow | 227,595,070 | 227,589,321 | 227,602,063 | −20.55 | 16.3 | 18.4 | 42.4 | 11.4 | 11.4 | 21,811 | 43,622 | 65,432 | 27.6 | 293 |
| S3b_rails_grease | 214,230,659 | 214,224,041 | 214,236,781 | −25.22 | 17.3 | 13.3 | 45.1 | 12.1 | 12.1 | 21,095 | 42,189 | 63,283 | 23.7 | 248 |
| S3c_dry_ground | 310,599,969 | 310,594,966 | 310,605,605 | +8.42 | 12.0 | 40.2 | 31.1 | 8.4 | 8.4 | 25,806 | 51,609 | 77,413 | 43.7 | 583 |
| S3d_rough | 346,903,024 | 346,895,937 | 346,909,115 | +21.10 | 10.7 | 46.5 | 27.8 | 7.5 | 7.5 | 27,512 | 55,021 | 82,531 | 48.1 | 732 |
| S3e_oxen | 222,800,124 | 222,779,482 | 222,816,130 | −22.22 | 16.7 | 16.7 | 43.3 | 11.7 | 11.7 | 21,631 | 43,261 | 64,889 | 25.9 | 242 |
| S4a_lever | 318,688,467 | 318,665,596 | 318,709,208 | +11.25 | 11.7 | 31.6 | 30.3 | 8.2 | 18.3 | 28,147 | 56,286 | 84,420 | 47.6 | 515 |
| S4b_ramp | 464,464,737 | 464,458,621 | 464,471,371 | +62.14 | 8.0 | 21.7 | 20.8 | 5.6 | 43.9 | 43,839 | 87,676 | 131,512 | 100.0 | 587 |
| S4c_internal_stair | 269,259,861 | 269,251,442 | 269,267,519 | −6.01 | 13.8 | 37.4 | 35.9 | 9.7 | 3.3 | 22,814 | 45,626 | 68,437 | 37.7 | 490 |
| S5a_onsite | 228,989,774 | 228,987,698 | 228,991,224 | −20.06 | 16.2 | 18.9 | 42.2 | 11.4 | 11.4 | 24,665 | 49,329 | 73,993 | 17.7 | 120 |
| S5b_any_buildstone | 245,218,903 | 245,215,662 | 245,222,180 | −14.40 | 15.1 | 24.3 | 39.4 | 10.6 | 10.6 | 24,665 | 49,330 | 73,993 | 23.4 | 449 |
| S5c_complex_far | 327,025,651 | 327,017,816 | 327,032,301 | +14.16 | 11.4 | 43.2 | 29.5 | 7.9 | 7.9 | 24,666 | 49,331 | 156,442 | 40.2 | 499 |
| S6_density | 369,378,802 | 369,373,276 | 369,386,770 | +28.94 | 15.4 | 30.6 | 39.9 | 7.0 | 7.0 | 39,539 | 79,075 | 118,612 | 77.9 | 586 |
| S7_webster_classes | 292,420,830 | 292,414,919 | 292,427,699 | +2.08 | 13.1 | 35.1 | 33.7 | 9.1 | 9.1 | 24,666 | 57,113 | 57,113 | 40.2 | 599 |
| S8_learning | 276,878,657 | 276,872,541 | 276,885,291 | −3.35 | 12.7 | 36.4 | 33.1 | 8.9 | 8.9 | 24,666 | 46,331 | 65,445 | 40.2 | 475 |
| LOW | 68,698,232 | 68,694,177 | 68,702,838 | −76.02 | 15.3 | 34.1 | 0.0 | 37.8 | 12.8 | 6,689 | 13,378 | 20,066 | 2.5 | 162 |
| HIGH | 809,389,607 | 809,383,197 | 809,396,517 | +182.54 | 17.4 | 22.5 | 31.8 | 3.2 | 25.2 | 73,676 | 233,540 | 350,308 | 100.0 | 1,191 |

Oxen-hours for S3e (not man-hours): 95,131,317 per run on average.

Runtime: 22 scenarios × 100 seeds on 8 ranks took 55 min 3 s (103–180 s per scenario). Raster builds took about 10 s each, and each haul preprocess 5–10 s.

**Duration, median years to build** (from `output/scenarios_lit/duration_years.csv`, which has every scenario and TWR_N 1–7):

| Workforce | Calendar | webster 1 / 2 / 3 towers | LOW 1 / 2 / 3 | HIGH 1 / 2 / 3 |
|---|---|---|---|---|
| household (6) | 40 d/yr | 12.85 / 25.69 / 38.54 | 3.48 / 6.97 / 10.45 | 38.37 / 121.64 / 182.45 |
| household (6) | 90 d/yr | 5.71 / 11.42 / 17.13 | 1.55 / 3.10 / 4.64 | 17.05 / 54.06 / 81.09 |
| household (6) | 255 d/yr | 2.02 / 4.03 / 6.05 | 0.55 / 1.09 / 1.64 | 6.02 / 19.08 / 28.62 |
| Trump (15) | 40 | 5.14 / 10.28 / 15.42 | 1.39 / 2.79 / 4.18 | 15.35 / 48.65 / 72.98 |
| Trump (15) | 90 | 2.28 / 4.57 / 6.85 | 0.62 / 1.24 / 1.86 | 6.82 / 21.62 / 32.44 |
| Trump (15) | 255 | 0.81 / 1.61 / 2.42 | 0.22 / 0.44 / 0.66 | 2.41 / 7.63 / 11.45 |
| community (ABM, 50–200) | 40 | 1.52 / 2.09 / 2.35 | 0.42 / 0.57 / 0.64 | 4.52 / 9.75 / 10.94 |
| community (ABM, 50–200) | 90 | 0.68 / 0.93 / 1.04 | 0.19 / 0.25 / 0.29 | 2.01 / 4.33 / 4.86 |
| community (ABM, 50–200) | 255 | 0.24 / 0.33 / 0.37 | 0.07 / 0.09 / 0.10 | 0.71 / 1.53 / 1.72 |
| canton (500) | 40 | 0.15 / 0.31 / 0.46 | 0.04 / 0.08 / 0.13 | 0.46 / 1.46 / 2.19 |
| canton (500) | 90 | 0.07 / 0.14 / 0.21 | 0.02 / 0.04 / 0.06 | 0.20 / 0.65 / 0.97 |
| canton (500) | 255 | 0.02 / 0.05 / 0.07 | 0.01 / 0.01 / 0.02 | 0.07 / 0.23 / 0.34 |

Fixed-workforce rows are man-days ÷ (workers × days) and ignore crew-size limits: a household of 6 cannot itself drag a 2.4 t block that needs 24 people. As a check, Webster's own example is a team of 10 × 40 days ≈ 10 years for one tower (NUR 186). That is consistent with our 12.85 years for 6 workers and 5.14 for 15.

**Community threshold (30,000 ph).**
- Share of sites over the threshold: webster 40.2%, LOW 2.5%, HIGH 100%.
- In the baseline a single tower is 24,666 ph (median), just under the threshold. Every 2-tower site is over it.
- Three single-axis scenarios push even single towers over 30,000: S1b_joints_high (30,568), S4b_ramp (43,839) and S6_density (39,539).

### 8.7 Which axes matter most
- **The upper bound is driven by two choices: an external earth ramp and dense, hard stone.**
  - The ramp (S4b, +62%) is a fixed volume of earth per tower, 1,687.5 m³, about three times the 566 m³ of stone. Lifting therefore becomes the largest stage (43.9%).
  - Hard, dense stone (S6, +29%) doubles quarrying and dressing at basalt and granite sites and makes every block heavier to haul.
- **Dressing is the biggest single lever on the downside** (S2a, −34%), because in Webster's split it is 36% of the work.
- **Transport technology matters next:**
  - Rails or oxen (−21 to −25%) cut crews by μ/0.3, or to 2 men per block.
  - Rough ground (+21%) does the opposite.
- **Stone sourcing matters mainly for the complex sites.**
  - On-site stone saves 20% overall.
  - A 3 km haul for complexes more than doubles their median (73,995 → 156,442 ph for 3 towers).
- **Smaller effects:**
  - Procurement method (−9 to +19%).
  - Learning (−3%).
  - Webster's class totals (+2%): they raise 2-tower sites and lower 3-tower sites.
- **Bounds.** The combined LOW and HIGH span 68.7 to 809.4 million man-hours, a factor of about 12.
- **Duration** depends far more on who builds than on how:
  - one single tower takes about 13 years for a household working 40 days a year,
  - but about a week for a 500-strong canton (0.02 yr at 255 d/yr),
  - and about 1.5 years for the ABM's community crew working 40 days a year.

---

## 9. Adaptive alliances along the supply chain (added 28 Oct 2026)

Specified by the authors: agents learn and interact; they search for the best way to build a nuraghe and may ask other agents to cooperate. Everyone at the same nuragic site already cooperates; cooperation with other areas needs an alliance or a request (for example, neighbours quarry and drag the stones part of the way and the owners take over the last leg). Alliances and cooperation are sought along the whole supply chain, trust grows with reciprocity, and the earlier outputs stay unchanged.

Code: `alliance.py` (model), `report_alliance.py` (outputs), `tools/kbest_quarries.py` (quarry faces and routes), `tools/alliance_emergence.py` (emergence statistics), config block `alliance:`. Run with `mpirun -n 8 python model.py config.yaml --alliance all`, then `--alliance A0_verify` and `--alliance sensitivity`. Outputs go to `output/scenarios_alliance/`.

### 9.1 Definitions
- **Agent = a community.** There is one community per site, a repast4py `core.Agent` in a `SharedContext`.
  - Inside a community everyone cooperates, exactly as in `webster`/`full`: the same builders N_i (50 + 25(T−1), ±10%), the same block draws, crews ceil(m/100 kg) and trip times, and Webster's stages per tower (quarry 4,000, dress 10,400, walling 2,800 and lifting 2,800 ph).
- **Time.** One repast4py tick = one building season of `season_days` = 90 working days (NUR 185: Renfrew's 90 days); one season stands for one year.
  - A share `start_rate` = 1/450 of all sites starts each season, in a random order per seed (FREE). That spreads the starts over 450 seasons, matching the roughly 500 years of nuraghe building (Ialongo 2018, NUR 116).
  - Towers are built one after another (phasing, NUR 99–108). A community that has finished stays active as a helper and supplier.
- **Supply chain.** Each tower is a chain of stage tasks: quarry → dress → [track] → transport (relay leg 1 → leg 2) → build+lift. Dressing is placed at the quarry, following the plan's order (GEN 58 discusses dressing at the quarry versus at the site).
- **Actions at the start of each tower**, chosen by the community:
  - (a) the quarry face: one of the k = 5 cheapest distinct faces;
  - (b) for quarrying, dressing and build+lift, do it itself or ask a neighbour within R = 10 km (FREE);
  - (c) a transport relay: a neighbour nearer the quarry drags stone to a hand-off cell at f ∈ {0.25, 0.5, 0.75} of the route's drag cost, and the requester drags the last leg;
  - (d) whether to build a trackway along the route (A4, A5).
- **Accepting a request.** Community j accepts community i's request with Pr = σ(β0 + β1·T_ji − β2·backlog_j − β3·δ_ij):
  - T_ji is j's trust in i, starting at trust0;
  - backlog_j is j's queued work in working days;
  - δ_ij is the straight-line distance in km;
  - each asked community decides in turn, up to `max_asks` = 3; if all refuse, i does the task itself.
- **Trust.**
  - T_ij rises by Δ⁺ when j helps i.
  - T_ij falls by Δ⁻ when j refuses i after having received help from i.
  - Trust is bounded to [0, 1].
  - An **alliance** is a pair with min(T_ij, T_ji) ≥ θ.
- **Labour accounting.**
  - Every task's labour (plus the helpers' walk, B_j × distance / 1.4 m/s, once per task) is charged to the performer and counts toward the man-hours of the nuraghe it was spent on.
  - A site's `mh_total` = all labour on it, from anyone: `mh_own` + `mh_received`.
  - `mh_given` = the community's labour on other nuraghi.
- **Where cooperation can save labour.** Three mechanisms, each with its own switch:
  1. **Specialisation (learning curve).** On quarrying, dressing and build+lift, unit cost = c_s (1 + Q_js)^(log2 b), Wright 1936, with b = 0.85 per doubling (FREE; GEN 91).
     - Q_js = the community's cumulative output in stage s, in tower-equivalents.
     - Own work always counts (learning by doing, in every scenario). Help given counts only with `specialisation` on (A3, A5).
  2. **Shared trackway.** A trackway uses μ = 0.1 (tallowed rails, GEN 65) on the route cells, and is permanent.
     - It costs `track_cost_mh_per_m` = 2 man-hours per metre (FREE; scanned 0.5 / 2 / 5), split equally between the builder and its allies within R.
     - On track cells the owner and its current allies use the μ 0.1 raster (`cache/cost_mu/drag_cost_8dir_mu0.1_int.tif`).
     - Per tower the crew is sized for either μ 0.3 or μ 0.1, whichever needs fewer man-hours (equation in 9.2).
  3. **Shared quarry face.** Opening a fresh face costs `setup_mh` = 200 man-hours (FREE). Reusing one's own face is free; reusing an ally's face is free only with `shared_quarry` on (A5).
- **Learning rule.** Each action dimension (quarry face, ask for quarrying / dressing / build, relay fraction, track) has its own value table, chosen ε-greedily (ε = 0.1, α = 0.5).
  - The reward after each tower is r = −(own man-hours on that tower ÷ its tonnes).
  - The quarry-face values start from a model-based estimate (each community can see the cost of its own faces). The other values start at 0, so a community tries asking first.
  - **Social learning:** with probability p_imit = 0.3 per tower, the community copies the last strategy of the neighbour within R with the lowest cost per tonne, if that is lower than its own. Faces are copied only if the neighbour's face region is also among its own faces.
- **Scenarios** (100 seeds each, seeds 1..100):

| Scenario | Settings |
|---|---|
| A0_alone | no requests; seasons, phasing, quarry setup, learning by doing on own towers (b = 0.85), social learning of the quarry choice |
| A1_ask | requests and relays; acceptance fixed at 0.5; no trust dynamics |
| A2_trust | requests, relays, reciprocity and trust (the main scenario) |
| A3_trust_learning | A2 + specialisation (help given builds skill) |
| A4_trust_track | A2 + shared trackways |
| A5_full | A2 + specialisation + trackways + shared quarry faces |
| A5_full_freerider | A5 with 20% of communities (drawn per seed) that never help |
| A0_verify (check only) | A0 with b = 1, setup = 0, no imitation, always the cheapest face |

**FREE parameters** (no empirical value in the reviews):
- start_rate (1/450);
- R (10 km);
- relay_min_flatm (300);
- max_asks (3);
- trust0 (0.5), Δ⁺ (0.1), Δ⁻ (0.2), θ (0.7);
- β0, β1, β2, β3 (0, 2, 0.05 per day, 0.2 per km);
- ε (0.1), α (0.5), p_imit (0.3);
- b (0.85);
- track cost (2 man-hours per m);
- setup_mh (200);
- whole-workforce helper walks;
- defector share (20%, from the spec).

**From the sources:** season_days 90 (NUR 185), track μ 0.1 (GEN 65), Wright form (GEN 91), and every `webster` stage and transport parameter (sections 2 and 8).

### 9.2 Mechanics and equations
1. **Quarry faces** (`tools/kbest_quarries.py`).
   - Outcrop regions are the 8-connected components of the allowed-outcrop raster: 6,828 regions.
   - For each site, a reverse directional Dijkstra settles cells in order of drag cost *to* the site until 5 distinct regions are found. The first settled cell of a region is that region's cheapest quarry cell.
   - Each face's path is read back from the search tree, with the per-move costs at μ 0.3 and μ 0.1.
   - Results (`cache/logs/alliance_kbest.log`): 7,159 sites have 5 faces, 2 have 1, and 6 have 0. The 0-face sites are on San Pietro and use a local quarry, as in the baseline. Run time 117 s, peak RSS 1,892 MB.
2. **Labour and time.**
   - In every one of the 716,700 `webster` site-runs the builders were never idle (idle share 0.0%, section 8.6). A tower's labour is therefore exactly Σ_b c_b τ (transport) + the stage pool.
   - Each tower becomes a chain of tasks with fixed labour totals X_x. Each day every community spends N_j·h on its tasks (all tasks in chain order, then by age).
   - A task may not run ahead of its upstream task: D_x/X_x ≤ D_u/X_u. This generalises the ABM's delivered-stone cap.
   - The day loop is a numba function called once per season, plus once per tower completion.
3. **Relay legs.**
   - With h = the first path cell whose cumulative cost reaches f·C: C1 + C2 = C, τ1 = C1/(3600 v_d) + L1/(3600 v_w) + τ_l/2, and τ2 likewise.
   - The minimum haul applies only to whole routes, and relays only to routes costing at least 300 flat-m.
4. **Track crew choice.** Crew A is sized for μ 0.3: on track cells its cost is max(0.5 d, c₀.₁·0.1/0.3). Crew B is sized for μ 0.1: off the track its cost is max(0.5 d, c₀.₃·0.3/0.1). Transport man-hours = min(Σ c_b^0.3 τ(C_A), Σ c_b^0.1 τ(C_B)).
5. **Rank independence.** The island is coupled, so each rank simulates the whole island for its own seeds (`MPI.COMM_SELF`, as in `high`).
   - Blocks use the site streams default_rng([seed, uid]). Decisions use default_rng([seed, uid, 7]). Start order and defectors use default_rng([seed, 99991]).
   - The whole island takes about 0.85 GB RSS per rank. Merges run after every rank has freed its data.

### 9.3 Verification (`tests/verify_alliance.py`, `cache/logs/verify_alliance.log`; k-best checks in `cache/logs/alliance_kbest.log`)
- **k-best search.** Face-0 cost equals the multi-source haul_flatm for all 7,161 reachable sites (ALL EQUAL). Face-0 path length differs from haul_m at 53 sites, because of equal-cost ties (max 135.4 m); there the model keeps the baseline length. The per-move costs sum to the route cost for all 35,797 routes.
- (1) A0_verify vs webster: 716,700 site-runs (seeds 1-100); bitwise equal 444,562; max |difference| 1.75e-10 man-hours (max relative 5.9e-16); stage pool difference max 0; transport max 2.44e-08. The only differences are floating-point summation order: webster's mh_total = builders x elapsed hours from the daily kernel, A0's = sum of stage labour (idle = 0 in both).
- (2) trust toy (3 communities): accept raises trust: OK; refusal after help lowers trust: OK; defector refusing after help loses trust: OK; no penalty w/o debt: OK; acceptance logistic: OK; alliance = mutual threshold: OK  [trust0 0.5, +0.1, -0.2, accept p at trust0 and 5 km = 0.500]
- (3) relay additivity over 96,480 (route, fraction) pairs: |C1 + C2 - C| max 0 (exact integers); |trip1 + trip2 - trip| max 1.78e-15 h; |labour leg1 + leg2 - single| max 7.28e-12 man-hours (2,500 crew-units) -> OK
- (4) rank independence, A5_full_freerider, 300 clustered sites x seeds 1-4: -n 1 vs -n 8 identical (sites, pairs, strategies; full precision): True; help received 10,892,576 man-hours, 1 allied pairs
- ALLIANCE VERIFICATION PASSED

### 9.4 Results (100 seeds each; from `output/scenarios_alliance/alliance_comparison.csv`, printed in `cache/logs/alliance_run.log`)

Stage shares are % of all man-hours; "Received" is the share of all labour performed by another community. Median MH is the median of per-site means.

| Scenario | Island mean | Island min | Island max | % vs A0 | % vs webster | Quarry | Dress | Transport | Build+lift | Setup | Track | Walk | Received | Median MH 1 / 2 / 3 towers | % sites > 30k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A0_alone | 298,756,769 | 296,058,052 | 303,317,384 | +0.00 | +4.29 | 11.9 | 30.9 | 40.1 | 16.6 | 0.5 | 0.0 | 0.0 | 0.0 | 28,117 / 52,406 / 74,451 | 48.4 |
| A1_ask | 300,965,640 | 299,231,152 | 302,842,341 | +0.74 | +5.06 | 11.9 | 31.1 | 39.6 | 16.7 | 0.4 | 0.0 | 0.1 | 43.2 | 27,558 / 54,379 / 80,034 | 45.8 |
| A2_trust | 301,772,808 | 299,047,297 | 305,494,393 | +1.01 | +5.34 | 11.9 | 31.2 | 39.6 | 16.7 | 0.4 | 0.0 | 0.1 | 47.6 | 27,594 / 54,712 / 80,548 | 46.0 |
| A3_trust_learning | 263,191,739 | 260,811,336 | 267,684,514 | -11.90 | -8.12 | 10.8 | 27.8 | 45.4 | 15.1 | 0.6 | 0.0 | 0.4 | 34.3 | 23,727 / 47,151 / 68,128 | 37.0 |
| A4_trust_track | 286,218,502 | 282,731,284 | 289,347,722 | -4.20 | -0.09 | 12.6 | 32.9 | 33.7 | 17.6 | 0.5 | 2.6 | 0.1 | 49.6 | 26,952 / 52,844 / 78,149 | 42.2 |
| A5_full | 248,299,374 | 245,130,268 | 251,720,800 | -16.89 | -13.32 | 11.4 | 29.4 | 39.1 | 16.0 | 0.7 | 3.0 | 0.4 | 35.8 | 23,094 / 45,667 / 65,080 | 34.5 |
| A5_full_freerider | 248,081,443 | 244,677,557 | 251,040,449 | -16.96 | -13.40 | 11.5 | 29.5 | 38.8 | 16.1 | 0.7 | 3.0 | 0.4 | 34.2 | 23,167 / 45,509 / 65,040 | 34.6 |

| Scenario | Island seasons mean (min–max) | Median years, 1 tower | Alliances / seed | Mean alliance size (max) | Towers using a relay | Track cells / seed |
|---|---|---|---|---|---|---|
| A0_alone | 451.93 (451–455) | 1.08 | 0.00 | 0.00 (0) | 0.0% | 0 |
| A1_ask | 451.68 (451–458) | 1.02 | 0.00 | 0.00 (0) | 77.4% | 0 |
| A2_trust | 451.53 (451–457) | 1.02 | 364.27 | 2.03 (5) | 78.0% | 0 |
| A3_trust_learning | 451.34 (451–455) | 1.02 | 12.14 | 2.08 (5) | 77.6% | 0 |
| A4_trust_track | 451.49 (451–458) | 1.01 | 367.81 | 2.03 (4) | 77.0% | 107,435 |
| A5_full | 451.27 (451–455) | 1.01 | 12.28 | 2.07 (5) | 76.8% | 106,029 |
| A5_full_freerider | 451.21 (451–453) | 1.02 | 10.49 | 2.06 (4) | 76.5% | 105,773 |

Free-rider run: each defector received 11,795 man-hours of help per run, against 11,852 for a cooperator. Own labour was 22,782 against 22,772, and defectors gave 0. At the end, the trust others hold in defectors averages 0.498, against 0.567 for cooperators (`stats.json`).

Runtime: 7 scenarios × 100 seeds on 8 ranks took 21 min 23 s (78–175 s of simulation per scenario, plus merging).

### 9.5 What emerged (from `cache/logs/alliance_emergence.log`)
- **Asking spreads.** In A2_trust the share of towers that ask a neighbour rises from the first 25 seasons to the last 25: quarrying 0.529 → 0.639, dressing 0.589 → 0.654, build 0.546 → 0.640, relays 0.758 → 0.796, relays at f = 0.75 0.260 → 0.351. Social imitation grows from 0.226 to 0.297 of towers.
  - The reward is the requester's *own* man-hours, so asking always pays for the asker. Help, however, does not save labour by itself: in A1 and A2 the island total rises by 0.74% and 1.01% over A0. Two things cause the extra. The helpers walk to the task. And a community that delegates forgoes its own learning by doing on later towers, because in A1 and A2 help given does not build the helper's skill: the median 2-tower site rises from 52,406 (A0) to 54,712 man-hours (A2). Single towers get slightly cheaper (27,594 vs 28,117), because some helpers already have experience from their own towers. The cheapest face is chosen equally often in A0 and A2 (0.873 of towers in the last 25 seasons).
- **Specialisation is the mechanism that saves labour.**
  - When help given builds skill (A3), the top 10% of suppliers deliver 28.5% of all craft-stage help (23.1% in A2). Median final skill multipliers are 0.916 for quarrying, 0.917 for dressing and 0.916 for build (lowest 0.678).
  - The island total falls by 11.90% against A0.
- **Trackways** (A4) cut transport from 40.1% to 33.7% of labour and the island total by 4.20%. About 107,435 track cells are built per seed, and 0.510 → 0.584 of towers choose to build one.
- **Everything together** (A5_full): −16.89% against A0 and −13.32% against `webster`. The median single tower costs 23,094 man-hours against 28,117 in A0, and the share of sites over 30,000 ph falls from 48.4% to 34.5%.
- **Alliances stay small.**
  - In A2, 364 allied pairs form per seed. Their mean component size is 2.03, the largest 5, and only 3 pairs are allied in ≥ 50% of seeds.
  - With specialisation (A3, A5) requests go to the most skilled neighbour rather than the most trusted, so trust is rarely mutual: about 12 alliances per seed.
  - The alliance network is a scatter of reciprocating pairs, not cantons.
- **Free-riders are not frozen out.** Defectors receive as much help as cooperators (11,795 vs 11,852 man-hours) and their island total is unchanged (−16.96% vs −16.89% for A5).
  - Trust can only punish a refusal by someone who has received help, and needs are not repeated: most communities build one tower, in sequence over 450 seasons, so the community that helped a defector rarely needs it later.
  - Trust in defectors falls only slightly (0.498 vs 0.567). Without repeated needs or reputation shared by gossip, reciprocity cannot discipline free-riders. That itself is a result.
- **Years.** The island's completion (about 451 seasons) is set by the start schedule. A single tower takes a median of about 1 season in every scenario, since 50–55 builders finish the about 3,000 man-days of one tower within a 90-day season.

### 9.6 Sensitivity (A5_full, 10 seeds per cell = seeds 1–10; full factorial; `output/scenarios_alliance/sensitivity/sensitivity.csv`)
"% vs A0" is relative to the 100-seed A0_alone mean.

| R (km) | b | Track MH/m | Island mean | min | max | % vs A0 | Received | Track share | Alliances / seed | Median MH 1 tower |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | 0.85 | 0.5 | 249,924,252 | 248,475,382 | 252,071,413 | -16.35 | 41.8% | 0.8% | 39.8 | 23,466 |
| 5 | 0.85 | 2 | 255,864,502 | 255,064,517 | 258,048,999 | -14.36 | 40.7% | 2.8% | 37.8 | 23,827 |
| 5 | 0.85 | 5 | 266,153,487 | 265,309,647 | 268,696,080 | -10.91 | 38.9% | 6.4% | 37.0 | 24,338 |
| 5 | 0.95 | 0.5 | 273,511,073 | 272,362,468 | 275,494,550 | -8.45 | 46.4% | 0.7% | 40.0 | 25,699 |
| 5 | 0.95 | 2 | 279,590,816 | 278,606,436 | 281,663,000 | -6.42 | 45.2% | 2.6% | 41.0 | 26,108 |
| 5 | 0.95 | 5 | 289,755,424 | 288,428,982 | 292,455,464 | -3.01 | 43.4% | 5.8% | 38.0 | 26,672 |
| 5 | 1 | 0.5 | 286,321,229 | 284,916,483 | 288,465,815 | -4.16 | 50.0% | 0.7% | 351.9 | 27,027 |
| 5 | 1 | 2 | 292,332,267 | 291,014,068 | 293,791,518 | -2.15 | 48.9% | 2.5% | 353.5 | 27,376 |
| 5 | 1 | 5 | 302,685,496 | 301,217,756 | 304,674,552 | +1.31 | 47.2% | 5.6% | 348.5 | 28,052 |
| 10 | 0.85 | 0.5 | 243,026,667 | 241,732,346 | 244,949,536 | -18.65 | 36.9% | 0.8% | 12.5 | 22,826 |
| 10 | 0.85 | 2 | 249,019,479 | 247,536,945 | 250,790,302 | -16.65 | 35.8% | 3.0% | 12.4 | 23,136 |
| 10 | 0.85 | 5 | 260,052,664 | 258,779,805 | 262,256,959 | -12.96 | 34.1% | 6.7% | 12.7 | 23,754 |
| 10 | 0.95 | 0.5 | 270,274,111 | 269,130,761 | 272,252,622 | -9.53 | 42.7% | 0.7% | 12.5 | 25,356 |
| 10 | 0.95 | 2 | 276,212,652 | 274,744,037 | 277,611,288 | -7.55 | 41.6% | 2.7% | 13.4 | 25,741 |
| 10 | 0.95 | 5 | 287,284,611 | 286,074,531 | 289,122,065 | -3.84 | 39.8% | 6.1% | 13.4 | 26,380 |
| 10 | 1 | 0.5 | 285,530,580 | 284,609,646 | 286,694,286 | -4.43 | 51.5% | 0.7% | 368.2 | 26,958 |
| 10 | 1 | 2 | 291,484,727 | 290,266,465 | 292,798,111 | -2.43 | 50.3% | 2.6% | 363.5 | 27,315 |
| 10 | 1 | 5 | 302,275,748 | 300,966,719 | 303,982,053 | +1.18 | 48.4% | 5.9% | 359.7 | 27,932 |
| 20 | 0.85 | 0.5 | 249,943,720 | 246,866,294 | 252,066,991 | -16.34 | 26.5% | 0.7% | 6.0 | 23,725 |
| 20 | 0.85 | 2 | 255,689,344 | 252,967,116 | 258,236,280 | -14.42 | 25.5% | 2.8% | 5.6 | 23,945 |
| 20 | 0.85 | 5 | 266,234,313 | 263,526,752 | 267,826,244 | -10.89 | 24.4% | 6.4% | 4.2 | 24,519 |
| 20 | 0.95 | 0.5 | 272,100,657 | 270,737,993 | 273,590,196 | -8.92 | 31.3% | 0.7% | 5.1 | 25,690 |
| 20 | 0.95 | 2 | 277,274,736 | 275,501,006 | 278,825,995 | -7.19 | 30.2% | 2.6% | 5.4 | 25,965 |
| 20 | 0.95 | 5 | 288,695,648 | 286,587,036 | 290,009,962 | -3.37 | 29.2% | 6.0% | 5.5 | 26,694 |
| 20 | 1 | 0.5 | 284,419,710 | 282,801,897 | 285,735,916 | -4.80 | 52.3% | 0.7% | 372.7 | 26,823 |
| 20 | 1 | 2 | 289,996,761 | 288,561,591 | 292,536,535 | -2.93 | 50.8% | 2.6% | 367.3 | 27,146 |
| 20 | 1 | 5 | 301,003,593 | 299,749,051 | 302,543,856 | +0.75 | 48.9% | 5.9% | 365.3 | 27,784 |

- **The learning rate dominates.** At R = 10 km and track cost 2 MH/m, A5 is −16.65% vs A0 with b = 0.85, −7.55% with b = 0.95, and −2.43% with b = 1 (no learning). With b = 1, alliances return to about 360 per seed, because requests are again ordered by trust rather than skill.
- **Track cost** moves the total by about 6 points between 0.5 and 5 MH/m. Without learning (b = 1) and at 5 MH/m, A5 is costlier than A0 (+0.75% to +1.32%).
- **R matters less.** 10 km gives the lowest totals. At 20 km more requests go to distant specialists (received share falls to 24–31% with learning), and at 5 km fewer specialists are in reach.
- Runtime: 27 cells × 10 seeds on 8 ranks. The first attempt was killed by the 8 GB cap after 18 cells, because a neighbour structure was kept for each of the three R values. It was fixed by keeping one at a time, and the run resumed from the parts on disk (10 min 7 s in total for the two passes).

### 9.7 Self-review against the spec: deviations and interpretations
1. **Capacity model.** Inside the alliance module the daily crew-by-crew kernel is replaced by a stage-task capacity model, in which each community spends N·h man-hours a day on its tasks. Labour per tower is the same as `webster` (Σ crew × trip + Webster stages; verification 1: max difference 1.75e-10 man-hours over 716,700 site-runs). This is valid because idle time was exactly 0 in every webster run. Durations follow from the capacity, with the delivered-stone cap generalised to the whole chain.
2. **Chain order.** Dressing is a stage at the quarry, before transport, following the spec's order quarry → dress → transport → lift/build. Webster's build stage and lifting are one task "build" (split 50/50 in the outputs as `mh_build` / `mh_lift`).
3. **Learning curves** apply to the craft stages (quarry, dress, build). Transport cost stays physical (crews × trips). Own work builds skill in every scenario, as the spec's learning by doing in A0. Help given builds the helper's skill only with specialisation (A3, A5). Skill is updated when a task is created.
4. **A0 includes social learning of the quarry choice** (imitation is information, not labour). Quarry-face values start from each community's own cost estimate, so the cheapest face is chosen by about 87% of towers.
5. **Trust is directional.** An alliance needs mutual trust ≥ 0.7. Candidates are ordered by skill (with specialisation), then by the requester's trust, then by distance; at most 3 are asked.
6. **Trackways** follow the chosen route without re-routing and are permanent. Labour is split equally between the builder and its allies within R. Access is for the owner and its current allies. Transport waits only for the builder's share. The crew-sizing approximation off and on the track is described in 9.2.
   **Track access rule (30 Oct, the authors' NEW-2; documentation only, BUGFIX_REPORT B17).** A track's cells are registered to their owner when the track tasks are *created* (at the start of the tower), not when they finish (`alliance.py`, `track_owner[c] = i` in `start_tower`). So (a) the owner's own transport waits only for the owner's share of the track task, not for the allies' shares; (b) any community allied with the owner at the time it plans a transport may use the track at the discounted cost before all of its track tasks have finished, possibly in the same season; and (c) `track_use` (the per-cell use counter) is incremented when a transport task is created, not when it runs. The track labour itself is always charged in full; only the timing of access is early. Measured effect (scratch/bug1030/tracks_early.py, 400-site subsets, 1 seed): on one 400-site test 0 of 623 towers used a foreign track that was still unfinished; in the densest 400-site area 1 of 457 towers did, worth 0.11% of transport and 0.02% of total man-hours. MOST_REALISTIC has no trackways (rails are priced by its tech rules).
7. **Relays** need routes costing at least 300 flat-m. Load/unload is split half per leg, and there is no extra cost at the hand-off.
8. **Helpers** walk with their whole workforce, once per task.
9. **Daily order.** Tasks are worked in chain-stage order, then by age, not own-first.
10. **YEARS** = finish season − start season + 1, with one season of 90 days per year. The island's completion (about 451 seasons) is set by `start_rate`.
11. **Defectors** never help but still ask. The 20% are drawn per seed.
12. **Rank independence** comes from the seed-parallel design: each rank simulates the whole island. It was tested on a 300-site cluster (verification 4).
13. **Seeds actually run:** 100 for each of the 7 scenarios and for A0_verify, and 10 per sensitivity cell. No GPU was needed: the 7 scenarios took 21 min 23 s.

### 9.8 Cooperation networks by role (added 28 Oct 2026, the authors' request)
Specified by the authors: networks of stone cutters, of transport and of builders, which together show a communication network (how cooperation links form).

**Model change (bookkeeping only).** The pair files `seed_NNNN.pairs.csv.gz` now also carry, for each direction, the man-hours and the number of tasks per stage: `help_ab_quarry`, `help_ab_dress`, `help_ab_transport` (relay leg 1 plus any transport help), `help_ab_build`, `help_ab_track`, the same for `ba`, and `n_ab_<stage>` / `n_ba_<stage>`. The columns are appended after the original ones, and no extra random draws are made. The 7 scenarios × 100 seeds were rerun (15 min 3 s on 8 ranks).

**Bit-identity check** (`tests/verify_alliance_identity.py`, `cache/logs/verify_alliance_identity.log`). The rerun was compared with a saved copy of the previous parts and outputs:
- A0_alone: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- A1_ask: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- A2_trust: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- A3_trust_learning: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- A4_trust_track: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- A5_full: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- A5_full_freerider: 100 seeds, 600 part files compared: differing 0 ; pair files with a differing original column 0; stage sums != totals 0; merged outputs differing none -> IDENTICAL
- alliance_comparison.csv byte-identical: True
- ALLIANCE BIT-IDENTITY PASSED

**Layers** (`tools/alliance_networks.py`, `cache/logs/alliance_networks.log`):
- stone = quarrying + dressing;
- transport = relay leg 1 and transport help, plus trackway labour (track is folded into transport because it is transport infrastructure and its volume is small: 2.5% of A5 labour);
- build = walling and lifting;
- all = every stage.

**Definitions.** For layer ℓ and seed r, G^ℓ_r is the directed help graph (an edge i→j when i worked on j's nuraghe in that layer), with weight w^ℓ_ij,r = man-hours.
- FREQ^ℓ_ij = the share of seeds with w > 0. w^ℓ_ij = the mean over all seeds.
- **Core links:** FREQ ≥ 0.5.
- **Betweenness:** on the undirected mean network of links with FREQ ≥ 0.05, with distance 1/w, estimated from 300 sampled sources (seed 1).
- **Louvain communities:** on the core network (seed 1).
- **Hubs:** the top 5% of helpers by out-strength in a layer (FREE threshold).
- **Reciprocal link:** help went both ways in the same layer and seed.
- **Link length:** the straight-line distance between the two sites.
- **Haul of a node:** its least-cost path length to the nearest permitted outcrop (`sites_haul.csv`).

**Outputs per scenario and layer** (`output/scenarios_alliance/<scen>/network/<layer>/`): `edges.csv.gz` (all links), `edges.shp` (FREQ ≥ 0.05), `core_edges.shp`, `nodes.csv`/`.shp`, `network.graphml` (FREQ ≥ 0.05), `network_by_seed.csv`, `degree_distribution.csv`, `metrics.json`.

**Outputs per scenario:** `community_roles.csv`/`.shp`.
- ROLE = the layer (stone, transport, build or track) a community gives the most labour to in a run, taken as the modal value over the runs in which it helps at all.
- ROLE_CONS = the share of those runs with that role.
- HELP_FREQ = the share of runs with any help given.
- GV_* = the mean labour given per run. SK_* = the mean final skill.
- The recomputed A5_full file matches the project team's file in ROLE, ROLE_CONS and HELP_FREQ for all 7,167 communities. GV_* differ by at most 0.1 man-hours (rounding).

**Cross-scenario output:** `output/scenarios_alliance/network_comparison.csv`, one row per scenario × layer. Runtime: 3 min 35 s with 6 worker processes.

**Results** (medians over seeds unless stated):

| Scenario | Layer | Links / run | Reciprocal | Median link km | Helpers ≥ 5 served | Max out-degree (median / max) | Core links | Largest core component | Top-5% hub share of help | Hubs on outcrop (helpers) | Hub / helper mean haul km |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1_ask | stone | 7,916 | 34.5% | 0.77 | 0.1% | 5 / 6 | 6,448 | 29 | 14.2% | 46% (51%) | 0.71 / 0.70 |
| A1_ask | transport | 1,780 | 1.6% | 0.95 | 0.0% | 4 / 5 | 399 | 10 | 32.5% | 2% (50%) | 3.42 / 0.71 |
| A1_ask | build | 4,780 | 21.8% | 0.75 | 0.0% | 4 / 6 | 1,329 | 16 | 13.9% | 47% (51%) | 0.69 / 0.70 |
| A1_ask | all | 11,282 | 43.1% | 0.81 | 0.9% | 6 / 8 | 9,905 | 93 | 15.0% | 21% (51%) | 2.10 / 0.69 |
| A2_trust | stone | 7,770 | 38.0% | 0.73 | 0.1% | 5 / 7 | 7,714 | 29 | 13.7% | 48% (51%) | 0.61 / 0.70 |
| A2_trust | transport | 1,956 | 1.7% | 0.94 | 0.0% | 4 / 6 | 734 | 15 | 32.5% | 3% (50%) | 3.35 / 0.70 |
| A2_trust | build | 5,070 | 18.6% | 0.82 | 0.0% | 5 / 6 | 930 | 11 | 12.7% | 48% (51%) | 0.50 / 0.70 |
| A2_trust | all | 11,418 | 43.6% | 0.81 | 0.8% | 6 / 8 | 10,118 | 217 | 14.5% | 18% (51%) | 2.15 / 0.70 |
| A3_trust_learning | stone | 8,597 | 1.5% | 5.28 | 55.4% | 127 / 178 | 6 | 3 | 16.9% | 52% (51%) | 0.62 / 0.70 |
| A3_trust_learning | transport | 1,946 | 1.8% | 0.91 | 0.3% | 8 / 16 | 1,062 | 13 | 31.1% | 3% (50%) | 3.28 / 0.71 |
| A3_trust_learning | build | 4,483 | 0.6% | 5.27 | 52.3% | 102 / 129 | 0 | 0 | 18.7% | 50% (51%) | 0.70 / 0.70 |
| A3_trust_learning | all | 14,094 | 2.8% | 4.74 | 21.7% | 151 / 197 | 1,272 | 16 | 17.6% | 17% (51%) | 2.36 / 0.70 |
| A4_trust_track | stone | 7,784 | 38.0% | 0.73 | 0.1% | 5 / 7 | 7,707 | 29 | 13.7% | 48% (51%) | 0.60 / 0.70 |
| A4_trust_track | transport | 2,073 | 5.0% | 0.91 | 0.0% | 4 / 6 | 723 | 15 | 32.3% | 3% (50%) | 3.30 / 0.71 |
| A4_trust_track | build | 5,073 | 18.7% | 0.82 | 0.0% | 5 / 6 | 942 | 8 | 12.8% | 50% (51%) | 0.51 / 0.70 |
| A4_trust_track | all | 11,397 | 43.5% | 0.81 | 0.8% | 6 / 8 | 10,092 | 217 | 14.3% | 21% (51%) | 2.04 / 0.70 |
| A5_full | stone | 8,610 | 1.5% | 5.28 | 55.2% | 131 / 180 | 3 | 3 | 17.0% | 51% (51%) | 0.64 / 0.70 |
| A5_full | transport | 1,925 | 2.1% | 0.92 | 0.3% | 8 / 15 | 978 | 16 | 31.0% | 3% (50%) | 3.23 / 0.70 |
| A5_full | build | 4,485 | 0.6% | 5.28 | 51.9% | 100 / 120 | 0 | 0 | 18.8% | 51% (51%) | 0.66 / 0.70 |
| A5_full | all | 14,102 | 2.8% | 4.75 | 21.7% | 155 / 213 | 1,209 | 18 | 17.4% | 20% (51%) | 2.21 / 0.70 |
| A5_full_freerider | stone | 8,362 | 1.3% | 5.30 | 58.2% | 132 / 180 | 1 | 2 | 16.7% | 52% (51%) | 0.65 / 0.69 |
| A5_full_freerider | transport | 1,757 | 1.6% | 0.96 | 0.4% | 8 / 14 | 315 | 5 | 30.3% | 4% (50%) | 3.17 / 0.71 |
| A5_full_freerider | build | 4,377 | 0.5% | 5.30 | 54.4% | 99 / 117 | 0 | 0 | 18.7% | 50% (51%) | 0.64 / 0.70 |
| A5_full_freerider | all | 13,486 | 2.4% | 4.82 | 23.6% | 158 / 212 | 391 | 7 | 17.1% | 20% (51%) | 2.19 / 0.70 |

| Scenario | Jaccard stone–transport | stone–build | transport–build | Hubs in > 1 layer | Roles: stone / transport / build / none |
|---|---|---|---|---|---|
| A1_ask | 0.037 | 0.206 | 0.108 | 49.6% | 6,202 / 903 / 12 / 50 |
| A2_trust | 0.031 | 0.117 | 0.058 | 39.1% | 5,963 / 921 / 259 / 24 |
| A3_trust_learning | 0.000 | 0.000 | 0.000 | 28.3% | 2,600 / 4,307 / 255 / 5 |
| A4_trust_track | 0.035 | 0.121 | 0.065 | 38.6% | 6,030 / 853 / 256 / 28 |
| A5_full | 0.000 | 0.000 | 0.000 | 27.5% | 2,580 / 4,353 / 227 / 7 |
| A5_full_freerider | 0.000 | 0.000 | 0.000 | 28.4% | 2,570 / 4,349 / 240 / 8 |

**What forms in each layer (from the numbers above).**
- **Stone cutting.** With specialisation (A3, A5) the stone layer becomes star-shaped.
  - In A5_full, 55.2% of stone helpers serve five or more communities in a run. The busiest serves 131 (median over runs; 180 at most). Links are long (median 5.28 km) and almost never reciprocal (1.5%).
  - The stars form in a different place each run: only 3 stone links recur in at least half of the seeds.
  - Without specialisation (A2) the stone layer is a mesh of short reciprocal exchanges: 38.0% reciprocal, median 0.73 km, a maximum out-degree of 5, and 7,714 core links.
  - Stone hubs are no more often on an outcrop than other helpers (51% against 51%). They are hubs by skill, not by geology.
- **Transport** stays local and chain-like in every scenario.
  - Median link 0.92 km in A5_full; maximum out-degree 8 (median over runs); 2.1% reciprocal.
  - It has the most persistent core of any layer (978 core links in A5_full, 734 in A2).
  - Help is the most concentrated: the top 5% of transport helpers give 31.0% of it.
  - Transport hubs are almost never on an outcrop (3%). Their mean haul to the nearest outcrop is 3.23 km, against 0.70 km for all transport helpers: they are the communities along long haul routes.
- **Building** follows the stone layer.
  - With specialisation it is star-shaped: 51.9% of helpers serve ≥ 5, a maximum out-degree of 100, and no core links.
  - Without specialisation it is local (A2: 0.0% serve ≥ 5; 930 core links).
- **The overall network.**
  - In A2 it is a dense, modular mesh of short, often reciprocal links (43.6% reciprocal; largest core component 217).
  - In A5 it is a set of specialist stars over a persistent transport skeleton (1,209 core links, largest core component 18).
  - The layers' core links overlap little: Jaccard indices in the table above are 0 in A3/A5 and at most 0.21 in A1. Many hubs serve more than one layer (27.5% in A5_full; up to 49.6% in A1).
  - With specialisation, transport becomes the most common community role (4,353 of 7,167 in A5_full) and stone the second (2,580).

### 9.9 Where the savings are (added 28 Oct 2026, the authors' request)
`tools/alliance_savings.py` (`cache/logs/alliance_savings.log`) writes three files:
- `savings_by_stage.csv`: island man-hours by stage (mean over seeds) and the change against A0_alone, in man-hours and as % of the A0 total. Stage sums match the totals to 0.06 man-hours.
- `time_by_scenario.csv`: median working days per tower by TWR_N over site-runs, island completion, and days per tower for helped vs unhelped site-runs.
- `scenario_matrix.csv`: pairwise row-vs-column % differences in island man-hours and median days per tower, and the difference in island seasons.

| Scenario | Quarry | Dress | Transport | Build+lift | Setup | Track | Walk | Net |
|---|---|---|---|---|---|---|---|---|
| A0_alone | +0 (+0.00%) | +0 (+0.00%) | +0 (+0.00%) | +0 (+0.00%) | +0 (+0.00%) | +0 (+0.00%) | +0 (+0.00%) | +0 (+0.00%) |
| A1_ask | +434,620 (+0.15%) | +1,401,763 (+0.47%) | -386,276 (-0.13%) | +650,712 (+0.22%) | -164,998 (-0.06%) | +0 (+0.00%) | +273,051 (+0.09%) | +2,208,871 (+0.74%) |
| A2_trust | +568,477 (+0.19%) | +1,736,827 (+0.58%) | -164,472 (-0.06%) | +749,086 (+0.25%) | -177,062 (-0.06%) | +0 (+0.00%) | +303,183 (+0.10%) | +3,016,039 (+1.01%) |
| A3_trust_learning | -7,185,066 (-2.40%) | -19,273,187 (-6.45%) | -306,936 (-0.10%) | -10,034,396 (-3.36%) | +113,476 (+0.04%) | +0 (+0.00%) | +1,121,079 (+0.38%) | -35,565,029 (-11.90%) |
| A4_trust_track | +582,352 (+0.19%) | +1,749,621 (+0.59%) | -23,334,152 (-7.81%) | +763,972 (+0.26%) | -179,066 (-0.06%) | +7,571,922 (+2.53%) | +307,085 (+0.10%) | -12,538,266 (-4.20%) |
| A5_full | -7,209,175 (-2.41%) | -19,311,119 (-6.46%) | -22,611,581 (-7.57%) | -10,037,020 (-3.36%) | +113,496 (+0.04%) | +7,474,723 (+2.50%) | +1,123,281 (+0.38%) | -50,457,394 (-16.89%) |
| A5_full_freerider | -7,085,316 (-2.37%) | -19,045,737 (-6.38%) | -23,362,087 (-7.82%) | -9,841,983 (-3.29%) | +111,316 (+0.04%) | +7,455,514 (+2.50%) | +1,092,967 (+0.37%) | -50,675,325 (-16.96%) |

| Scenario | Days / tower, 1 / 2 / 3 towers | Island seasons | Helped site-runs | Days / tower helped vs not |
|---|---|---|---|---|
| A0_alone | 63.0 / 43.0 / 30.7 | 451.93 | 0.0% | — vs 63.0 |
| A1_ask | 48.0 / 36.0 / 31.0 | 451.68 | 91.5% | 40.5 vs 63.0 |
| A2_trust | 45.0 / 36.5 / 31.7 | 451.53 | 93.9% | 40.0 vs 63.0 |
| A3_trust_learning | 45.0 / 30.5 / 22.7 | 451.34 | 90.8% | 37.0 vs 63.0 |
| A4_trust_track | 42.0 / 35.5 / 31.0 | 451.49 | 93.8% | 39.0 vs 63.0 |
| A5_full | 42.0 / 29.5 / 21.7 | 451.27 | 90.8% | 36.0 vs 63.0 |
| A5_full_freerider | 44.0 / 29.5 / 22.0 | 451.21 | 89.9% | 36.0 vs 63.0 |

**Reading.**
- **Specialisation** (A3) saves on the craft stages: dressing −6.45%, walling and lifting −3.36%, quarrying −2.40% of the A0 total, against +0.38% for helpers' walking.
- **Tracks** (A4) save 7.81% on transport but cost 2.53% to build.
- **Asking alone** (A1, A2) adds labour on the craft stages, because communities lose learning by doing on their own later towers, and adds walking.
- **Help saves time.** Helped site-runs take a median 36–40.5 working days per tower, against 63 for unhelped ones.
- **The island's completion** (about 451 seasons) is set by the start schedule and barely changes.

### 9.10 Which scenarios build fastest, and why (added 28 Oct 2026, the authors' request)
`tools/fastest.py` (`cache/logs/fastest.log`) puts every scenario on one time metric: the median over sites of each site's mean working days from start to completion with the model's own workforce. For the alliance family these are the working days between a site's start and completion; 90-day seasons count only their working days, so the metric is the same.

The labour metric is island man-hours. Labour is decomposed by stage per family (`output/fastest_stage_decomposition.csv`):
- **baseline and cooperation:** the pool is split with Webster's Table 1 shares, which is exact for 2,500 man-days per tower; any excess is splits; walk = total − transport − pool − idle;
- **literature:** the stage columns of the runs files;
- **alliance:** the stage columns.

Days here are medians of per-site means. The per-site-run medians in 9.9 can therefore differ slightly (e.g. A5_full 40.3 vs 42.0 days).

| Rank | Family | Scenario | Days 1 / 2 / 3 towers | Time saved (1 tower) | Labour saved (island) | Effective workers / own builders (1 tower) |
|---|---|---|---|---|---|---|
| 1 | literature | LOW — Lower bound (cheapest options) | 16.8 / 22.9 / 25.7 | +72.5% | +76.0% | 49.9 / 51.2 |
| 2 | literature | S2a_unworked — Undressed (cyclopean) blocks | 35.4 / 48.5 / 54.4 | +42.0% | +33.7% | 50.6 / 51.2 |
| 3 | alliance | A5_full — Full supply-chain cooperation | 40.3 / 58.7 / 66.2 | +33.9% | +13.3% | 72.6 / 51.2 |
| 4 | alliance | A5_full_freerider — Full cooperation with free-riders | 41.0 / 59.2 / 67.3 | +32.8% | +13.4% | 71.3 / 51.2 |
| 5 | alliance | A3_trust_learning — Trust + specialisation | 41.5 / 60.5 / 69.0 | +31.9% | +8.1% | 72.3 / 51.2 |
| 6 | alliance | A4_trust_track — Trust + shared trackways | 43.6 / 71.7 / 95.1 | +28.5% | +0.1% | 78.0 / 51.2 |
| 7 | alliance | A2_trust — Asking with reciprocity and trust | 44.5 / 73.2 / 96.7 | +27.0% | -5.3% | 78.3 / 51.2 |
| 8 | alliance | A1_ask — Asking for help, no trust | 45.8 / 73.1 / 95.1 | +24.9% | -5.1% | 76.1 / 51.2 |
| 9 | literature | S3b_rails_grease — Sledge on greased rails | 52.0 / 71.6 / 80.3 | +14.8% | +25.2% | 50.9 / 51.2 |
| 10 | literature | S3e_oxen — Ox teams haul the sledges | 53.7 / 73.4 / 82.4 | +11.8% | +22.2% | 50.6 / 51.2 |
| 18 | baseline | baseline — Baseline: one community, full cooperation | 60.9 / 83.7 / 93.8 | +0.0% | +0.0% | 50.8 / 51.2 |

**Mechanism.** "Effective workers" = man-hours ÷ (days × 8) for the median single tower. Above the community's own builders it means more hands (help); equal means the same hands doing less work.
- **LOW, S2a and the rails/oxen scenarios** save time exactly in step with labour: they mean less work per tower.
- **The alliance scenarios** save more time than labour, because neighbours add hands: about 72–78 effective workers on a single tower against about 51 own builders. A1 and A2 build faster even though they use more labour.
- **Combined effects** (`output/fastest_combined_effects.csv`):

| Combination | Reference | Metric | Combined | Sum of parts | Product of parts |
|---|---|---|---|---|---|
| LOW = S1a_scree+S2a_unworked+S3a_rails_tallow+S4c_internal_stair+S5b_any_buildstone | webster | island man-hours | -76.02% | -83.96% | -61.56% |
| HIGH = S1b_joints_high+S2b_fine+S3d_rough+S4b_ramp+S6_density | webster | island man-hours | +182.54% | +156.74% | +278.31% |
| A5_full = A3_trust_learning+A4_trust_track | A2_trust | island man-hours | -17.72% | -17.94% | -17.28% |
| LOW = S1a_scree+S2a_unworked+S3a_rails_tallow+S4c_internal_stair+S5b_any_buildstone | webster | median days, 1 tower | -72.50% | -72.68% | -58.05% |
| A5_full = A3_trust_learning+A4_trust_track | A2_trust | median days, 1 tower | -9.46% | -8.70% | -8.56% |

LOW's levers overlap: −76.02% combined against −83.96% summed. A5 ≈ A3 + A4 relative to A2: −17.72% against −17.94%.

**Scenario key.** `tools/scenario_guide.py` writes `output/scenario_guide.csv` (38 rows: family, code, readable name, one-sentence description, sources, parameters, FREE), which is Appendix A of the report.

### 9.11 Deviations in the network, savings and fastest analyses
1. **Edges.** `edges.shp` and `network.graphml` keep only links with FREQ ≥ 0.05; the full list of up to 580k links per layer is in `edges.csv.gz`. Written in full, `edges.shp` was 240 MB per layer.
2. **Betweenness** uses the same FREQ ≥ 0.05 network, with 300 sampled sources. It is an estimate.
3. **Fixes to the project team's tool:**
   - it took the last hash directory alphabetically; it now takes the complete, most recent one;
   - node degrees on the any-seed network accumulated over 100 seeds; they are now per-seed means;
   - edge `TRUST` is now the helped community's trust in the helper.
4. **Hubs** are the top 5% by out-strength (FREE). "Serving ≥ 5" follows the spec.
5. **Track** is folded into the transport layer.
6. **Project team's files.** The old single-layer files in `A5_full/network/` were replaced by `network/all/`.

### 9.12 Late additions (28 Oct 2026, evening)
- **A Nurnet collaborator's ask/refusal counters and a Nurnet collaborator's formation bookkeeping** were folded into `alliance.py` with no random draws added or moved.
  - The pair files gain `asks_*`, `refused_*`, per-stage asks (`asks_ab_<stage>`) and `ask_only` rows (pairs known only from asks, with no help).
  - New per-seed files: `seed_NNNN.helplog.csv.gz` (season, helper, owner, man-hours) and `seed_NNNN.allied.csv.gz` (first season allied).
  - Asks are per request, and each request is for one stage task, so attributing them to a layer is exact. Track work is never requested.
- **Final rerun:** 7 × 100 seeds, 25 min 50 s on 8 ranks, on a shared machine (load average about 19).
  - Bit-identity against the saved reference (`cache/logs/verify_alliance_identity.log`): 600 part files per scenario differ in 0; original pair rows are identical; all merged outputs and `alliance_comparison.csv` are byte-identical. ALLIANCE BIT-IDENTITY PASSED.
  - For seed 1, the new help logs and alliance seasons reproduce a Nurnet collaborator's files exactly: identical keys, man-hours within 1e-10, identical alliance rows.
- **Refusal rate per layer** (`network_comparison.csv`, share of requests refused):

| Scenario | stone | transport | build | all |
|---|---|---|---|---|
| A1_ask | 50.0% | 50.1% | 49.9% | 50.0% |
| A2_trust | 31.7% | 38.6% | 46.4% | 37.4% |
| A3_trust_learning | 54.9% | 34.1% | 56.2% | 53.4% |
| A4_trust_track | 31.6% | 38.4% | 46.3% | 37.3% |
| A5_full | 54.9% | 34.0% | 56.2% | 53.4% |
| A5_full_freerider | 56.1% | 45.6% | 57.6% | 55.5% |

- **Relationship census** (`tools/census.py`; a Nurnet collaborator's definitions; population 519,638 pairs ≤ 10 km).
  - Recomputed for seeds 1–10, it equals a Nurnet collaborator's `relationship_census.csv` in every cell (max difference 0).
  - The 100-seed version is `output/census/relationship_census_v4_seeds1-100.csv`. a Nurnet collaborator's census uses seeds 1–10; the rest of the report uses 1–100.
- **Formation** (`tools/formation.py`, `output/formation_v4/`).
  - a Nurnet collaborator's "ever-allied pairs" (allied at any time) differ from the alliance tables' count (allied at the end of a run):

| Scenario | Ever allied / seed | Allied at end / seed | Seed 1: ever / end |
|---|---|---|---|
| A1_ask | 0.0 | 0.0 | 0 / 0 |
| A2_trust | 579.3 | 364.3 | 588 / 376 |
| A3_trust_learning | 14.1 | 12.1 | 18 / 16 |
| A4_trust_track | 584.0 | 367.8 | 565 / 361 |
| A5_full | 14.2 | 12.3 | 15 / 13 |
| A5_full_freerider | 12.4 | 10.5 | 7 / 6 |

- **Connected help networks** (`tools/components.py`): connected components of size ≥ 2 of the any-help graph.
  - Seed 1 equals a Nurnet collaborator's `seed-1 components file` (6 rows identical).
  - A connected help network is not an alliance: A5_full is one island-wide connected network with about 12 alliances per run.

| Scenario | Up to | Largest network, median (5–95%) | Share of sites | Networks, median |
|---|---|---|---|---|
| A1_ask | 200 | 44 (32–69) | 0.6% | 1,108 |
| A1_ask | end | 706 (451–988) | 9.9% | 454 |
| A2_trust | 200 | 44 (32–66) | 0.6% | 1,143 |
| A2_trust | end | 726 (498–1,116) | 10.1% | 448 |
| A3_trust_learning | 200 | 3,018 (2,874–3,304) | 42.1% | 52 |
| A3_trust_learning | end | 6,597 (6,461–6,674) | 92.0% | 13 |
| A4_trust_track | 200 | 43 (29–77) | 0.6% | 1,142 |
| A4_trust_track | end | 728 (520–970) | 10.2% | 448 |
| A5_full | 200 | 3,032 (2,877–3,304) | 42.3% | 52 |
| A5_full | end | 6,589 (6,441–6,685) | 91.9% | 13 |
| A5_full_freerider | 200 | 2,896 (2,781–3,164) | 40.4% | 56 |
| A5_full_freerider | end | 6,524 (6,374–6,619) | 91.0% | 14 |

- **Master comparison** (`tools/master_comparison.py`, `output/master_comparison.csv`): every family on the baseline webster = full (286,466,319 man-hours, seeds 1–100), with a parameter-base column and a `base_differs` flag.
  - Alliance rows also give % vs their own A0.
  - a Nurnet collaborator's GPU drag × crew grid (`output/crew/crew_drag_grid_gpu.csv`, 1,000 seeds per cell) is a separate sensitivity block.
  - Validation: GPU full ×1 at 0.6 m/s = 286,466,410 against CPU 286,466,319 (+0.000000%).
  - Crew size leaves man-hours unchanged where everyone or no one cooperates. It changes them through idle waiting in low and mixed, more so at slow drag speeds, and not monotonically in low (numbers in the report, from the CSV).
- **Sensitivity** (a Nurnet collaborator's files in `output/sensitivity/`):
  - The cooperation Morris screen (`morris_cooperation_gpu.csv`) is shown.
  - Pending: the cooperation and alliance Sobol analyses, and the second Morris screen.

### 9.13 Fixes of 30 October 2026 (the authors' NEW-1 and the sea payload; BUGFIX_REPORT B14-B21)
- **Lift per piece in the alliance tech rules (MOST_REALISTIC family).** Blocks split to fit the work party are lifted as pieces: the per-site stage hours use the site's piece count (lever/stair lift is linear in it), and the per-tower piece counts (`tower_nblk`) are used for the S9 hoist labour and the join-mode hands cap. Non-tech alliance scenarios never split, so their stages are unchanged.
- **Sea payload split in the alliance model.** As in the stand-alone S9 model (model.py), a block carried by boat may not exceed the craft payload (`sea.payload_kg` = 2,000 kg, Hazell & Fitzpatrick 2006). When a tower's chosen quarry face is a sea face, its heavier blocks are cut into the fewest equal pieces that fit both the craft and the crew; the pieces set the crews of every leg, the hoist (per piece), the cut cost (`split_cost_mh` per cut, on the quarry task) and, for lever/stair sites, the lift of the extra pieces. Land faces keep the land split. With non-tech sea scenarios (A1..A5 `_sea`, pre-network `_sea`) the effect is +0.01% island man-hours on a 300-site test (no change in seasons); these delivered runs were not rerun.
- **Join hands cap.** With pieces the cap counts pieces instead of blocks (build: 6 hands × pieces per course; quarry/dress: 4 / 2 hands × pieces; transport: the crews of the pieces, as before). It did not bind in any of ~2,000 joins on the 300-site test, before or after.

## 10. Pre-existing networks (added 28–29 Oct 2026, the authors' request)
Spec: `catalogue/PRE_NETWORKS_PLAN.md`. Code: `pre_networks.py`; config block `pre_networks:` (self-contained, so a Nurnet collaborator can run GPU sweeps). Run with `mpirun -n 8 python model.py config.yaml --pre all`. Outputs go to `output/scenarios_pre/`.

**Rules.**
- Ties exist at season 0. Requests go ONLY along ties and are accepted with p_tie = 0.9 (FREE), with no trust needed.
- Everything else is the alliance A2 rule set: stage tasks, relays, helper walking, seasons, phasing, quarry setup, and learning by doing on own towers.
- No coordination cost is modelled.
- A community offers only the request options for which it has ties, so empty tie sets reproduce A0_alone exactly.
- **Reach h:** a request may travel up to h ties. Each broker walks to the next community and back (1 person, FREE), and this is charged as labour on the asking community's nuraghe.

**Groups.**
- Seeded k-means on site coordinates, k = round(7,167 / size), generator_seed 2026 (FREE). G3_canton is seeded at the multi-tower nuraghi; G133_tribe merges cantons into 54 tribes.
- Realised sizes: G3 1,265 groups, mean 5.67. The plan's ~2.65 assumed ~2,700 canton seats, but the inventory has 1,265 multi-tower nuraghi. G5 mean 5.00; G9_verify 9.00 (sensitivity only, unverified in Ugas 2005); G20 20.02; G50 50.12; G133 132.72.

**Shapes.** chain, kmesh2/4/8, hub (the group's highest-TWR_N nuraghe; for G133, a two-level hub), smallworld (kmesh4 with 10% rewired within 10 km outside the group), complete, and partners 2/5/10 (no groups).

**Location.**
- Groups centred on or away from outcrops.
- Networks only in the north, central or south latitude third (PROVINCIA mixes two schemes), or only in top-tercile 30 km density cells.

**Other variants:** per-stage tie sets (D6), ties + trust (D7), tie lost after 2 refusals (D8), learning and tracks.

**Runs:** 56 scenarios × 100 seeds (main grid plus every variant), on the hybrid stone base. Run in four batches of 14 scenarios on 8 ranks, 26–27 min each (23:42–01:30). The 10-seed wide grid (252 cells) was NOT run on CPU; it is left for a Nurnet collaborator's GPU sweep from the config block.

**Fixes during the runs.**
- Two runs were OOM-killed. The cause: dense tie sets (G133 complete, 661k ties) held as Python sets added ~460 MB per rank. They are now one shared sorted numpy array per site (+64 MB). Rank-0 memory, logged per scenario, stayed at ~1.06 GB.
- Eight sites with identical coordinates could be their own k-nearest neighbour, creating self-ties. These are now removed, and all 56 scenarios were rerun fresh.

**Verification.**
- `P_none` == A0_alone per site: 100 of 100 seeds byte-identical (`cache/logs/verify_pre.log`).

**Results** (`pre_comparison.csv`; the 8 cheapest and 4 costliest):

| Scenario | Size / shape / reach / variant | Island MH | % vs A0 | % vs A2 | % vs A5 | Received |
|---|---|---|---|---|---|---|
| P_G20_kmesh4_track | G20_system / kmesh4 / 1 tracks | 277,128,330 | -3.47% | -4.65% | +16.25% | 50.7% |
| P_G20_kmesh4_learning | G20_system / kmesh4 / 1 specialisation | 281,385,263 | -1.99% | -3.18% | +18.04% | 48.1% |
| P_none | none / none / 1 no ties | 287,086,943 | +0.00% | -1.22% | +20.43% | 0.0% |
| P_G20_kmesh4_north | G20_system / kmesh4 / 1 region=north | 287,507,483 | +0.15% | -1.08% | +20.61% | 13.8% |
| P_G50_hub | G50 / hub / 1  | 287,508,221 | +0.15% | -1.08% | +20.61% | 38.6% |
| P_G20_system_hub | G20_system / hub / 1  | 287,569,499 | +0.17% | -1.06% | +20.63% | 39.9% |
| P_G3_canton_hub | G3_canton / hub / 1  | 287,799,526 | +0.25% | -0.98% | +20.73% | 38.9% |
| P_G20_kmesh4_central | G20_system / kmesh4 / 1 region=central | 288,166,916 | +0.38% | -0.85% | +20.88% | 16.9% |
| P_G20_system_complete | G20_system / complete / 1  | 291,014,798 | +1.37% | +0.13% | +22.08% | 49.0% |
| P_G133_tribe_kmesh8 | G133_tribe / kmesh8 / 1  | 291,056,266 | +1.38% | +0.14% | +22.10% | 49.6% |
| P_G133_tribe_smallworld | G133_tribe / smallworld / 1  | 291,061,733 | +1.38% | +0.14% | +22.10% | 48.9% |
| P_G133_tribe_complete | G133_tribe / complete / 1  | 291,068,755 | +1.39% | +0.15% | +22.10% | 49.6% |

**Findings.**
- **Pre-existing structure does not beat learned cooperation.**
  - Every pure tie network is within +0.15% to +1.39% of A0_alone, and close to A2_trust.
  - Only the variants that add a saving mechanism are cheaper: tracks −3.47% and specialisation −1.99% against A0.
  - The emergent A5_full remains far cheaper (−16.96% vs A0).
- **What matters among the network axes:**
  - Averaged over shapes, size changes the island total by 0.41 points; averaged over sizes, shape changes it by 0.93.
  - Hub networks are the cheapest pure networks (+0.15% to +0.66% vs A0), because requests concentrate on a few communities.
  - Reach matters little, and placement on or off outcrops not at all.
- **Hubs concentrate labour.** Hub communities give 62–91% of all help while being 2–20% of sites (`pre_hubs.csv`).
- **Location, like for like** (`pre_location.csv`): networked sites cost +0.67% (north), +1.24% (central) and +1.96% (south) against the same sites in A0. Groups with no on-outcrop member cost +1.60%, against +1.32% for groups with one.

## 11. Stone rule (added 28–29 Oct 2026, the authors' request)
**The rule.** The HYBRID baseline: a site quarries its recorded building stone where known, otherwise the nearest of 7 classes (limestone/marble, metamorphic, basalt, granite, acid volcanic, trachyte, andesite).
- **Source:** 10,662 records of Nurnet's data (site building stone) (`materiale`; aggregate statistics in outputs only). The mapping of values to lithology classes is in `config.yaml → materiale.map` and `output/materiale_mapping.csv`.
- **Hauls:** one multi-source Dijkstra per distinct class set (23 sets).
- **Use of the recorded stone:** fallback 5,052, recorded 2,114, recorded_unreachable_fallback 1 sites. Sandstone and marl lie on loose deposits and have no outcrop class, so those sites fall back to the 7-stone rule.
- **Comparisons:** `stones4` (old results, `output/stones4/`) and `stones7` (7 classes, no recorded stone; baseline in `output/stones7/`).

**Hauls under each rule:**

| Rule | Mean haul (flat-m) | Mean haul (m) | 90th pct haul (m) | Sites on own-rule outcrop | Unreachable |
|---|---|---|---|---|---|
| stones4 | 688 | 697 | 2,329 | 3,637 | 6 |
| stones7 | 249 | 258 | 750 | 5,186 | 0 |
| hybrid | 460 | 471 | 1,115 | 4,940 | 0 |

**Validation** (single-stone sites, 9 classes; hybrid agreement is 100% by construction for recorded sites):

| Rule | Single-stone sites | Recorded stone allowed by the rule | Model stone agrees | Agreement | Built of excluded stone |
|---|---|---|---|---|---|
| stones4 | 2,056 | 1,559 | 1,354 | 86.85% | 497 |
| stones7 | 2,056 | 1,911 | 1,475 | 77.18% | 145 |
| hybrid | 2,056 | 1,963 | 1,962 | 99.95% | 93 |

**Island man-hours** (`stone_rule_comparison.csv`, 100 seeds):
- Baseline: 286,466,319 (4-stone), 250,007,184 (7-stone, -12.73%), 278,136,996 (hybrid, -2.91%).
- Hybrid vs 4-stone by family (min / median / max): alliance -4.25 / -3.88 / -3.25%; baseline -2.91 / -2.91 / -2.91%; cooperation -5.22 / -2.91 / -1.28%; literature -5.40 / -2.66 / +0.00%.

**Re-verification on the hybrid base (all passed):**
- `webster` == `full` (0 h difference).
- Cooperation `full` == baseline, in every column.
- A0_verify == `webster` (max 4.66e-10 man-hours).
- `P_none` == A0_alone.
- Rank independence (baseline, `high`, `patchwork`, S3e, S6, HIGH, alliance cluster).
- Haul spot-checks.
- Webster calibration (0.89×).
- k-best face 0 == the multi-source haul at all 7,167 sites.

**Numbers in sections 1–9** were computed on the 4-stone base unless stated; the report recomputes every table from the hybrid outputs.


## 12. v11 (2 November 2026, approved by the authors)

### 12.1 Webster's man-days: which are 5-hour days (item 1)
Webster 1991 (Antiquity 65: 840–856), p. 852 (text and Table 1), builds his per-nuraghe costs from four rates:
- quarrying: 2,700 kg per man-day with a hardwood bar, **Erasmus 1965: 286** (500 man-days per single tower);
- transport: 1,200 kg per man-day, man-hauling with tumpline and sled over at most 200 m, **Erasmus 1965: 286–7**
  (1,100 man-days);
- rough dressing: 0.40 m³ per man-day, from **Abrams 1984: 165** (1,300 man-days);
- wall construction: 0.80 m³ per man-day, **Abrams 1984: 175–6** (700 man-days).
Webster states no day length. Erasmus's working day is about 5 hours (Erasmus 1965: 283, via Boswinkel 2021: 145;
the primary was not available). Abrams's man-day is 8 hours: Abrams (1994: 46–47) reports 7,200 kg of rubble per
person "in 8 hrs" (via Boswinkel 2021: 109); Abrams & Bolland (1999) use 8-hour workdays (via Boswinkel 2021: 146);
Devolder's 0.1 m³ per person-hour "based on experiment by Abrams" (Boswinkel 2021: 125, Table 7.11) equals Abrams's
0.8 m³ per man-day ÷ 8 h. Abrams 1984 itself was not read, so the 8 h for dressing and walling is the best-supported
reading, not a quotation; the alternative (every Webster man-day = 5 h) is the sensitivity C2_day5 (= MR_P10_v11_day5all).

v11 therefore converts Webster's man-days at their source day length (`config.yaml` `v11.webster_day_hours`:
quarry 5, transport 5, dress 8, build 8; `lit.md_hours`), instead of `hours_per_day` (8) for all. Effects:
- every scenario that uses Webster's quarry man-days (the `baseline`/cooperation pool, TOST, lit scenarios with the
  `webster` quarry rule, all alliance and pre-network scenarios without technique rules): quarrying 500 × 5 = 2,500
  instead of 4,000 person-hours per tower (−1,500 per tower);
- the transport man-days are never used as labour (hauling is simulated), so nothing changes there;
- MOST_REALISTIC (all P10/P20/P100 variants, S10–S14, C1–C3, M1–M4) uses no Erasmus-based man-day (quarrying at
  Boswinkel's per-m³ rates, hauling simulated; its Webster stages are the Abrams-based dressing and walling, 8 h):
  its results are unchanged (verified: subset and full-island part files identical in content);
- TOST `hours_per_day` ends: the Webster stages no longer scale with the builders' working day (a source's man-day is
  a fixed amount of work); only the schedule does.
Calibration (section 3, NID1501300): Webster's single tower in person-hours becomes 500×5 + 1,100×5 + 1,300×8 +
700×8 = 24,000 (was 28,800 at 8 h); the model's 25,415 becomes 23,915 (ratio 0.996); Webster's transport,
1,100 × 5 = 5,500 person-hours, against the model's simulated 5,415.

### 12.2 Citation fixes (items b, c)
- (b) S2b / MOST_REALISTIC fine facing: 131.5 and 40.85 ph/m³ are Boswinkel's total all-stage costs per m³ (Table 8.3,
  p. 144), not dressing rates. The model's use (the difference, 90.65 ph/m³, as the extra cost of facade over
  cyclopean masonry on the facing of complexes with ≥ 3 towers) is unchanged; labels corrected in code comments,
  this file and the report. C3_dress gives the dressing-only alternative (57–62 ph/m³, pp. 120–121, Table 7.8).
- (c) Oxen: 481–549 N (Boswinkel 2021: 52 n. 37); midpoint 515 N in v11 (v10: 520 N from the misprinted 491). Only
  ox scenarios (S3e_oxen, REALISTIC_oxen) use it; none of them is in the v11 rerun list (v10 values kept, marked).

### 12.3 Pulling force (item d): sensitivity only
300 N per person (30 kgf; 10 haulers per tonne, from press reports of the Harris 2016 experiment: ASSUMPTION since v12) is a short-burst peak; a sustained effort is ~125 N
(Boswinkel 2021: 52, from Hertzberg's 104 W at 0.83 m/s). The headline keeps 300 N. MR_P10_v11_pull125 sets every
per-person pulling force to 125 N (`f_person_kgf` 12.7465, `pull_kg_per_person` 42.49 at μ 0.3; config
outputs/config_v11_pull125.yaml); the boat-crew factor of the sea legs is pinned at the headline value
(`sea.boat_pull_kg_per_person: 100`), so only land hauling changes.

### 12.4 Ratings and obsolete runs (items e, f)
- The 30 Oct (b) master table had no base rating for 47 rows, so its `realism_min` showed only the schedule rating
  (e.g. P_none_P10: 4). outputs/summary/master_table_v11.csv fills them from the 1 Nov (b) judgements
  (REALISM_RATINGS_V11.md; each labelled a judgement) and recomputes `realism_min`.
- The season-length runs (40/120/210 days, 29 Oct) used pre-fix code and show identical man-hours across season
  lengths; the authors dropped the scenario on 30 Oct. They are marked "obsolete" in every v11 table and not rerun.

### 12.5 Reruns and identity
v11 code with the v11 switches off (`outputs/config_v11_off.yaml`) reproduces the v10 MR_P10 part files exactly
(full island, 100 seeds: outputs/identity/IDENTITY.txt). Reruns: code/V11_NOTES.md and outputs/summary/v11_runs.csv.
