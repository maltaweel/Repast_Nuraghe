# Nuraghe build ABM: methods

**Question.** How many man-hours did it take to build each of the 7,167 nuraghi in the Nurnet inventory, counting stone transport from the nearest permitted outcrop plus quarrying, dressing and building?

**Framework.** Python with repast4py 1.3.1 (MPI), numba and numpy. Every number below is a parameter in `config.yaml`, a value from the literature, or a count of the prepared inputs. This file describes methods only: model results (totals, scenario effects, calibration outcomes, sensitivity indices, seed statistics) are not part of it. Results are reported separately in the results data.

**Scope.** This file records the model families in the order they were built (sections 1-12); section 13 lists where the current rules of the model (the code in `code/`, run with the configs in `config/scenarios/`) are described. Parameter values in this file are those of `config/scenarios/config_full_audited.yaml`. The headline scenario family (MOST_REALISTIC, season-based community engine with per-site technique rules) is specified in full in `ODD/ODD.md`, which follows the code; where this file and the ODD differ, the ODD and the code win (ODD Appendix D). Where a rule described below was changed later, a note marked **Current code:** gives the rule the code of the model applies (for the pricing of lift see section 13).

---

## 1. What was done, step by step

### Step 1: Inputs (all EPSG:25832)
- **Sites.** `nurnet_nuraghi.shp` has 7,167 points. The model uses `TWR_N` (number of towers, 1–7) and carries `TWR_FILL` (1 = tower count assumed) through to the outputs.
- **Cost raster.** `sardinia_drag_cost_8dir_mu03_25832_int.tif` is 9,080 × 4,808 cells at 30 m, 8 uint8 bands, nodata 0. Band k (1..8 = N, NE, E, SE, S, SW, W, NW) is the cost of dragging a sledge FROM a cell INTO its neighbour in direction k. It is in flat-ground-metre equivalents: `max(0.5, |0.3 + t| / 0.3) × d`, where t is the signed gradient (+ uphill) and d is 30 m or 42.43 m. I confirmed these semantics in `costsurface/build_drag8.py`, `drag_cost_recipe.md` and section 7a of `data-file-README.md`. They were also checked independently against the DEM (Verification b).
- **Lithology.** `sardinia_lithology_25832.shp`, field `STONE`. In this first version the allowed quarry stones were exactly `limestone/marble`, `metamorphic`, `basalt` and `granite` (the authors' list); all other classes were excluded: schist, acid volcanic, andesite, tuff, dyke, trachyte, other intrusive and none. **Current code:** `stone_rule: hybrid` (section 11): a site quarries its recorded building stone where known, otherwise the nearest of 7 classes (`allowed_stones`: limestone/marble, metamorphic, basalt, granite, acid volcanic, trachyte, andesite); the four-stone list is kept as `stones4`.

### Step 2: Preprocessing (`preprocess.py`, run once, about 15 s)
1. Read the 8 cost bands into one uint8 array (about 350 MB). A band value of 0 means that move is impossible.
2. Rasterize the allowed outcrop polygons onto the same grid. A cell gets a stone code (1 limestone/marble, 2 metamorphic, 3 basalt, 4 granite) if the polygon covers the cell centre (`rasterize_all_touched: false`). Saved as `cache/outcrop_code.tif`. Printed: limestone/marble 2,327,851 cells, metamorphic 1,004,012, basalt 1,626,812, granite 6,759,551, for 11,718,226 seed cells in total.
3. **One multi-source directional Dijkstra.** Every allowed-outcrop cell is a source at cost 0. Stone moves outcrop → site, so the search moves forward: the edge from cell u to its neighbour in direction k costs band k *at u*. For every cell the search records:
   - the least summed cost from any allowed outcrop (`haul_flatm`, flat-metre equivalents),
   - the outcrop cell where that cheapest path starts (giving the quarry x/y and stone type),
   - the real horizontal length of that path in metres (`haul_m`). This is accumulated during relaxation as +30 m per orthogonal move and +42.43 m per diagonal move.

   Implementation: numba with an indexed binary heap (decrease-key, at most one heap entry per cell), using float32 and int32 arrays. Costs are whole numbers, so the float32 sums are exact. Printed: 27,212,159 cells settled in 9.8 s, **peak RSS 1,687 MB**. The model ranks never load the raster.
4. **Sampling at the sites.** Each site point is mapped to its grid cell. If the cell had no finite cost, the code searched up to 20 cells away (`nodata_snap_radius_cells`) for the nearest cell with a finite cost and flagged the site. **No site fell on nodata.** **6 sites were unreachable (cost inf).** All six are on Isola di San Pietro (Carloforte): NID0243400, NID0243500, NID1064500, NID0247000, NID0248700, NID9220200. The island carries only `acid volcanic` and `none` polygons, and an allowed outcrop can't be reached over land. Under `unreachable_policy: local_min_haul` they are kept with a local quarry at the minimum haul, `quarry_stone = local_unlisted` and `haul_flag = unreachable_local`. Setting `exclude` drops them instead. **Current code:** under the hybrid / 7-class rule acid volcanic rock is allowed, so no site is unreachable and the policy acts on no site (ODD Appendix D, D6).
5. Output: `cache/sites_haul.csv`, with UID, x, y, TWR_N, haul_flatm, haul_m, quarry_x, quarry_y, quarry_stone, on_outcrop, plus grid row/col, snapping status and haul_flag. Under the 4-stone rule 3,637 sites sit on an allowed outcrop (haul 0).

### Step 3: The agent-based model (`model.py`, repast4py)
- **Agents.** `Site` and `Builder` are subclasses of `repast4py.core.Agent` and are added to a `repast4py.context.SharedContext` on each MPI rank. Sites are dealt to ranks round-robin (site i goes to rank i mod n). Each Site owns its Builders.
- **Schedule.** `repast4py.schedule.init_schedule_runner` repeats one event every tick, and **one tick = one working day of `hours_per_day` = 8 h**. After each tick the ranks `allreduce` the number of unfinished sites and the runner stops when it reaches 0. There is a safety stop at `max_days` = 20,000.
- **Random numbers.** Every site in run i has its own stream, `numpy.random.default_rng([i, uid_int])`, where `uid_int` is the numeric part of UID (e.g. NID9067800 → 9067800). Results therefore do not depend on the rank count or the order in which sites are processed.
- **Per site, at the start of each run:**
  1. Builders: `B = clamp(round(round(50 + 25·(TWR_N−1)) × U(0.9, 1.1)), 50, 200)`.
  2. Stone needed: `1,350 t × TWR_N`. Blocks are drawn from lognormal(median 450 kg, σ 0.6) clipped to [60, 2,400] kg until the cumulative mass reaches the target (the block that crosses the target is included). Because the mean of a lognormal is above its median, a tower has fewer blocks than Webster's ~3,000.
  3. Crew per block: `ceil(mass / 100 kg)`, i.e. 1 to 24 people.
  4. Trip time (h): `haul_flatm_eff / drag_speed_ms / 3600 + haul_m_eff / return_walk_ms / 3600 + load_unload_h`, with `haul_flatm_eff = max(haul_flatm, min_haul_flatm)` and `haul_m_eff = max(haul_m, min_haul_flatm)`. The first term drags the loaded sledge at `drag_speed_ms` per flat-metre equivalent, the second walks back empty along the same path at `return_walk_ms`, and the third is load/unload (0.25 h). A block's transport man-hours are crew × trip time. This section was first written with a 100 m minimum haul, 0.6 m/s and 1.4 m/s. **Current code:** `min_haul_flatm` = 15 m (v15), `drag_speed_ms` = 0.27 m/s (audited value; ASSUMPTION since v12: a sustained mean below the reported 1 m/s peak, Harris 2016, AAM p. 4; press reports give ~0.6 m/s; 1.0 m/s is the sensitivity MR_P10_v12_drag10) and `return_walk_ms` = 1.39 m/s.
  5. Quarry/dress/build pool: Webster's 2,500 man-days per tower (quarry 500 + dressing 1,300 + walling 700) × TWR_N. First version: every man-day × `hours_per_day` (8 h). **Current code:** v11 converts each stage at its source day length (`v11.webster_day_hours`: quarry 5 h, dress 8 h, build 8 h; section 12.1), i.e. 500 × 5 + 1,300 × 8 + 700 × 8 = 18,500 person-hours per tower.
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
- `quarry_sources.shp`: the distinct quarry cells used, each with STONE, N_SITES (sites served) and MH_SUM.

## 2. Parameters and sources

| Parameter | Value | Source / reasoning |
|---|---|---|
| stone_rule / allowed_stones | hybrid: recorded stone, else the nearest of limestone/marble, metamorphic, basalt, granite, acid volcanic, trachyte, andesite (first version: the four-stone list, now `stones4`) | The authors (sections 1, 11) |
| cost raster μ | 0.3 | drag_cost_recipe.md (sledge friction; an assumption) |
| hours_per_day | 8 | assumption (a standard working day; Webster counts in man-days) |
| builders | 50 + 25·(TWR_N−1), ×U(0.9,1.1), clamp [50, 200] | The authors' spec |
| tonnes_per_tower | 1,350 | Webster 1991, *Antiquity* 65(249): 840–856: ~3,000 blocks/tower × ~450 kg |
| block_median_kg / sigma / clip | 450 / 0.6 / [60, 2,400] | 0.19 m³ × 2,386 kg/m³ ≈ 450 kg (Webster); σ and clip are the modellers' assumptions (roughly Webster's 0.06–1 m³ block range) |
| pull_kg_per_person | 100 | ASSUMPTION (v12 relabel): press reports of the UCL 2016 Stonehenge sledge experiment, ~10 people per ~1 t; the primary (Harris 2016) gives no tonnage |
| drag_speed_ms | 0.27 (first version 0.6) | ASSUMPTION (v12 relabel): a sustained mean below the reported 1 m/s peak (Harris 2016, AAM p. 4); press reports ~0.6 m/s |
| return_walk_ms | 1.39 (first version 1.4) | normal walking speed |
| load_unload_h | 0.25 | the modellers' assumption |
| min_haul_flatm | 15 (v15, 5 Nov 2026; 100 before) | quarry face to the site when the site sits on the outcrop, and the floor of every whole route; Webster's local hauls are ≤ 200 m |
| other_mandays_per_tower | 2,500 | Webster Table 1: ~3,600 man-days per tower, minus ~1,100 for transport (= quarry 500 + dressing 1,300 + walling 700) |
| v11.webster_day_hours | quarry 5, transport 5, dress 8, build 8 | section 12.1 (Erasmus 1965 via Boswinkel 2021; Abrams via Boswinkel 2021) |
| seeds | 1..100 | The authors' spec |

