# code_v16_flags (5 Nov 2026): addendum-4 rules behind flags, L5, S1-S4, spread statistics

Decisions (specified by the authors, 5 Nov 2026; "addendum 4" of the specification): L1-L4 each behind its own config
flag, default OFF; L5 and S1-S4 as written. A small test decided which of L1-L4 are kept (a rule is kept only if it
moves mean island years or mean island man-hours by about 3% or more, on the headline or on its most exposed row);
the kept rules are ON by default in code_v16_final (CHANGES_V16_FINAL.md).

Base: the run's code_v15b_outcrop (CHANGES_V15B_OUTCROP.md). Changed files: alliance.py, lit.py, sea.py,
report_alliance.py, census_v12.py, tools/sea_routes.py; new: tests/test_add4_flags.py, this note. Every other file was
byte-identical. code_v16_flags was not published on its own; it is the base of code_v16_final.

## Flags (top-level config block `add4:`, absent = all OFF)

    add4: {rails_cost_choice: false, bedrock_everywhere: false, load_per_tonne: false, sea_priced_as_charged: false,
           rail_lay_mh_per_m: 2.0, load_ph_per_t: 1.2}

The two parameters act only when their flag is on. Flags act on the tech-rules path (MOST_REALISTIC family, alliance.py);
L2 also acts in model.py `--lit REALISTIC` (lit.resolve_site). Not wired (out of the test's scope): L1 in model.py's
`--lit` mixed path and in census_v12.py S23 bichrome (still the 1 km threshold), haul-profile rows (C1/M3/M4) and carts,
which set their own haul / loading and keep it, as the spec says.

| Flag | OFF (= v15b) | ON |
|---|---|---|
| `add4.rails_cost_choice` (L1) | rails (mu 0.1, 300 kg/person) iff the dry-ground (mu 0.38) route > `long_min_haul_m` 1,000 m | per site, before the run (Static._l1_choice): total transport man-hours of all its towers on face 0 for dry ground vs rails + `rail_lay_mh_per_m` x real route length (face-0 length, min-haul floor); cheaper wins and applies to every face and leg (lit.mixed_haul `use_long`). Crews = expected crews per tonne of the block draw (lit.crews_per_tonne, fixed sample, S6 density of the rule's stone) x tonnes; drag costs = the kbest move costs the model charges. Laying is booked to transport in equal parts per tower (owner's transport task, land faces). Near-site rule unchanged (own 1 km test on the dry route). |
| `add4.bedrock_everywhere` (L2) | on-outcrop joints_low 11.1 ph/m3, off-outcrop scree 2.0 ph/m3 | every site joints_low 11.1 ph/m3 x hardness (lit.resolve_site); on-outcrop status still sets the 15 m haul and the stone set |
| `add4.load_per_tonne` (L3) | load_unload_h 0.25 h per crew member per trip (half per relay leg) | crews x (drag + walk) + `load_ph_per_t` 1.2 x tonnes of the tower (half per relay leg) (AllianceModel._crew_trip_mh) |
| `add4.sea_priced_as_charged` (L4) | sea face iff the table builder's per-crew (mu 0.3, 100 kg/person) trip was cheaper (column `mode`); land legs charged at dry-ground crews | every sea route the builder found (new r_* columns, v16 tools/sea_routes.py) is a candidate; per site before the run (Static._l4_sea_faces), expected cost per tonne as charged: land legs at the site's rule (L1 on: each leg rails or dry by its own cost incl. laying; L1 off: the site's rule), loading per crew per landing (sea.transfer_h) or under L3 1.2 ph/t per land leg, boat crews x boat time as S9, hoist per block; sea face iff cheaper than the face-0 land cost. The model charges the same way (AllianceModel._sea_l4_mh). Needs sea tables rebuilt with v16 tools/sea_routes.py (the old columns are unchanged; r_* added). Route geometry = the builder's shortest path in its own per-crew currency (not re-optimised for the charged currency); people travel tables unchanged. |

## Relay leg-1 filter removed (specified by the authors, 5 Nov 2026)
The relay leg-1 candidate filter "nearer the quarry than the owner" (v15b: `candidates(i, "leg1", qxy,
nearer_than=dself)`) is REMOVED, no flag: leg-1 candidates are the ordinary candidate list (as
code_v15c_norelayfilter, built separately from code_v15b_outcrop). Its effect was measured before the removal with a
temporary switch (headline, flags OFF). Consequence: with all add4 flags OFF this code is v15b minus the relay filter,
NOT v15b. The identity with v15b (below) was verified on the code before the removal (V16_VERSION -1); the final code
with flags OFF reproduces that measurement run (headline seeds 1-3, every site identical).
All L1-L4 test runs used the v15b relay rule (filter on).

Signature: V16_VERSION is always hashed (S1 adds a column to the strategy parts, S3 changes the ceiling basis), so no
v16 run reuses v15b parts; the add4 settings (and the r_* sea columns under L4) are hashed only when a flag is on.

## Always on (as written)
- **L5** `island_years_p95`: per seed, the island-wide 95th percentile of the site finish seasons (numpy linear).
  This replaced (5 Nov) the first definition (sum over cohorts of the 95th-percentile site finish in seasons from
  the cohort start, report_alliance.island_years_q, which breaks when cohorts overlap); that one is still reported as
  `island_years_p95_cohortsum` (with the max instead of p95 it equals island years; tested).
- **S1** strategy parts get `relay_made` (hand-off executed); stats.json `relay_share_chosen` (= the old
  `relay_share_towers`, which is kept as an alias for existing readers) and `relay_share_made`.
- **S2** census S21 levy: the work booked beyond the season's budget (days x share x party x hours) carries to the next
  season (census_v12.Census.season_start; v15b reset it to 0). Census levy rows only.
- **S3** population ceiling checked against the residents of all communities of the run (started or waiting), not the
  active cohort; population.json gets `ceiling_binding`, stats.json `ceiling_binding`, `ceiling_binding_seeds`,
  `total_residents_mean/max`. On the headline the ceiling does not bind. Rows with larger
  resident ranges and a ceiling may now bind (redraw rule as written).
- **S4** spec text only; the code has no literal 100 m minimum (all floors read transport.min_haul_flatm). One code
  comment in census_v12.py corrected.

## Spread statistics (report_alliance.write_scenario)
stats.json keeps every existing key and adds, for island seasons (= island years), island_years_p95, island man-hours
and island man-hours by stage (quarry, dress, transport, build, lift, setup, track, walk): `_mean _sd _min _max _p5
_p95` across seeds (sd ddof=1, numpy linear percentiles; existing `_mean/_min/_max` keys are not overwritten). New file
`island_by_seed.csv` (per-seed values). `static_info` (rails sites, sea faces, flags) from the run's static_info.json.

## Tests
`tests/test_add4_flags.py` (13 tests; `python tests/test_add4_flags.py`, the geo-venv has no pytest): each flag off =
old, on = new (L1 threshold vs cost choice incl. a hand computation; L2 scree vs joints; L3 loading; L4 pricing equals
the S9 charge when the rules match, L3/L1 variants), S2, S3, L5, spread, signature (all-off = no add4 hash).
Whole-run identity, all flags OFF vs v15b, headline seeds 1-3: IDENTICAL (code before the relay-filter removal).