## 3. Verification

**(a) Dijkstra unit tests** (`tests/test_dijkstra.py`, `cache/logs/verify_a.log`):
- 1-D ramp, where uphill moves cost 50 and downhill moves cost 15: west outcrop → east end = 150 (expect 150); east outcrop → west end = 45 (expect 45). A Dijkstra running edges the wrong way round would swap these.
- Two outcrops on the same ramp: the middle cell costs 30 from the east outcrop (expect 30, from col 4), not 100 from the west.
- Diagonal detour around a nodata cell: cost 102 (expect 102), path 102.43 m (expect 102.43), and the nodata cell is unreachable.
- Random 40×35 grid with 3 sources and 10% nodata: all 1,400 finite cells equal an independent plain-Python heapq Dijkstra, and every cell's cost equals a single-source run from its reported origin. **ALL DIJKSTRA TESTS PASSED.**

**(b) Spot-check on 3 real sites** (`tests/verify_hauls.py`, `cache/logs/verify_b.log`). A separate lazy-deletion heapq Dijkstra was run from the reported quarry cell on a raster window padded by 15 km:

| Site | haul_flatm (multi-source) | single-source from quarry | path length vs haul_m |
|---|---|---|---|
| NID1830000 (basalt) | 481 | 481 MATCH | 499.7 m vs 499.7 m |
| NID0459600 (limestone/marble) | 1,826 | 1,826 MATCH | 2,004.3 m vs 2,004.3 m |
| NID1548400 (limestone/marble) | 5,678 | 5,678 MATCH | 6,015.8 m vs 6,015.8 m |

A DEM check recomputes the cost of the same path from `sardinia_dem_GLO30_25832.tif` with the recipe formula; agreement within 0.5% is the expected rounding error of the integer raster, and it was met at all three sites. It confirms the band direction: uphill moves cost more and the floor applies downhill. All three quarry cells carry the allowed stone code. **SPOT CHECK PASSED.** (These are prepared haul inputs on the 4-stone rule, not model outputs.)

**(c) Webster sanity check** (`tests/verify_webster.py`). The test site is NID1501300 (Silius): 1 tower, a 200 m haul (167 flat-m) from metamorphic rock. The test runs the site over several seeds and accepts the model if the total is within 0.5–1.5 × Webster's ~3,600 man-days per single tower and transport is between 100 and 1,100 man-days (Webster: ~1,100). The same comparison is made across all single-tower sites with 150–250 m hauls. Webster's man-days are converted at their source day lengths since v11 (section 12.1). Results are reported separately in the results data.

**(d) Reproducibility** (`tests/test_reproducibility.py --full`, `cache/logs/verify_d.log`):
- 3 sites × seeds 1–3: `-n 1` vs `-n 4` identical at full precision: True.
- `-n 4` rerun identical: True.
- Different seeds give different results: True.
- All sites × seeds 1–5: `-n 8` vs `-n 3` identical: True.
- Seeds 1–5 rerun vs `output/nuraghe_manhours_runs.csv.gz`: identical.
- **REPRODUCIBILITY PASSED.**

**(e) Code review against the spec.** Every item is implemented as specified except the points below.
1. **Random order.** The block queue is the random draw order, fixed for the run, and is not reshuffled every day. The blocks are i.i.d., so the draw order is already a random order. With first-fit, skipped heavy blocks keep their place in the queue.
2. **Crew reuse within a day.** The spec says each day builders form crews. I let crews re-form whenever a crew returns, within the same day. Without this, a short haul would make one trip per crew per day and the site would sit idle for most of the day.
3. **First-fit.** If a waiting block's full crew isn't free, the next block that does fit is dragged. A block is never dragged with a partial crew.
4. **Return walk.** The return walk uses `haul_m_eff` (the minimum haul `min_haul_flatm` applies to both legs; 100 m in the first version, 15 m since v15), following the spec's definition of `haul_m_eff`.
5. **Final day.** Man-hours count to the completion hour on the last day, and `days` counts that last day as a whole day.
6. **Idle column.** `mh_other` is the pool total. Idle time is a separate column (`mh_idle`) and is included in `mh_total`.
7. **Builder state.** Builder agents are real repast4py agents, but their state (the hour each builder is next free) lives in the Site's numpy array, which the numba kernel updates. Running the scheduling in Python agent by agent would be far slower. No simplification was needed for speed: 100 runs take 1 min 50 s on 8 ranks.
8. **Unreachable sites.** Under the 4-stone rule the 6 San Pietro sites use a local, non-listed stone at the minimum haul. This is configurable and flagged. Under the hybrid / 7-class rule no site is unreachable.
9. **Overlapping polygons.** If allowed polygons overlap, the one drawn last sets the stone code. A cell is a source either way.

## 4. Results

Results are reported separately in the results data.

## 5. Limitations
- **Modern lithology map.** It is a present-day geological map, so small or quarried-out outcrops may be missing or added. An outcrop that covers no 30 m cell centre is not seeded.
- **Nearest permitted outcrop ≠ the real quarry.** The model picks the cheapest-to-drag allowed outcrop. Real builders may have used a specific stone, an older quarry, or rubble from the site itself. Sites that sit on an outcrop get the minimum haul (`min_haul_flatm`).
- **The cost surface** comes from a surface model (trees, buildings) with an assumed μ = 0.3, rounded to whole flat-metres. It has no ramps, tracks, rivers or levering on steep slopes.
- **Constant labour rates.** Pull per person, speeds, load time and the 2,500 man-days/tower for quarrying and building are fixed. There is no fatigue, seasonality, food supply or skill difference. Webster's figures are themselves estimates.
- **Tower count.** `TWR_N` is assumed for 3,764 sites (`TWR_FILL = 1`). Mass scales linearly with towers, with no allowance for bastions, walls or villages.
- **No chronology (sections 1-8).** Every site is built independently with its own workforce, with no shared labour, competition for quarries, or phasing. The island total is a sum of labour, not a duration. The alliance engine (section 9) and the headline model add seasons, start cohorts and phasing.

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
   - **30 Oct (b) fix, BUGFIX_REPORT B22 (the authors' N1).** Before, c_max was n_coop whenever n_coop > 0, so a bigger household was ignored and some blocks were cut into more pieces than needed. This can change a site-run only when 0 < n_coop < max hh_n ≤ household_size (5), which with ≥ 50 builders can happen only in the partial-cooperation scenarios (`low`, `mixed`, `mostly`) at site-runs with fewer than 5 cooperators. `none` (n_coop = 0), `full`, `high`, `patchwork` and every literature run (p_coop = 0 or 1 at every site) are unchanged by construction.
   - **n_splits** counts the cuts (k − 1 per block).
   - Each cut adds `split_cost_mh` = 1.0 man-hour to the pool.
   - **Lifting is per piece (30 Oct fix, BUGFIX_REPORT B14).** Where lifting is charged per block (S4a lever, S4c internal stair), every piece is lifted separately at the full per-block rate (specified by the authors: the conservative upper end). `n_blocks` reports the pieces; `n_splits` and the cut cost are separate. With full cooperation (every literature run) no block splits, so this changes nothing there.
6. **Scheduling.** At every event the earliest waiting block (in queue order) that any free crew can move is assigned:
   - first choice: the first free household (in household order) big enough for it,
   - otherwise: free cooperators.

   This keeps cooperators for the heavy blocks. It is first-fit and deterministic. With no households it is exactly the baseline kernel.
7. **Inter-site help (`high`).**
   - When a site finishes, all cooperators working there (its own and any helpers) walk to the nearest unfinished site within `help_radius_m` = 10,000 m, measured in a straight line (ties broken by site index).
   - The walk costs n × distance / `help_walk_ms` (1.39 m/s; 1.4 m/s in the first version) in man-hours, charged to the helped site. The helpers join its cooperator pool at the start of the next working day.
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
2. **Split hand-check (`none`, seed 1).** The RNG was replayed by hand in plain Python for two sites (NID9067800, B = 50, largest household 5, i.e. 500 kg; NID0168700, B = 71): the hand counts of splits and pieces equal the model's: MATCH.
3. **Rank independence.** 300 spatially clustered sites (within 11.4 km of the island median), seeds 1–8, `-n 1` vs `-n 8`:
   - `high`: identical, True. Under `-n 8` the cap of 2 makes 2 ranks do the work, but the seeds land on different ranks than with `-n 1`.
   - `patchwork`: identical, True.
4. **Monotonicity in p_coop.** The island totals of `none`, `low`, `mixed`, `mostly` and `full` were compared to check whether cost is monotone in p_coop; the outcome is part of the results.
5. **Code review against the brief.** Deviations and interpretations:
   1. n_splits counts cuts (k − 1), not split blocks.
   2. Helpers arrive at the start of the next working day; their walk is charged but does not take up working time on the day they leave.
   3. When a block could go to several free households, it goes to the first in household order, not the smallest that fits.
   4. The split rule uses "crew > largest available crew". This equals the brief's "crew > total cooperators" whenever cooperators exist; when there are none, the largest household is the limit.
   5. Summary CSV columns are lowercase (n_split_mean, help_mean) to match the existing columns; the shapefile uses SPL_MEAN and HLP_MEAN as asked, plus COOP_MEAN.
   6. `high` runs seed-parallel on at most 2 ranks for memory reasons.
   7. The files in `output/` (baseline) were written by the pre-scenario code. They equal `full` in every column, and a baseline rerun under the new code adds the new columns.

### 7.4 Results

Results are reported separately in the results data.

---

## 8. Literature-based chaîne opératoire / logistics scenarios (added 28 Oct 2026)

The scenarios come from `literature/SCENARIOS_PLAN.md`, using the two reviews in `literature/`:
- `general_energetics_logistics.md`, cited below as **GEN**,
- `nuraghe_specific.md`, cited below as **NUR**.

Line numbers refer to those files. Every number sits in `config.yaml → lit_scenarios` with its source line. A value marked **FREE** has no empirical basis in either review: it is a stated assumption, and its effect is the point of the scenario.

Run with `mpirun -n 8 python model.py config.yaml --lit all` (or `--lit NAME`). Outputs go to `output/scenarios_lit/`. All scenarios use full cooperation, with 100 seeds (1..100).

### 8.1 The stage-explicit baseline (`webster`)
- The old single pool of 2,500 man-days per tower is split into Webster's 1991 Table 1 stages for a single tower (NUR 181): quarrying 500, dressing 1,300 and building 700 man-days. Transport (1,100 man-days in Webster) stays simulated by the ABM. **Current code:** the man-days are converted at their source day lengths (quarry 5 h, dress and build 8 h; section 12.1).
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
| S2b_fine | complex sites (TWR_N ≥ 2): extra cost = facing volume × (131.2 − 40.95) ph/m³ (audited midpoints; the first version used 131.5 − 40.85; v11 citation fix: these are Boswinkel's TOTAL all-stage costs per m³ of conglomerate facades and cyclopean walls, Boswinkel 2021: 144, Table 8.3, NOT dressing rates; the difference is the extra total cost of facade masonry; Boswinkel's dressing rates proper, 57–62 ph/m³, pp. 120–121, Table 7.8, are variant C3_dress) | GEN 57, 199 (Table 8.3 facade and cyclopean midpoints); isodomic masonry, NUR 61. Facing = outer face of one tower, π(R0 + R1)·√(H² + (R0 − R1)²), × 0.5 m × TWR_N: 420.5 m² per tower with the audited geometry (14 m, 12 → 6.8 m; 475.2 m² with the first 15 m, 12 → 8 m); the 0.5 m is **FREE** |
| S3a / S3b / S3c / S3d | μ = 0.1 tallowed rails / 0.05 greased rails / 0.38 dry ground / 0.5 rough ground. Cost raster rebuilt from the DEM per μ; crew = ceil(m·μ / 30 kg-force) | GEN 64–65, 201; 30 kgf = 300 N per person, GEN 202 (30 / 0.3 = 100 kg per person in the baseline). v11 note: 300 N is a PEAK, short-burst draught effort (Cotterell & Kamminga 1990: 219, de Haan 2009, via Boswinkel 2021: 47 n. 25, 52, 111); a sustained effort is ~125 N (Boswinkel 2021: 52): sensitivity MR_P10_v11_pull125 |
| S3e_oxen | an ox team per block: 2 men (drover + helper), with yokes as needed at 520 N per ox in v10 (v11: 515 N, see section 12) and 95/80/63% efficiency for 1/2/3 pairs, at 0.75 m/s. Oxen-hours are reported separately (not man-hours). Surface μ stays 0.3 | GEN 69, 203 (v11 citation fix: Boswinkel 2021: 52 prints 491–549 N, but its footnote 37 computes 350 × 14% × 9.81 ≈ 481 N and 400 × 14% × 9.81 ≈ 549 N; 491 is a misprint, midpoint 515 N); LBA only, since cattle may be rare before the LBA (NUR 54). Return speed 0.75 and 63% for more than 3 pairs are **FREE** |
| S4a_lever | lifting = Σ pieces × courses climbed × 0.37 ph (pieces = lifted pieces after any split, 30 Oct) | GEN 77, 204. Geometry **FREE**: `lit_scenarios.geometry` = 14 m tall, 0.9 m courses (15 of 0.9 m and a top course of 0.5 m), truncated cone 12 → 6.8 m (first version: 15 m, 17 courses, 12 → 8 m). Courses climbed are weighted by the stone share of each course (`lit.cone_course_weights`): 2.179 ph per piece with the audited geometry (ODD 7.2) |
| S4b_ramp | lifting = single-sided earth ramp to the tower height at 20%, 3 m wide: volume 0.5 × (H / 0.2) × H × 3 m; labour (dig 4.2 ph/m³ + compaction ρ/1,000 kg/ph + carrying 50 kg loads × 0.000444 h/m × 50 m) × 2 (build + remove). With H = 14 m (audited): 1,470 m³ and about 19,141 ph per tower (first version, H = 15 m: 1,687.5 m³, 21,973 ph) | GEN 68, 78, 205. Width, earth density 1,600 kg/m³ and carrying distance 50 m are **FREE** |
| S4c_internal_stair | lifting = blocks above the ground course × 0.37 × (1 m / 0.9 m) (blocks = lifted pieces after any split, 30 Oct) | Laner's internal stair, NUR 79–81. The "last metre only" rule is **FREE** |
| S5a_onsite | haul = the minimum haul (`min_haul_flatm`: 15 m since v15, 100 m before) everywhere | NUR 27, 45–46, 195–196 |
| S5b_any_buildstone | quarries may be any BUILDSTONE class (all 11 non-"none" classes) | shows what the authors' four-stone rule costs |
| S5c_complex_far | TWR_N ≥ 3: the cheapest allowed outcrop cell ≥ 3 km away (straight line, measured cell centre to site) | S'Urachi about 3 km (NUR 49, 198); "some km" (NUR 50, 199). The TWR_N ≥ 3 mapping is **FREE** |
| S6_density | block volume held, so mass × ρ/2,386 (basalt 3,000, granite 2,700, limestone/marble 2,600, metamorphic 2,750 kg/m³; the first version used basalt 2,950 and granite 2,650). Quarrying and dressing × hardness: basalt and granite 2, others 1. Other quarry classes (acid volcanic, andesite, schist, tuff, trachyte, other intrusive) keep 2,386 kg/m³ and hardness 1 (`lit.mass_factor`; ODD Appendix D, D13) | Turner's critique of Webster (GEN 136, 212). Densities and multipliers are **FREE** (standard values; GEN 212 gives basalt ~2.9–3.0 and limestone ~2.5) |
| S7_webster_classes | Webster's class totals in place of "× TWR_N": single 1,350 t, 500/1,300/700 md; multi-tower 3,100 t, 1,200/3,000/1,600; bastioned 6,700 t, 2,500/6,400/3,500 | NUR 156–158, 181–183. The mapping TWR_N 1 / 2–3 / ≥ 4 is **FREE** |
| S8_learning | tower i (counting from 0) costs 0.85^i in quarrying, dressing and building; lifting is not scaled | **FREE** (GEN 91: no archaeological learning rate) |
| LOW | S1a + S2a + S3a + S4c + S5b (any buildstone at μ 0.1) | see deviation 6 |
| HIGH | S1b_high + S2b + S3d + S4b + S6 | |

**Duration.** Each site's mean man-days is divided by workforce × days per year:
- Workforces: a household of 6 (NUR 205), Trump's 15 (NUR 130, 206), and a canton of 500 (GEN 26).
- Calendars: 40 or 90 days (NUR 185), or 255 days (GEN 36, 206: the midpoint of 220–290).
- The "community" row uses the ABM's own 50–200 builders and simulated working days.
- Fixed-workforce rows are man-days ÷ (workers × days) and ignore crew-size limits: a household of 6 cannot itself drag a 2.4 t block that needs 24 people. For comparison, Webster's own example is a team of 10 × 40 days ≈ 10 years for one tower (NUR 186).

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
   - Prepared hauls (inputs): straight-line distance median 3,008 m; haul_m median 3,100 m (max 9,139); haul_flatm median 2,834 against a baseline median of 0 for these sites.
   - 3 forward single-source checks: all MATCH.
4. **Transport technology.**
   - S3 changes the crew per block (`pull = 30/μ` kg per person) and the drag cost. A lower μ makes slopes relatively costlier, so haul_flatm rises (mean 687 at μ 0.3, 778 at μ 0.1, 960 at μ 0.05), while crews shrink by μ/0.3.
   - S3e gives every block a 2-man crew, with the number of yokes needed to overcome m·g·0.3.
5. **S6 density** scales the block median, the clip limits and the site's total mass by ρ/2,386, using the stone type of the site's quarry.
6. **Stage costs** (`lit.py: stage_hours`) are deterministic per site, except lifting under S4a and S4c, which uses the site's simulated block count. They feed the ABM pool. Transport, days and idle time come from the ABM as before.

### 8.4 Verification (`tests/verify_lit.py`, `cache/logs/verify_lit.log`)
1. **`webster` == `full`.** All 716,700 site-runs (7,167 sites × 100 seeds); all 15 shared columns identical at full precision: True. Island totals identical for all 100 seeds: True. Quarry + dress + build + lift == pool in every row: True.
2. **Raster rebuild.** μ = 0.3 rebuild against the delivered `sardinia_drag_cost_8dir_mu03_25832_int.tif`: 0 mismatching cells of 349,253,120 (8 bands): IDENTICAL.
3. **Ramp formula.** Boswinkel's 6 m and 9 m ramp volumes (354 and 796 m³) imply a width of 3.93 m at 20%. The formula gives 879 ph for a 3 m ramp at our 3.0 m width (below his range) and 1,152 ph at his implied width; Boswinkel gives 971–1,208 ph, so the formula is IN RANGE.
4. **Calibration.** NID1501300 (1 tower, 200 m haul) is compared with Webster's single tower stage by stage (quarry, transport, dressing, walling, lifting), as in section 3 (c). Results are reported separately in the results data.
5. **Rank independence.** 300 clustered sites × seeds 1–4, `-n 1` vs `-n 8`, all columns at full precision: S3e_oxen True, S6_density True, HIGH True.
- **Result: LIT VERIFICATION PASSED.** S5c's own checks are in `cache/logs/lit_haul_far.log`.

### 8.5 Deviations from the plan (fixed after reading the sources)
1. **Stage man-days.** The plan's 504 / 1,296 / 684 (shares × 3,600) sum to 2,484. Webster's Table 1 values 500 / 1,300 / 700 (NUR 181) sum to the model's 2,500 and were used, which keeps `webster` == `full` exactly.
2. **Dressing rate.** Webster's 0.40 m³/man-day would give 1,415 man-days for 565.8 m³, but Table 1 has 1,300 (NUR 156, 178, 181). The Table 1 totals are kept as the baseline. Per-m³ rates are used only for the replacement stages.
3. **S2b.** The 96–167 ph/m³ is Boswinkel's *all-stage* cost of facade masonry (GEN 57, 199), not a dressing rate. Only the increment over cyclopean masonry is added (131.5 − 40.85 = 90.65 ph/m³, both Table 8.3 midpoints; audited values: 131.2 − 40.95 = 90.25 ph/m³), to avoid double counting quarrying, transport and setting.
4. **Calendar.** The midpoint of 220–290 days is 255, not 250.
5. **Oxen.** GEN 203 also gives 95% efficiency for a single pair, which the plan omitted, and it is used. More than 3 pairs keep 63% (Boswinkel caps the loss at 36%; **FREE**). Teams return at ox pace (**FREE**).
6. **LOW used S4c instead of S4a.** Levering (S4a: 0.37 ph × courses climbed × pieces) costs more per tower than Webster's lifting share (2,800 ph). A lower bound should take the cheapest lifting option, so LOW uses the internal stair (S4c).
7. **S7.** Webster's tonnages are used directly (3,100 and 6,700 t; NUR 157–158), rather than scaling 1,350 t by the block ratio (which would give 3,150 and 6,750 t).
8. **Ramp check.** The plan's "3 m ramp ≈ 1,000 ph" is matched only at Boswinkel's implied 3.93 m width. Our tower ramp keeps the plan's 3 m width.
9. **Household duration.** The "household of 6" is the whole household (NUR 205 gives 5–6 people, of whom about 1 in 5 is an adult man, NUR 207). The household row is therefore an optimistic (short) duration.
10. **S5c distance.** The 3 km is measured from the site point to the quarry cell centre, so the nearest accepted source is 2,985 m away.
11. **Not modelled.** Hauling blocks up the S4b ramp. Carrying stone up the internal stair in S4c (only the last metre is levered). Oxen availability, fodder and the ploughing season (GEN 88).

### 8.6 Results

Results are reported separately in the results data.

---

## 9. Adaptive alliances along the supply chain (added 28 Oct 2026)

Specified by the authors: agents learn and interact; they search for the best way to build a nuraghe and may ask other agents to cooperate. Everyone at the same nuragic site already cooperates; cooperation with other areas needs an alliance or a request (for example, neighbours quarry and drag the stones part of the way and the owners take over the last leg). Alliances and cooperation are sought along the whole supply chain, trust grows with reciprocity, and the earlier outputs stay unchanged.

Code: `alliance.py` (model), `report_alliance.py` (outputs), `tools/kbest_quarries.py` (quarry faces and routes), `tools/alliance_emergence.py` (emergence statistics), config block `alliance:`. Run with `mpirun -n 8 python model.py config.yaml --alliance all`, then `--alliance A0_verify` and `--alliance sensitivity`. Outputs go to `output/scenarios_alliance/`.

### 9.1 Definitions
- **Agent = a community.** There is one community per site, a repast4py `core.Agent` in a `SharedContext`.
  - Inside a community everyone cooperates, exactly as in `webster`/`full`: the same builders N_i (50 + 25(T−1), ±10%), the same block draws, crews ceil(m/100 kg) and trip times, and Webster's stages per tower (quarry 2,500 ph = 500 md × 5 h since v11, dress 10,400, walling 2,800 and lifting 2,800 ph; the first version had quarry 4,000 ph at 8 h; ODD Appendix D, D1).
- **Time.** One repast4py tick = one building season of `season_days` = 90 working days (NUR 185: Renfrew's 90 days); one season stands for one year.
  - A share `start_rate` = 1/450 of all sites starts each season, in a random order per seed (FREE). That spreads the starts over 450 seasons, matching the roughly 500 years of nuraghe building (Ialongo 2018, NUR 116).
  - Towers are built one after another (phasing, NUR 99–108). A community that has finished stays active as a helper and supplier.
- **Supply chain.** Each tower is a chain of stage tasks: quarry → dress → [track] → transport (relay leg 1 → leg 2) → build+lift. Dressing is placed at the quarry, following the plan's order (GEN 58 discusses dressing at the quarry versus at the site).
- **Actions at the start of each tower**, chosen by the community:
  - (a) the quarry face: one of the k = 5 cheapest distinct faces;
  - (b) for quarrying, dressing and build+lift, do it itself or ask a neighbour within R = 10 km (FREE);
  - (c) a transport relay: a neighbour (asked from the ordinary candidate list, as for the other stages) drags stone to a hand-off cell at f ∈ {0.25, 0.5, 0.75} of the route's drag cost, and the requester drags the last leg. An earlier rule filtered the leg-1 candidates to neighbours nearer the quarry than the requester; that filter was removed (specified by the authors, 5 Nov 2026). The hand-off cell and the 300 flat-m minimum for relays use the μ 0.3 cost of the route; under the per-site technique rules the legs are then costed at the site's own friction (μ 0.38 or 0.1) (ODD Appendix D, D15);
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
  - Every task's labour (plus the helpers' walk, B_j × distance / `return_walk_ms`, 1.39 m/s, once per task; 1.4 m/s in the first version) is charged to the performer and counts toward the man-hours of the nuraghe it was spent on.
  - A site's `mh_total` = all labour on it, from anyone: `mh_own` + `mh_received`.
  - `mh_given` = the community's labour on other nuraghi.
- **Where cooperation can save labour.** Three mechanisms, each with its own switch:
  1. **Specialisation (learning curve).** On quarrying, dressing and building, unit cost = c_s (1 + Q_js)^(log2 b), Wright 1936, with b = 0.85 per doubling (FREE; GEN 91). **Current code:** lift (all lift rules) is priced at the undiscounted rate: neither skill nor the S8 learning factor applies to it .
     - Q_js = the community's cumulative output in stage s, in tower-equivalents.
     - Own work always counts (learning by doing, in every scenario). Help given counts only with `specialisation` on (A3, A5).
  2. **Shared trackway.** A trackway uses μ = 0.1 (tallowed rails, GEN 65) on the route cells, and is permanent.
     - It costs `track_cost_mh_per_m` = 2 man-hours per metre (FREE; scanned 0.5 / 2 / 5), split equally between the builder and its allies within R.
     - On track cells the owner and its current allies use the μ 0.1 raster (`cache/cost_mu/drag_cost_8dir_mu0.1_int.tif`).
     - Per tower the crew is sized for either μ 0.3 or μ 0.1, whichever needs fewer man-hours (equation in 9.2).
  3. **Shared quarry face.** Opening a fresh face costs `setup_mh` = 200 man-hours (FREE). Reusing one's own face is free; reusing an ally's face is free only with `shared_quarry` on (A5).
- **Learning rule.** Each action dimension (quarry face, ask for quarrying / dressing / build, relay fraction, track) has its own value table, chosen ε-greedily (ε = 0.1, α = 0.5).
  - The reward after each tower is r = −(own man-hours on that tower ÷ its tonnes).
  - The quarry-face values start from a model-based estimate (each community can see the cost of its own faces). The other values start at 0 and ties are broken at random, so asking and not asking are equally likely on the first tower; an option tried once gets a negative value, so the untried one is preferred next (ODD Appendix D, D3).
  - **Social learning:** with probability p_imit = 0.3 per tower, the community copies the last strategy of the neighbour within R with the lowest cost per tonne, if that is lower than its own. Faces are copied only if the neighbour's face region is also among its own faces.
  - **Near-site rule (5 Nov 2026; `quarry.near_site_fixed_face_m`, 1,000 m in the model's configuration, absent / 0 = off).** A site whose dry-ground (μ 0.38) route to its cheapest face (face 0, haul table `haul/sites_haul_mu0.38.csv`, `haul_m`) is at most this length always quarries from face 0: for it the face is never explored (no ε draw), never chosen by its value table and never copied by imitation; the draws are skipped, not drawn and discarded. Its other dimensions, and the imitation draw itself, are unchanged. Sites over the threshold keep the choice among their k = 5 faces (and a sea face). The run signature includes the rule only when it is on (`change notes, git history`).
  - **Minimum haul (5 Nov 2026; `transport.min_haul_flatm`).** The minimum haul is 15 m (flat-equivalent metres; it was 100 m) for a site on its outcrop and as the floor of every whole route (drag and walk-back legs alike; relay legs have no minimum). It is a config value only: every floor in the code reads this key, and the sea tables, the only prepared tables that apply it, are rebuilt per config. Rows with their own value (the 200 / 210 / 300 m sensitivity configs) keep it.
  - **Rules and fixes of 5 Nov 2026.** The on-outcrop test uses the stone set a site actually quarries (recorded set if reachable, else the allowed fallback set). Four rules of addendum 4 sit behind flags in a top-level `add4:` config block: L2 `bedrock_everywhere` (every site quarries at the bedrock rate, joints_low 11.1 ph/m³ × hardness, instead of scree off its outcrop) and L3 `load_per_tonne` (loading 1.2 ph per tonne instead of 0.25 h per crew member per trip) are ON by default; L1 `rails_cost_choice` and L4 `sea_priced_as_charged` are OFF. Reporting adds the island-wide 95th percentile of site finish seasons (`island_years_p95`) and spread statistics across seeds (`_sd _p5 _p95`, `island_by_seed.csv`). Fixes: D3 (a stage with no work creates no help request, walk, trust change or skill credit), D6 (in join mode each party is priced at its own skill), D11 (the site's stone is the class of the face it hauls from). The run signature hashes `CODE_VERSION` and the effective add4 settings. The configs are in `config/scenarios/`. Fix of 9 Nov 2026: L2 and L3 apply to the season-based community engine only; the day-based engine-B rows of `model.py --lit` (REALISTIC, REALISTIC_oxen) keep their own quarry rule (joints_low on the outcrop, else scree) and `load_unload_h`.
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
   - Faces per site in the hybrid cache used by the queue (`cache/alliance/kbest.npz`): 7,165 sites have 5 faces and 2 have 1 (35,827 routes); none has 0 (ODD Appendix D, D4). Under the 4-stone rule 6 San Pietro sites had 0 faces and used a local quarry, as in the baseline.
2. **Labour and time.**
   - The capacity model rests on the day kernel's builders having no idle time in the `webster` runs (checked; A0_verify, 9.3). A tower's labour is therefore Σ_b c_b τ (transport) + the stage pool.
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
- **k-best search.** Face-0 cost equals the multi-source haul_flatm at every reachable site (ALL EQUAL). Face-0 path length differs from haul_m at a few sites because of equal-cost ties; there the model keeps the baseline length. The per-move costs sum to the route cost for every route. (Prepared inputs, 4-stone rule.)
- (1) A0_verify vs webster: all 716,700 site-runs (seeds 1-100) agree up to floating-point summation order (webster's mh_total = builders × elapsed hours from the daily kernel, A0's = sum of stage labour; idle = 0 in both).
- (2) trust toy (3 communities): accept raises trust: OK; refusal after help lowers trust: OK; defector refusing after help loses trust: OK; no penalty w/o debt: OK; acceptance logistic: OK; alliance = mutual threshold: OK  [trust0 0.5, +0.1, -0.2, accept p at trust0 and 5 km = 0.500]
- (3) relay additivity over all (route, fraction) pairs: C1 + C2 = C exactly (integers); trip and labour of leg 1 + leg 2 equal the single trip up to floating-point rounding -> OK
- (4) rank independence, A5_full_freerider, 300 clustered sites x seeds 1-4: -n 1 vs -n 8 identical (sites, pairs, strategies; full precision): True
- ALLIANCE VERIFICATION PASSED

### 9.4 Results

Results are reported separately in the results data.

### 9.5 What emerged

The emergence statistics (`tools/alliance_emergence.py`: share of towers asking per stage, relays, imitation, specialisation of suppliers, skill multipliers, alliances and their size, free-rider statistics) are written to `cache/logs/alliance_emergence.log`. Results are reported separately in the results data.

### 9.6 Sensitivity (method)
Base A5_full; full factorial over R ∈ {5, 10, 20} km, b ∈ {0.85, 0.95, 1.0} (1.0 = no learning) and track cost ∈ {0.5, 2, 5} man-hours per metre (27 cells); 10 seeds per cell (seeds 1–10; `alliance.sensitivity` in `config.yaml`). Output: `output/scenarios_alliance/sensitivity/sensitivity.csv`; "% vs A0" is relative to the 100-seed A0_alone mean. Results are reported separately in the results data.

### 9.7 Self-review against the spec: deviations and interpretations
1. **Capacity model.** Inside the alliance module the daily crew-by-crew kernel is replaced by a stage-task capacity model, in which each community spends N·h man-hours a day on its tasks. Labour per tower is the same as `webster` (Σ crew × trip + Webster stages; verification 1). This is valid because the builders of the `webster` day kernel are never idle. Durations follow from the capacity, with the delivered-stone cap generalised to the whole chain.
2. **Chain order.** Dressing is a stage at the quarry, before transport, following the spec's order quarry → dress → transport → lift/build. Webster's build stage and lifting are one task "build" (split 50/50 in the outputs as `mh_build` / `mh_lift`). **Current code:** the task stays one, but its labour is priced in two parts: build (discounted by skill / S8 learning) and lift (undiscounted), and each part is booked to its own account.
3. **Learning curves** apply to the craft stages (quarry, dress, build); never to lift. Transport cost stays physical (crews × trips). Own work builds skill in every scenario, as the spec's learning by doing in A0. Help given builds the helper's skill only with specialisation (A3, A5). Skill is updated when a task is created.
4. **A0 includes social learning of the quarry choice** (imitation is information, not labour). Quarry-face values start from each community's own cost estimate.
5. **Trust is directional.** An alliance needs mutual trust ≥ 0.7. Candidates are ordered by skill (with specialisation), then by the requester's trust, then by distance; at most 3 are asked.
6. **Trackways** follow the chosen route without re-routing and are permanent. Labour is split equally between the builder and its allies within R. Access is for the owner and its current allies. Transport waits only for the builder's share. The crew-sizing approximation off and on the track is described in 9.2.
   **Track access rule (30 Oct, the authors' NEW-2; documentation only, BUGFIX_REPORT B17).** A track's cells are registered to their owner when the track tasks are *created* (at the start of the tower), not when they finish (`alliance.py`, `track_owner[c] = i` in `start_tower`). So (a) the owner's own transport waits only for the owner's share of the track task, not for the allies' shares; (b) any community allied with the owner at the time it plans a transport may use the track at the discounted cost before all of its track tasks have finished, possibly in the same season; and (c) `track_use` (the per-cell use counter) is incremented when a transport task is created, not when it runs. The track labour itself is always charged in full; only the timing of access is early. MOST_REALISTIC has no trackways (rails are priced by its tech rules).
7. **Relays** need routes costing at least 300 flat-m. Load/unload is split half per leg, and there is no extra cost at the hand-off.
8. **Helpers** walk with their whole workforce, once per task.
9. **Daily order.** Tasks are worked in chain-stage order, then by age, not own-first.
10. **YEARS** = finish season − start season + 1, with one season of 90 days per year. The island's completion follows from `start_rate` (1/450 of the sites start each season) and the build times.
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
- transport = relay leg 1 and transport help, plus trackway labour (track is folded into transport because it is transport infrastructure);
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
- The recomputed A5_full file matches the project team's file in ROLE, ROLE_CONS and HELP_FREQ for all 7,167 communities; GV_* agree up to rounding.

**Cross-scenario output:** `output/scenarios_alliance/network_comparison.csv`, one row per scenario × layer. Runtime: 3 min 35 s with 6 worker processes.

**Results.** Results are reported separately in the results data.

### 9.9 Where the savings are (added 28 Oct 2026, the authors' request)
`tools/alliance_savings.py` (`cache/logs/alliance_savings.log`) writes three files:
- `savings_by_stage.csv`: island man-hours by stage (mean over seeds) and the change against A0_alone, in man-hours and as % of the A0 total. Stage sums match the totals up to rounding.
- `time_by_scenario.csv`: median working days per tower by TWR_N over site-runs, island completion, and days per tower for helped vs unhelped site-runs.
- `scenario_matrix.csv`: pairwise row-vs-column % differences in island man-hours and median days per tower, and the difference in island seasons.

Results are reported separately in the results data.

### 9.10 Which scenarios build fastest, and why (added 28 Oct 2026, the authors' request)
`tools/fastest.py` (`cache/logs/fastest.log`) puts every scenario on one time metric: the median over sites of each site's mean working days from start to completion with the model's own workforce. For the alliance family these are the working days between a site's start and completion; 90-day seasons count only their working days, so the metric is the same.

The labour metric is island man-hours. Labour is decomposed by stage per family (`output/fastest_stage_decomposition.csv`):
- **baseline and cooperation:** the pool is split with Webster's Table 1 shares, which is exact for 2,500 man-days per tower; any excess is splits; walk = total − transport − pool − idle;
- **literature:** the stage columns of the runs files;
- **alliance:** the stage columns.

Days here are medians of per-site means, so they can differ slightly from the per-site-run medians of 9.9.

The ranking table (rank, family, scenario, days for 1 / 2 / 3 towers, time saved, labour saved, effective workers / own builders) is written to the output files. "Effective workers" = man-hours ÷ (days × 8) for the median single tower: above the community's own builders it means more hands (help); equal means the same hands doing less work. Results are reported separately in the results data.
**Combined effects** (`output/fastest_combined_effects.csv`): for each combination scenario (LOW = S1a+S2a+S3a+S4c+S5b and HIGH = S1b_high+S2b+S3d+S4b+S6 against `webster`; A5_full = A3+A4 against A2_trust), the combined change is compared with the sum and the product of the single-axis changes, for island man-hours and median days of a single tower. Results are reported separately in the results data.

**Scenario key.** `tools/scenario_guide.py` writes `output/scenario_guide.csv` (38 rows: family, code, readable name, one-sentence description, sources, parameters, FREE), which is Appendix A of the report.

### 9.11 Deviations in the network, savings and fastest analyses
1. **Edges.** `edges.shp` and `network.graphml` keep only links with FREQ ≥ 0.05; the full list of links per layer is in `edges.csv.gz` (written in full, `edges.shp` was too large).
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
  - For seed 1, the new help logs and alliance seasons reproduce a Nurnet collaborator's files exactly (identical keys and alliance rows; man-hours up to rounding).
- **Refusal rate per layer** (`network_comparison.csv`, share of requests refused per stage layer and in all). Results are reported separately in the results data.
- **Relationship census** (`tools/census.py`; a Nurnet collaborator's definitions; population 519,638 pairs ≤ 10 km).
  - Recomputed for seeds 1–10, it equals a Nurnet collaborator's `relationship_census.csv` in every cell (max difference 0).
  - The 100-seed version is `output/census/relationship_census_v4_seeds1-100.csv`. a Nurnet collaborator's census uses seeds 1–10; the rest of the report uses 1–100.
- **Formation** (`tools/formation.py`, `output/formation_v4/`).
  - a Nurnet collaborator's "ever-allied pairs" (allied at any time) differ from the alliance tables' count (allied at the end of a run). Results are reported separately in the results data.
- **Connected help networks** (`tools/components.py`): connected components of size ≥ 2 of the any-help graph.
  - Seed 1 equals a Nurnet collaborator's `seed-1 components file` (6 rows identical).
  - A connected help network is not an alliance. Components are reported up to season 200 and at the end of the run (largest network, share of sites, number of networks). Results are reported separately in the results data.

- **Master comparison** (`tools/master_comparison.py`, `output/master_comparison.csv`): every family on the common baseline webster = full (seeds 1–100), with a parameter-base column and a `base_differs` flag.
  - Alliance rows also give % vs their own A0.
  - a Nurnet collaborator's GPU drag × crew grid (`output/crew/crew_drag_grid_gpu.csv`, 1,000 seeds per cell) is a separate sensitivity block.
  - The GPU grid was validated against the CPU baseline (`full`, crew ×1 at the then drag speed of 0.6 m/s). Results are reported separately in the results data.
- **Sensitivity** (a Nurnet collaborator's files in `output/sensitivity/`):
  - The cooperation Morris screen (`morris_cooperation_gpu.csv`) is part of the results data.
  - Pending: the cooperation and alliance Sobol analyses, and the second Morris screen.

### 9.13 Fixes of 30 October 2026 (the authors' NEW-1 and the sea payload; BUGFIX_REPORT B14-B21)
- **Lift per piece in the alliance tech rules (MOST_REALISTIC family).** Blocks split to fit the work party are lifted as pieces: the per-site stage hours use the site's piece count (lever/stair lift is linear in it), and the per-tower piece counts (`tower_nblk`) are used for the S9 hoist labour and the join-mode hands cap. Non-tech alliance scenarios never split, so their stages are unchanged.
- **Sea payload split in the alliance model.** As in the stand-alone S9 model (model.py), a block carried by boat may not exceed the craft payload (`sea.payload_kg` = 2,000 kg, Hazell & Fitzpatrick 2006). When a tower's chosen quarry face is a sea face, its heavier blocks are cut into the fewest equal pieces that fit both the craft and the crew; the pieces set the crews of every leg, the hoist (per piece), the cut cost (`split_cost_mh` per cut, on the quarry task) and, for lever/stair sites, the lift of the extra pieces. Land faces keep the land split. The delivered non-tech sea runs (A1..A5 `_sea`, pre-network `_sea`) were not rerun after this fix.
- **Join hands cap.** With pieces the cap counts pieces instead of blocks (build: 6 hands × pieces per course; quarry/dress: 4 / 2 hands × pieces; transport: the crews of the pieces, as before).

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

**Results.** Results are reported separately in the results data.

## 11. Stone rule (added 28–29 Oct 2026, the authors' request)
**The rule.** The HYBRID baseline: a site quarries its recorded building stone where known, otherwise the nearest of 7 classes (limestone/marble, metamorphic, basalt, granite, acid volcanic, trachyte, andesite).
- **Source:** 10,662 records of Nurnet's data (site building stone) (`materiale`; aggregate statistics in outputs only). The mapping of values to lithology classes is in `config.yaml → materiale.map` and `output/materiale_mapping.csv`.
- **Hauls:** one multi-source Dijkstra per distinct class set (23 sets).
- **Use of the recorded stone:** fallback 5,052, recorded 2,114, recorded_unreachable_fallback 1 sites. Sandstone and marl lie on loose deposits and have no outcrop class, so those sites fall back to the 7-stone rule.
- **Comparisons:** `stones4` (the original 4-stone rule, `output/stones4/`) and `stones7` (7 classes, no recorded stone; `output/stones7/`).

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

**Island man-hours** (`stone_rule_comparison.csv`, 100 seeds): Results are reported separately in the results data.

**Re-verification on the hybrid base (all passed):**
- `webster` == `full` (0 h difference).
- Cooperation `full` == baseline, in every column.
- A0_verify == `webster` (up to floating-point summation order).
- `P_none` == A0_alone.
- Rank independence (baseline, `high`, `patchwork`, S3e, S6, HIGH, alliance cluster).
- Haul spot-checks.
- Webster calibration (section 3 (c)).
- k-best face 0 == the multi-source haul at all 7,167 sites.

Preprocessing figures in sections 1–9 refer to the 4-stone base unless stated.


## 12. Revision of 2 November 2026 (approved by the authors)

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
700×8 = 24,000 (was 28,800 at 8 h); Webster's transport is 1,100 × 5 = 5,500 person-hours. The model's simulated
values are compared with these. Results are reported separately in the results data.

### 12.2 Citation fixes (items b, c)
- (b) S2b / MOST_REALISTIC fine facing: 131.5 and 40.85 ph/m³ (audited midpoints: 131.2 and
  40.95) are Boswinkel's total all-stage costs per m³ (Table 8.3, p. 144), not dressing rates. The model's use (the
  difference, 90.65 ph/m³ in v11, 90.25 ph/m³ with the audited values, as the extra cost of facade over cyclopean
  masonry on the facing of fine-dressed complexes: TWR_N ≥ 2 in S2b, ≥ 3 in the MOST_REALISTIC rules) is unchanged; labels corrected in code comments,
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
- The season-length runs (40/120/210 days, 29 Oct) used pre-fix code; the authors dropped the scenario on 30 Oct.
  They are marked "obsolete" in every v11 table and not rerun.

### 12.5 Reruns and identity
v11 code with the v11 switches off (`outputs/config_v11_off.yaml`) reproduces the v10 MR_P10 part files exactly
(full island, 100 seeds: outputs/identity/IDENTITY.txt). Reruns: code/V11_NOTES.md and outputs/summary/v11_runs.csv.

## 13. The model: where the current rules are described

- **Headline model.** The MOST_REALISTIC family (the headline row MOST_REALISTIC_AUDITED_LIT_P10 and its variants: work party from residents, per-site technique rules for friction, quarrying, dressing and lifting, population ceiling, sea faces, joint work, seasons and start cohorts) runs on the alliance engine of section 9 with the technique rules of section 8. Its complete description, with every parameter value of the configs of the queue, is `ODD/ODD.md` (sections 2-7, Appendix A); scenario families are described as deltas against the headline in ODD Appendix B.
- **Changes after section 12.** Labels of assumptions and audited parameter values (`config/config_full_audited.yaml`), the social mechanisms (ODD 7.15, 7.16; off in the headline), the near-site rule and the 15 m minimum haul (section 9.1), the on-outcrop test, the addendum-4 flags, L5 / S1-S3 and spread statistics, the relay leg-1 filter removed, the fixes D3, D6, D11 and the 9 Nov L2 scope fix (section 9.1). Earlier versions of the code and of their change notes are in the git history.
- **Lift (9 November 2026; spec addendum k).** Lift (all lift rules: Webster's lift share, lever, internal stair, ramps, earth ramp, spiral, per-site lift overrides, graded lift, and the lever / stair lift of extra sea-payload pieces) is priced at the undiscounted rate. The learning factor (1 − 0.15)^t and skill apply to quarrying, dressing and building only. In the season engine the build stage of a tower is split by its lift share into a build part (discounted as before: the owner at min(skill, 0.85^t), a helper at its own skill, join mode per party) and a lift part (factor 1, whoever performs it; in join mode split by the helper's hands share); `mh_lift` books the lift part exactly. In engine B (`lit.stage_hours`) the S8 factor scales quarrying, dressing and building but no longer lifting (rows with `learning: true`). Skill credits, value-table priors, the task chain and the help logic are unchanged. `CODE_VERSION` is part of every run signature. The configs are those of `config/scenarios/`.
- **Sensitivity and uncertainty methods.** Parameter alternatives (`config/scenarios/config_full_audited_alt_*.yaml`, leave-one-out `_loo_*` configs and the `MOST_REALISTIC_AUD_*` rows), spread statistics across seeds (`_sd _p5 _p95`, `island_by_seed.csv`), and the Sobol, Morris and TOST analyses (section 9.12; TOST configs in `config/scenarios/`; Sobol harnesses in `sensitivity/`) are run from the configs and the queue in `config/`. Results are reported separately in the results data.
