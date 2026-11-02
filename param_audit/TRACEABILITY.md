# Traceability matrix: literature ideas, audited parameters and literature alternatives -> FULL AUDITED queue (2 Nov 2026)

Requested by the authors: every parameter auditable, every literature idea linked to at least one scenario. No model was run for this matrix. Built by `param_audit/_build/traceability.py` (data tables in `_build/trace_data.py`) and `_build/render_trace.py`; scenario dicts are resolved with the frozen code's `alliance.scenario()` (runs/2026-11-02-v12-census/full_audited/code).

Queue snapshot: queue_full.tsv  + queue_full_p23.tsv : 313 entries, 507 distinct scenario names (comma lists, `--alliance sensitivity` = 27 SENS cells, config copies as NAME@config). 140 names are MOST_REALISTIC-family runs (tech_rules set). Files written: IDEA_TRACE.csv, PARAM_TRACE.csv, PARAM_NOT_IN_AUDIT.csv, LIT_ALT_COVERAGE.csv, SCENARIO_PROVENANCE_v2.csv, GAPS.md.

## 0. Findings that need a decision

1. **Duplicate runs.** In config_full_audited.yaml `*mr_work_party.adult_share` is 0.4, so `MOST_REALISTIC_P10` and `MOST_REALISTIC_POP_adult04_P10` resolve to exactly the same scenario dict as `MOST_REALISTIC_AUDITED_LIT_P10` (alliance.scenario, all keys; the block and work-party draws are seeded by seed and site, not by name). They are queued as MOST_REALISTIC_P10, MOST_REALISTIC_POP_adult04_P10: about 12 min of identical output. MR_P10's P20 / P100 twins are the audited schedule twins, which is what they should be.
2. **Population family is no longer one-at-a-time.** The queued POP entries (lilliu30, webster_household, webster_density, calo_6km2, ugas_high, ugas400, ugas700, anchored) set `adult_share: 0.5` with their residents rule, so each differs from the audited baseline (0.4) in TWO keys; men_only (0.2) and adult06 (0.6) are one change. PARAM_TRACE lists them under both P1 and P2. Twins at 0.4: GAPS.md rank 4.
3. **drag10 / pull125 sea tables.** `tools/sea_routes.py` reads transport.drag_speed_ms, return_walk_ms, load_unload_h, min_haul_flatm, pull_kg_per_person, the lever rate, course height and the block draw (sea_params, code/tools/sea_routes.py:154-171) to choose sea vs land routes. The LOO_drag and LOO_walk runs get their own SEA_TABLES; `MR_P10_v12_drag10` and `MR_P10_v11_pull125` use the shared cache_dir (tables built at 0.27 m/s and 100 kg). Their trip times are recomputed from their own config at run time (code/sea.py:32-39), but the sea/land choice is the audited one. Worth stating in the report or giving them own tables (2 x 220 s).
4. **Config value vs audit final value: no mismatch.** All 70 audited rows carry the AUDITED value in config_full_audited.yaml (the 9 changed values: drag 0.27, walk 1.39, basalt 3000, granite 2700, joints_low 11.1, facade 131.2 / 40.95, height 14, top 6.8, adult_share 0.4). Stale text only: the config comments at transport.pull_kg_per_person / drag_speed_ms ('Value unchanged') and lit_scenarios geometry ('15 m, 12 m -> 8 m'), and PARAM_AUDIT Part 2 rows 8a ('round(0.5 x residents)') and 11b ('1.4 m/s') still describe the pre-audit values. P2 is marked 'provisional; final from the population runs' in the audit.
5. **Post hoc checks are not queue entries.** The 10 V_* checks (tools/v12_checks.py) need re-running on the full_audited outputs after the chain; they are counted as LINKED through the queued runs they read.

## 1. Literature ideas -> scenarios -> queue (IDEA_TRACE.csv)

92 census ideas: **LINKED 79** (run 64, post hoc on queued runs 10, implicit in every run 5), **LINKED-NOT-QUEUED 0**, **NO SCENARIO 13** (the 13 NOT TESTABLE ideas). By class: ALREADY TESTED 48/48 linked, TESTABLE NOW 31/31 linked, NOT TESTABLE 0/13.

Matching: a mapped scenario X counts as queued when a queued `--alliance / --scenario / --lit / --pre` name equals X or X + `_P10/_P20/_P100/_sea/_sea<kn>kn` (exact names; wildcard families such as `P_G3_canton_*` are expanded against the queue). The queued labels are the queue `label` column. `scenario_origin_v2` is the origin of the matched scenarios in SCENARIO_PROVENANCE_v2.csv. Partial links worth knowing: G04 `stones7` is a preprocessing rule, not a queued scenario (only S5b_any_buildstone is queued); D02 runs v 0.10 / 0.30 (v 0.20 of the plan is not configured); F01's optional S15_found_ramp pair is not configured; S01 is linked through the 90-day season only.

| id | class | status | link | queued names | queue entry labels | note / proxy |
|---|---|---|---|---|---|---|
| Q01 | ALREADY TESTED | LINKED | run | 8 | S5a_onsite; S1b_joints_low; S1b_joints_high; REALISTIC; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_AUDITED_LIT_P10 | hybrid stone rule is in every run (preprocessing cache) |
| Q02 | ALREADY TESTED | LINKED | run | 3 | S1b_joints_low; S1b_joints_high; MOST_REALISTIC_C3_quarry_P10 |  |
| Q03 | ALREADY TESTED | LINKED | implicit | 2 | MOST_REALISTIC_AUDITED_LIT_P10; MOST_REALISTIC_C2_day5_P10 | every quarry rate is a non-metal rate; v11 5-h day in the baseline |
| Q04 | ALREADY TESTED | LINKED | run | 6 | S1a_scree; REALISTIC; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_AUDITED_LIT_P10 |  |
| Q05 | TESTABLE NOW | LINKED | run | 4 | MOST_REALISTIC_S18_clearance_y10_P10; MOST_REALISTIC_S18_clearance_y50_P10; MOST_REALISTIC_S18_clearance_y200_P10; MOST_REALISTIC_AUDITED_LIT_P10 | V_density_stone is post hoc (inputs only) |
| Q06 | ALREADY TESTED | LINKED | run | 3 | S1b_joints_low; S1b_joints_high; MOST_REALISTIC_AUDITED_LIT_P10 | hybrid stone rule |
| Q07 | ALREADY TESTED | LINKED | run | 7 | S7_webster_classes; MOST_REALISTIC_S13_high_P10; MOST_REALISTIC_S10_all_P10; MOST_REALISTIC_S10_s70_P10; MOST_REALISTIC_S10_half_P10; MOST_REALISTIC_S... |  |
| D01 | ALREADY TESTED | LINKED | run | 6 | S2a_unworked; REALISTIC; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_AUDITED_LIT_P10 |  |
| D02 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S2c_vault_v10_P10; MOST_REALISTIC_S2c_vault_v30_P10 | TESTABLE_PLAN range v 0.10-0.30; v 0.20 is not configured |
| D03 | ALREADY TESTED | LINKED | run | 6 | S2b_fine; REALISTIC; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_C3_dress_P10 |  |
| D04 | ALREADY TESTED | LINKED | run | 2 | S2b_fine; HIGH | stone-sourcing side = G05 |
| D05 | ALREADY TESTED | LINKED | implicit | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | all runs haul undressed block mass; quarry-dressing alternative not run (contradicted by the evidence, census) |
| D06 | ALREADY TESTED | LINKED | run | 25 | baseline; mostly_TOST_block_median_kg_min; full_TOST_block_median_kg_min; mostly_TOST_block_median_kg_max; full_TOST_block_median_kg_max; mixed_TOST_b... | TOST ends are on the cooperation family only (not MR) |
| D07 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S4_graded_rate_P10; MOST_REALISTIC_S4_graded_order_P10 |  |
| D08 | TESTABLE NOW | LINKED | run | 3 | MOST_REALISTIC_S20_lintels_1t5_P10; MOST_REALISTIC_S20_lintels_3t0_P10; MOST_REALISTIC_S20_lintels_4t2_P10 |  |
| T01 | ALREADY TESTED | LINKED | run | 5 | S3a_rails_tallow; S3b_rails_grease; S3c_dry_ground; MOST_REALISTIC_C1_rails_P10; MOST_REALISTIC_C1_rails_relay_P10 |  |
| T02 | ALREADY TESTED | LINKED | run | 5 | S3c_dry_ground; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; S4a_lever |  |
| T03 | ALREADY TESTED | LINKED | run | 2 | S3e_oxen; REALISTIC_oxen |  |
| T04 | ALREADY TESTED | LINKED | run | 1 | S3b_rails_grease | slope penalty of the drag raster is in every run |
| T05 | ALREADY TESTED | LINKED | run | 2 | MOST_REALISTIC_C2_sled200_P10; webster |  |
| T06 | TESTABLE NOW | LINKED | run | 1 | MOST_REALISTIC_S24_carts_P10 |  |
| T07 | ALREADY TESTED | LINKED | run | 70 | S9_sea_2kn; S9_sea_4kn; S9_sea_5kn; S9_sea_6kn; high_sea; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; S9_alliance_sea_6; S9_pre_sea_5... |  |
| T08 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| T09 | ALREADY TESTED | LINKED | run | 16 | A4_trust_track; S9_alliance_sea_6; PHASE_alliance_P10; PHASE_alliance_P20; A5_full; P_G20_kmesh4_track; S9_pre_sea_5; GRID10_sea_b3; GRID10_P10_b3; GR... |  |
| T10 | ALREADY TESTED | LINKED | run | 1 | S5c_complex_far | hybrid stone rule (recorded stone) |
| T11 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | hybrid-rule haul of San Gavino sites (MR summary); post hoc via tools/v12_checks.py (not a queue entry; re-run on full_a |
| L01 | ALREADY TESTED | LINKED | run | 2 | S4b_ramp; HIGH |  |
| L02 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S4e_laner_h3_P10; MOST_REALISTIC_S4e_laner_h4_P10 |  |
| L03 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S4d_spiral_7m5_P10; MOST_REALISTIC_S4d_spiral_full_P10 |  |
| L04 | NOT TESTABLE | NO SCENARIO |  | 0 | - | partial (queued) |
| L05 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| L06 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| L07 | ALREADY TESTED | LINKED | run | 5 | S4c_internal_stair; REALISTIC; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100 |  |
| L08 | ALREADY TESTED | LINKED | run | 2 | S4b_ramp; S4c_internal_stair |  |
| L09 | ALREADY TESTED | LINKED | run | 4 | S4a_lever; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100 |  |
| L10 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| L11 | ALREADY TESTED | LINKED | implicit | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | no centring cost in any run; the centring alternative has no rate |
| L12 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| L13 | ALREADY TESTED | LINKED | run | 2 | MOST_REALISTIC_C3_set_low_P10; MOST_REALISTIC_C3_set_high_P10 |  |
| F01 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S15_found_d1_P10; MOST_REALISTIC_S15_found_d2_P10 | optional S15_found_ramp pair (TESTABLE_PLAN) is not configured |
| F02 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S4_graded_order_P10; MOST_REALISTIC_S4_graded_rate_P10 |  |
| F03 | ALREADY TESTED | LINKED | implicit | 2 | MOST_REALISTIC_AUDITED_LIT_P10; MOST_REALISTIC_S15_found_d1_P10 | no foundation cost in the baseline; contrast S15_found |
| M01 | ALREADY TESTED | LINKED | run | 4 | webster; MOST_REALISTIC_C2_wall_P10; MOST_REALISTIC_C3_set_low_P10; MOST_REALISTIC_C3_set_high_P10 |  |
| M02 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S16_mud_m05_P10; MOST_REALISTIC_S16_mud_m15_P10 |  |
| M03 | TESTABLE NOW | LINKED | run | 3 | MOST_REALISTIC_S17_fill_f30_P10; MOST_REALISTIC_S17_fill_f40_P10; MOST_REALISTIC_S17_fill_f50_P10 |  |
| M04 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S19_mudbrick_h2_P10; MOST_REALISTIC_S19_mudbrick_h4_P10 |  |
| P01 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_S10_all_P10; MOST_REALISTIC_S10_s70_P10; MOST_REALISTIC_S10_half_P10; MOST_REALISTIC_S10_all_crew50_P10 |  |
| P02 | ALREADY TESTED | LINKED | run | 3 | MOST_REALISTIC_S10_unitary_P10; MOST_REALISTIC_S10_s70_P10; MOST_REALISTIC_S10_half_P10 |  |
| P03 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_S10_all_P10; MOST_REALISTIC_S10_s70_P10; MOST_REALISTIC_S10_half_P10; MOST_REALISTIC_S10_all_crew50_P10 |  |
| P04 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_S11_order_P10; MOST_REALISTIC_S11_low_P10; MOST_REALISTIC_S11_mid_P10; MOST_REALISTIC_S11_high_P10 |  |
| P05 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| P06 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S13_rifascio_p80_s20_P10; MOST_REALISTIC_S13_rifascio_p120_s50_P10 |  |
| W01 | ALREADY TESTED | LINKED | run | 7 | A0_alone; MOST_REALISTIC_alone_P10; MOST_REALISTIC_alone_P20; MOST_REALISTIC_alone_P100; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100 |  |
| W02 | ALREADY TESTED | LINKED | run | 31 | MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; P_G3_canton_hub; P_G3_canton_chain; P_G3_canton_kmesh2; P_G3_canton_kmesh4; P_G3_canton_c... |  |
| W03 | ALREADY TESTED | LINKED | run | 15 | A1_ask; S9_alliance_sea_6; PHASE_alliance_P10; PHASE_alliance_P20; A2_trust; A3_trust_learning; MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC... |  |
| W04 | ALREADY TESTED | LINKED | run | 5 | MOST_REALISTIC_M2_complex_P10; A3_trust_learning; S9_alliance_sea_6; PHASE_alliance_P10; PHASE_alliance_P20 |  |
| W05 | ALREADY TESTED | LINKED | run | 76 | P_G20_system_kmesh4; P_G20_system_complete; P_G20_system_kmesh8; P_G20_system_kmesh4_h3; P_G20_system_smallworld; P_G20_system_kmesh4_h2; P_G20_system... |  |
| W06 | ALREADY TESTED | LINKED | run | 20 | P_G3_canton_hub; GRID10_sea_b1; GRID10_P10_b1; GRID10_P20_b1; P_G133_tribe_hub; P_G133_tribe_hub_h2; P_G133_tribe_hub_h3; GRID10_sea_b2; GRID10_P10_b2... |  |
| W07 | TESTABLE NOW | LINKED | run | 4 | MOST_REALISTIC_S21_levy_R1.7_D40_P10; MOST_REALISTIC_S21_levy_R1.7_D90_P10; MOST_REALISTIC_S21_levy_R1.1_D40_P10; MOST_REALISTIC_S21_levy_R11.9_D40_P1... |  |
| W08 | TESTABLE NOW | LINKED | run | 1 | MOST_REALISTIC_S21_levy_masters_P10 |  |
| W09 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_M2_central_P10; MOST_REALISTIC_M2_small_P10; MOST_REALISTIC_M2_large_P10; MOST_REALISTIC_M2_complex_P10 |  |
| W10 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_M2_regional_tribes_P10; MOST_REALISTIC_M2_regional_regions_P10 |  |
| W11 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_M2_central_P10 | contrast MR (no masters) vs M2 |
| W12 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| W13 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S22_demog_r035; MOST_REALISTIC_S22_demog_r042 | unphased by design |
| W14 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_AUDITED_LIT_P10 | population_ceiling 300,000 in every MR run |
| S01 | ALREADY TESTED | LINKED | run | 4 | MOST_REALISTIC_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100; MOST_REALISTIC_AUDITED_LIT_P10 | 90-day season only; the 40/120/210-day runs are obsolete (pre-fix code) and no 40-day MR run is queued (gap) |
| R01 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| R02 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| R03 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| R04 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| R05 | TESTABLE NOW | LINKED | posthoc | 3 | MOST_REALISTIC_AUDITED_LIT_P10; MOST_REALISTIC_P20; MOST_REALISTIC_P100 | needs MR P10, P20 and P100; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| R06 | TESTABLE NOW | LINKED | run | 21 | X_nurtime | single-site predictions (unphased) |
| R07 | TESTABLE NOW | LINKED | posthoc | 2 | MOST_REALISTIC_AUDITED_LIT_P10; MOST_REALISTIC_S20_lintels_3t0_P10 | also uses S20_lintels_3t0; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| U01 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| U02 | NOT TESTABLE | NO SCENARIO |  | 0 | - | partial (queued) |
| U03 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| C01 | ALREADY TESTED | LINKED | run | 3 | MOST_REALISTIC_S14_low_P10; MOST_REALISTIC_S14_central_P10; MOST_REALISTIC_S14_high_P10 |  |
| C02 | ALREADY TESTED | LINKED | run | 3 | MOST_REALISTIC_S14_low_P10; MOST_REALISTIC_S14_central_P10; MOST_REALISTIC_S14_high_P10 |  |
| C03 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| E01 | ALREADY TESTED | LINKED | run | 5 | MOST_REALISTIC_S12_low_P10; MOST_REALISTIC_S12_s10_P10; MOST_REALISTIC_S12_central_P10; MOST_REALISTIC_S12_s30_P10; MOST_REALISTIC_S12_high_P10 |  |
| E02 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S12b_feast_b05_P10; MOST_REALISTIC_S12b_feast_b2_P10 |  |
| Z01 | NOT TESTABLE | NO SCENARIO |  | 0 | - | no |
| Z02 | ALREADY TESTED | LINKED | run | 16 | P_G3_canton_hub; GRID10_sea_b1; GRID10_P10_b1; GRID10_P20_b1; P_G20_system_hub; S9_pre_sea_5; GRID10_sea_b3; P_G20_system_hub_P10; GRID10_P10_b3; P_G2... |  |
| Z03 | ALREADY TESTED | LINKED | run | 77 | MOST_REALISTIC_M1_s1_R5_P10; MOST_REALISTIC_M1_s01_R5_P10; MOST_REALISTIC_M1_s10_R5_P10; MOST_REALISTIC_M1_s1_R2500_P10; MOST_REALISTIC_M1_s1_R10_P10;... |  |
| G01 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| G02 | ALREADY TESTED | LINKED | implicit | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | hybrid stone rule (preprocessing cache) in every run |
| G03 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| G04 | ALREADY TESTED | LINKED | run | 1 | S5b_any_buildstone | stones7 is a stone_rule value (preprocess.py --rule), not a queued scenario |
| G05 | TESTABLE NOW | LINKED | run | 2 | MOST_REALISTIC_S23_bichrome_b05_P10; MOST_REALISTIC_S23_bichrome_b15_P10 |  |
| G06 | TESTABLE NOW | LINKED | posthoc | 1 | MOST_REALISTIC_AUDITED_LIT_P10 | ; post hoc via tools/v12_checks.py (not a queue entry; re-run on full_audited outputs) |
| G07 | TESTABLE NOW | LINKED | run | 1 | MOST_REALISTIC_S25_size_P10 |  |

### NOT TESTABLE ideas: reason (census) and proxy

| id | not_testable_reason (census) | proxy | why / which |
|---|---|---|---|
| T08 | Data missing: no evidence of Bronze Age navigability of Sardinian rivers or of river-borne building stone. | no | No config key routes stone along rivers. A small-code proxy would need river legs in a router like tools/sea_routes.py (about 120-150 lines, plus a navigability rule); the only stream data in the project (water/sardinia_rivers_25832.shp, used by tools/wl_inputs.py) is the modern network. The census records no evidence of Bronze Age navigability, so any river speed or depth rule would be invented. Not proposed. |
| L04 | Data missing: no timber felling/working rate in the sources, and Laner shows the structure impractical. | partial (queued) | Geometric proxy already queued: MOST_REALISTIC_S4d_spiral_7m5_P10 / MOST_REALISTIC_S4d_spiral_full_P10 (lift_ramp {kind: spiral, slope 0.12}) cost an external spiral ramp in EARTH. The wooden version needs a timber felling/working rate, which no source gives (census), so a timber cost cannot be added without inventing a number. |
| L05 | No mechanism or rate specified in an accessible source. | no | No mechanism or rate in an accessible source; a lever-rate change (lit_scenarios.lever_ph_per_block_course) would be an invented factor. Not proposed. |
| L06 | Data missing: no Bronze Age pulley or tackle, no lift rate; cattle traction late (T03). | no | No Bronze Age pulley or lift rate (census). The only hoist in the code is the sea-cliff hoist (sea.py hoist_ph_per_block_m = lever rate / course height), which is the lever rate itself. A winch scenario would need an invented lift rate. Not proposed. |
| L10 | Data missing: no timber rate or scaffold design; contradicted by Laner 1999: 33 (no scaffolding). | no | No timber rate or scaffold design; contradicted by Laner 1999: 33 (census). Not proposed. |
| L12 | No labour or spatial consequence at the model grain (same stone, same lift). | no | Same stone and same lift at the model grain (census): a course-order switch would change no labour total. Would need code (course sequencing per face) and still give an identical result. |
| P05 | Data missing: no count of nuraghi built on earlier walls; the stone saving cannot be assigned to sites. | no | No count of nuraghi built on earlier walls (census), so neither a site share nor a stone saving can be set. A config proxy (e.g. type_cost volume < 1 for corridor nuraghi) would use invented numbers. Not proposed. |
| W12 | No labour or spatial consequence in the model. | no | No labour or spatial consequence in the model (census). |
| U01 | Post-Nuragic: no consequence for how the nuraghi were built (affects only today's heights and tower counts). | no | Post-Nuragic (census): affects today's heights / tower counts (input data), not building. |
| U02 | Post-Nuragic; an input-data issue (original heights), not a building mechanism. | partial (queued) | Input-data issue (original heights). The nearest queued proxy is MOST_REALISTIC_S25_size_P10 (size_draw floor shares 0.58/0.38/0.04, Atzeni & Frau 2023: 326), but those shares are of residual floors, not original ones (census G07), so it does not reconstruct removed upper courses. |
| U03 | Data missing: no evidence that Nuragic builders robbed abandoned towers; abandonment mostly postdates the building phase. | no | Needs code (stone source = an abandoned tower within R, salvage share; about 80-100 lines in alliance.py) and the census records no evidence of Nuragic robbing; abandonment mostly postdates building. Not proposed. |
| C03 | Post-use process; no consequence for construction labour. | no | Post-use process; no consequence for construction labour (census). |
| Z01 | Chronology: federal sanctuaries date from c. 950 BC, after most nuraghe building (Ialongo 2018); no consequence for tower construction. | no | Sanctuaries date from c. 950 BC, after most nuraghe building (Ialongo 2018, census); no construction consequence. |

No config-only or small-code proxy is proposed for these: each would need a number the sources do not give. Two have a partial proxy that is already queued (L04: the earth spiral ramp S4d; U02: S25_size), which does not test the idea itself.

## 2. Audited parameters -> config -> code -> queue (PARAM_TRACE.csv, PARAM_NOT_IN_AUDIT.csv)

70 audited rows traced. Value in config_full_audited.yaml = audited final value: **70/70**. Read by the frozen code (file:line found): **70/70**. Acting on MR_P10: 69/70 (5 of them only through a cached preprocessing product or the SEA_TABLES entry: H10, H11, K1, K2, S5); not acting: P4 (no (cooperation family only)). Varied by at least one queued MR-family run: 30/70; acting on MR_P10 but varied by NO queued MR run: 39 (T3, T4, B2, B3, B4, B6, B9, B10, B11, Q3, Q7, G2, G4, G6, G7, G9, G10, H9, H10, H11, H12, H13, K1, K2, K3, A1, A2, A3, A5, A6, A7, A8, S1, S2, S3, S4, S5, X1, X2).

Code locations are the first non-comment reads of the key in code/{alliance, lit, census_v12, sea, phasing, model, preprocess, pre_networks}.py and the cache tools (tools/sea_routes.py, kbest_quarries.py, build_cost_mu.py, wl_inputs.py). 'Queued MR scenarios varying' is computed by diffing every queued MR-family scenario dict (and config copy) against MOST_REALISTIC_AUDITED_LIT_P10.

| id | config path | config value | audited | = | code reads | acts on MR_P10 | status after (PARAM_AUDIT) | MR runs varying | other families varying |
|---|---|---|---|---|---|---|---|---|---|
| P1 | MR:builders_rule.residents_by_towers | [[5, 40], [40, 110], [110, 185], [185, 2 | [5,40],[40,110],[110,185],[185 | yes | code/lit.py:223; code/lit.py:231 | yes | DERIVED | 30 |  |
| P2 | MR:builders_rule.adult_share; mr_work_party.adult_share | [0.4, 0.4] | 0.4 (provisional; final from t | yes | code/lit.py:244 | yes | DERIVED | 32 |  |
| P3 | MR:population_ceiling | 300000 | 300000 | yes | code/alliance.py:258; code/alliance.py:561 | yes | SOURCED | 26 |  |
| P4 | scenarios.household_size | 5 | 5 | yes | code/model.py:237 | no (cooperation family only) | SOURCED | 0 | TOST household_size 3 / 8 on none, low, mixed, mostly, full, |
| T1 | MR:phase_frac | 0.1 | 0.1 | yes | code/alliance.py:253; code/alliance.py:458; code/model.py:406 | yes | Authors' assumption (specified by M. Alt | 29 | PHASE_alliance_P10 / P20, P_*_P10 / P20, high_P10 / P20 |
| T2 | (code) phasing.cohorts | (not a config key) | random | yes | code/phasing.py:24 | yes | Authors' assumption (agent's design choi | 16 |  |
| T3 | alliance.season_days | 90 | 90 | yes | code/alliance.py:669; code/alliance.py:1689 | yes | Authors' assumption (specified by M. Alt | 0 |  |
| T4 | hours_per_day | 8 | 8 | yes | code/alliance.py:233; code/alliance.py:701; code/lit.py:89 | yes | SOURCED | 0 | TOST hours_per_day 6 / 10 (cooperation family only) |
| T5 | v11.webster_day_hours | {"quarry": 5, "transport": 5, "dress": 8 | quarry 5, transport 5, dress 8 | yes | code/lit.py:88 | yes | REPORTED-ONLY | 1 |  |
| B1 | stone.tonnes_per_tower | 1350 | 1350 | yes | code/alliance.py:331; code/alliance.py:332; code/lit.py:76 | yes | SOURCED | 9 | S7_webster_classes, LOW, HIGH (lit family) |
| B2 | stone.block_median_kg | 450 | 450 | yes | code/alliance.py:340; code/alliance.py:341; code/model.py:221 | yes | SOURCED | 0 | TOST block_median_kg 300 / 1000 (cooperation family only) |
| B3 | stone.block_sigma | 0.6 | 0.6 | yes | code/alliance.py:340; code/model.py:221; code/tools/sea_routes.py:166 | yes | DERIVED | 0 | TOST block_sigma 0.3 / 0.9 (cooperation family only) |
| B4 | stone.block_min_kg | 60 | 60 | yes | code/alliance.py:340; code/model.py:221; code/tools/sea_routes.py:167 | yes | Authors' assumption (agent's design choi | 0 |  |
| B5 | stone.block_max_kg | 2400 | 2400 | yes | code/alliance.py:340; code/model.py:221; code/tools/sea_routes.py:167 | yes | SOURCED | 3 |  |
| B6 | lit_scenarios.webster_density_kg_m3 | 2386 | 2386 | yes | code/alliance.py:739; code/alliance.py:905; code/lit.py:69 | yes | SOURCED | 0 |  |
| B7 | lit_scenarios.density_kg_m3.basalt | 3000 | 3000 | yes | code/lit.py:69 | yes | SOURCED † | 1 | S6_density, HIGH, REALISTIC, REALISTIC_oxen (lit family: on) |
| B8 | lit_scenarios.density_kg_m3.granite | 2700 | 2700 | yes | code/lit.py:69 | yes | SOURCED | 1 | as B7 |
| B9 | lit_scenarios.density_kg_m3.limestone/marble | 2600 | 2600 | yes | code/lit.py:69 | yes | Authors' assumption (agent's design choi | 0 | as B7 |
| B10 | lit_scenarios.density_kg_m3.metamorphic | 2750 | 2750 | yes | code/lit.py:69 | yes | REPORTED-ONLY | 0 | as B7 |
| B11 | lit_scenarios.hardness | {"basalt": 2.0, "granite": 2.0, "limesto | 2.0 / 1.0 | yes | code/alliance.py:762; code/alliance.py:906; code/lit.py:121 | yes | Authors' assumption (agent's design choi | 0 | as B7 |
| Q1 | lit_scenarios.quarry_ph_m3.scree | 2.0 | 2.0 | yes | code/alliance.py:759; code/alliance.py:908; code/lit.py:108 | yes | SOURCED | 3 | S1a_scree, LOW (lit family) |
| Q2 | lit_scenarios.quarry_ph_m3.joints_low | 11.1 | 11.1 | yes | code/alliance.py:759; code/alliance.py:908; code/lit.py:108 | yes | SOURCED | 3 | S1b_joints_low (lit family) |
| Q3 | lit_scenarios.list.REALISTIC.mixed.quarry_on_outcrop; lit_sc | ["joints_low", "scree"] | rule | yes | code/lit.py:205 | yes | Authors' assumption (agent's design choi | 0 | S1a_scree, S1b_joints_low/high, S5a_onsite (lit family) |
| Q4 | lit_scenarios.list.REALISTIC.mixed.dress_none_max_towers; li | [1, 3] | rule | yes | code/lit.py:206; code/lit.py:208 | yes | Authors' assumption (agent's design choi | 2 | S2a_unworked, S2b_fine, HIGH, LOW (lit family) |
| Q5 | lit_scenarios.webster_md_per_tower | {"quarry": 500, "transport": 1100, "dres | 500 / 1300 / 700 md | yes | code/alliance.py:734; code/alliance.py:918; code/lit.py:96 | yes | SOURCED | 5 | webster, S7_webster_classes (lit family) |
| Q6 | lit_scenarios.facade | {"facade_ph_m3_mid": 131.2, "cyclopean_p | 131.2 / 40.95 | yes | code/lit.py:118 | yes | DERIVED | 3 | S2b_fine, HIGH (lit family) |
| Q7 | lit_scenarios.facing_thickness_m | 0.5 | 0.5 | yes | code/alliance.py:923; code/lit.py:116; code/census_v12.py:225 | yes | DERIVED | 0 |  |
| G1 | lit_scenarios.geometry.tower_height_m | 14.0 | 14 | yes | code/alliance.py:921; code/alliance.py:1371; code/lit.py:36 | yes | SOURCED † | 7 |  |
| G2 | lit_scenarios.geometry.base_diam_m | 12.0 | 12 | yes | code/alliance.py:921; code/lit.py:36; code/lit.py:114 | yes | DERIVED | 0 |  |
| G3 | lit_scenarios.geometry.top_diam_m | 6.8 | 6.8 | yes | code/alliance.py:921; code/lit.py:36; code/lit.py:114 | yes | DERIVED | 1 |  |
| G4 | lit_scenarios.geometry.course_height_m | 0.9 | 0.9 | yes | code/alliance.py:736; code/alliance.py:1372; code/lit.py:36 | yes | SOURCED | 0 |  |
| G5 | lit_scenarios.lever_ph_per_block_course | 0.37 | 0.37 | yes | code/alliance.py:765; code/alliance.py:778; code/lit.py:128 | yes | SOURCED | 2 |  |
| G6 | lit_scenarios.lift_share_of_build | 0.5 | 0.5 | yes | code/alliance.py:735; code/alliance.py:1892; code/lit.py:97 | yes | Authors' assumption (agent's design choi | 0 |  |
| G7 | lit_scenarios.stair_lever_last_m | 1.0 | 1.0 | yes | code/lit.py:134; code/census_v12.py:147; code/census_v12.py:164 | yes | Authors' assumption (agent's design choi | 0 |  |
| G8 | lit_scenarios.list.REALISTIC.mixed.lift_by_type; lit_scenari | [{"Nuraghe a corridoio (protonuraghe)":  | rule | yes | code/lit.py:212 | yes | Authors' assumption (agent's design choi | 25 | S4a_lever, S4b_ramp, S4c_internal_stair (lit family) |
| G9 | lit_scenarios.learning_rate | 0.15 | 0.15 | yes | code/alliance.py:312; code/lit.py:137 | yes | Authors' assumption (agent's design choi | 0 | S8_learning (lit family, on); other lit scenarios off |
| G10 | MR:b; alliance.defaults.b | [0.85, 0.85] | 0.85 | yes | code/alliance.py:247 | yes | DERIVED | 0 | A5_SENSITIVITY_27cells (b 0.85 / 0.95 / 1.0 on A5_full) |
| H1 | transport.drag_speed_ms | 0.27 | 0.27 | yes | code/alliance.py:804; code/alliance.py:1267; code/lit.py:151 | yes | SOURCED | 3 | MR_P10_v12_drag10 (config copy, 1.0 m/s) |
| H2 | lit_scenarios.f_person_kgf | 30 | 30 | yes | code/alliance.py:243; code/alliance.py:382; code/lit.py:150 | yes | SOURCED | 1 | MR_P10_v11_pull125 (config copy, 12.75 kgf) |
| H3 | transport.pull_kg_per_person | 100 | 100 | yes | code/alliance.py:242; code/lit.py:150; code/sea.py:27 | yes | DERIVED | 5 | MR_P10_v11_pull125 (config copy, 42.49 kg) |
| H4 | transport.return_walk_ms | 1.39 | 1.39 | yes | code/alliance.py:979; code/alliance.py:1008; code/lit.py:151 | yes | SOURCED | 1 |  |
| H5 | transport.load_unload_h | 0.25 | 0.25 | yes | code/alliance.py:804; code/alliance.py:1268; code/sea.py:26 | yes | DERIVED | 2 |  |
| H6 | transport.min_haul_flatm | 100 | 100 | yes | code/alliance.py:1263; code/alliance.py:1264; code/census_v12.py:227 | yes | SOURCED | 1 |  |
| H7 | lit_scenarios.list.REALISTIC.mixed.short.mu | 0.38 | 0.38 | yes | code/alliance.py:818; code/lit.py:186; code/lit.py:193; code/alliance. | yes | SOURCED | 6 | S3c_dry_ground, S3d_rough (lit family) |
| H8 | lit_scenarios.list.REALISTIC.mixed.long.mu; alliance.track_m | [0.1, 0.1] | 0.1 | yes | code/alliance.py:243; code/alliance.py:1255 | yes | SOURCED | 4 | S3a_rails_tallow, S3b_rails_grease (lit family); A4/A5 track |
| H9 | lit_scenarios.list.REALISTIC.mixed.long_min_haul_m | 1000 | 1000 | yes | code/lit.py:188; code/census_v12.py:229 | yes | Authors' assumption (agent's design choi | 0 |  |
| H10 | paths.cost_raster; lit_scenarios.baseline_mu | ["costsurface/sardinia_drag_cost_8dir_mu | 0.3 | yes | code/lit.py:150; code/tools/kbest_quarries.py:96 | yes (via cache: k-best routes  | Authors' assumption (agent's design choi | 0 |  |
| H11 | (code) tools/build_cost_mu.py | (not a config key) | formula | yes | code/tools/build_cost_mu.py:42; code/tools/build_cost_mu.py:57 | yes (via cache: cost rasters i | SOURCED | 0 |  |
| H12 | alliance.relay_fractions; alliance.relay_min_flatm | [[0.25, 0.5, 0.75], 300] | 0.25/0.5/0.75; 300 | yes | code/alliance.py:137; code/alliance.py:1432; code/alliance.py:1546 | yes | Authors' assumption (agent's design choi | 0 |  |
| H13 | scenarios.split_cost_mh | 1.0 | 1.0 | yes | code/alliance.py:297 | yes | Authors' assumption (agent's design choi | 0 |  |
| H14 | MR:join_hands_per_block | {"quarry": 4, "dress": 2, "build": 6} | quarry 4, dress 2, build 6 | yes | code/alliance.py:1363 | yes | SOURCED | 6 |  |
| K1 | stone_rule; allowed_stones | ["hybrid", ["limestone/marble", "metamor | hybrid | yes | code/preprocess.py:34; code/preprocess.py:236; code/preprocess.py:333 | yes (via cache: sites_haul.csv | Authors' assumption (specified by M. Alt | 0 | S5b_any_buildstone (lit family) |
| K2 | alliance.k_quarries | 5 | 5 | yes | code/tools/kbest_quarries.py:96 | yes (via cache: cache/alliance | Authors' assumption (agent's design choi | 0 |  |
| K3 | alliance.setup_mh | 200 | 200 | yes | code/alliance.py:1448; code/alliance.py:1508 | yes | Authors' assumption (agent's design choi | 0 | A0_verify (setup 0) |
| A1 | alliance.R_m | 10000 | 10000 | yes | code/alliance.py:181; code/alliance.py:1936 | yes | Authors' assumption (agent's design choi | 0 | A5_SENSITIVITY_27cells (R 5 / 10 / 20 km on A5_full) |
| A2 | alliance.max_asks | 3 | 3 | yes | code/alliance.py:1100; code/alliance.py:1168 | yes | Authors' assumption (agent's design choi | 0 |  |
| A3 | alliance.trust0; alliance.delta_up; alliance.delta_down | [0.5, 0.1, 0.2] | 0.5 / 0.1 / 0.2 | yes | code/alliance.py:1021; code/alliance.py:1125; code/alliance.py:1127 | yes | Authors' assumption (agent's design choi | 0 |  |
| A4 | alliance.beta0; alliance.beta1; alliance.beta2; alliance.bet | [0.0, 2.0, 0.05, 0.2] | 0 / 2 / 0.05 / 0.2 | yes | code/alliance.py:1108; code/alliance.py:1109 | yes | Authors' assumption (agent's design choi | 2 | A1_ask (fixed acceptance 0.5) |
| A5 | alliance.alliance_threshold | 0.7 | 0.7 | yes | code/alliance.py:1024 | yes | Authors' assumption (agent's design choi | 0 |  |
| A6 | alliance.epsilon | 0.1 | 0.1 | yes | code/alliance.py:1235 | yes | SOURCED | 0 |  |
| A7 | alliance.alpha | 0.5 | 0.5 | yes | code/alliance.py:1627 | yes | Authors' assumption (agent's design choi | 0 |  |
| A8 | alliance.p_imit | 0.3 | 0.3 | yes | code/alliance.py:1212 | yes | Authors' assumption (agent's design choi | 0 |  |
| A9 | MR:help_mode; MR:specialisation | ["join", true] | rule | yes | code/alliance.py:1467; code/alliance.py:1202; code/alliance.py:1413 | yes | Authors' assumption (agent's design choi | 6 | A1-A5 families (handover help, with / without specialisation |
| S1 | MR:sea_kn | 2 | 2 | yes | code/alliance.py:1854; code/alliance.py:1899; code/model.py:255 | yes | SOURCED | 0 | S9_sea_2kn/4kn/5kn/6kn, high_sea (cooperation); A*_sea, P_*_ |
| S2 | sea.payload_kg | 2000 | 2000 | yes | code/alliance.py:296; code/sea.py:27; code/sea.py:28 | yes | SOURCED | 0 |  |
| S3 | sea.crew | 10 | 10 | yes | code/sea.py:27; code/tools/sea_routes.py:162 | yes | DERIVED | 0 |  |
| S4 | sea.transfer_h | 0.25 | 0.25 | yes | code/sea.py:26; code/sea.py:39; code/tools/sea_routes.py:161 | yes | Authors' assumption (agent's design choi | 0 |  |
| S5 | sea.sea_band_m; sea.coast_band_m; sea.land_band_m; sea.beach | [2000, 2000, 5000, 10, 10, 5, 2000, 0.25 | various | yes | code/tools/sea_routes.py:238; code/tools/sea_routes.py:246; code/tools | yes (via SEA_TABLES, queue ent | Authors' assumption (agent's design choi | 0 |  |
| X1 | MR:max_seasons | 20000 | 20000 | yes | code/alliance.py:551 | yes | Authors' assumption (agent's design choi | 0 |  |
| X2 | seeds | {"first": 1, "last": 100} | 1-100 | yes | code/model.py:498 | yes | Authors' assumption (agent's design choi | 0 | entries with their own --seeds:  |

### Keys acting on MR_P10 that are not audited rows

Scan of the resolved MOST_REALISTIC_AUDITED_LIT_P10 dict plus the global transport / stone / lit_scenarios / sea / alliance / scenarios blocks and top-level keys. Not in the audit and acting on MR_P10 (parameters, not switches or data): **6**: sea.sea_grid_factor = 3; sea.attach_radius_blocks = 2; sea.people_max_h = 6.0; rasterize_all_touched = false; nodata_snap_radius_cells = 20; unreachable_policy = local_min_haul. The rest are switches (documented in PARAM_AUDIT Part 2), data fields, or keys that do not act on MR_P10.

| key | acts_on_MR_P10 | code_reads | note |
|---|---|---|---|
| MR:requests / MR:trust / MR:specialisation | yes | code/alliance.py:1202; code/alliance.py:1413 | behaviour switches; documented in PARAM_AUDIT Part 2 (B1 rows 1a, 4a, 13), not a Part 1 parameter row |
| MR:tech_rules = REALISTIC | yes | code/alliance.py:1868; code/alliance.py:1904 | selects the per-site literature rules; its parameters are audited row by row (Q3, Q4, G8, H7-H9, B7-B11, G9) |
| MR:imitation = true (alliance.defaults.imitation) | yes | code/alliance.py:1212 | switch for A8 p_imit; Part 2 B1 row 4c |
| MR:tracks / shared_quarry = false, defector_frac = 0.0, track_cost_mh_per_m = 2.0 | no (switched off) | code/alliance.py:1532; code/alliance.py:1830 | A4/A5 mechanisms off in MR; track_cost acts only with tracks |
| lit_scenarios.fine_min_towers = 2 | yes (non-binding) | code/alliance.py:917; code/alliance.py:919; code/lit.py:112 | gate for fine facing (tw >= 2) in lit.stage_hours / alliance._swap_stage_rates; REALISTIC already requires >= 3 towers (Q4), so it never binds in MR |
| lit_scenarios.list.REALISTIC.density / learning = true | yes | code/alliance.py:312 | switch S6 density (B7-B11) and S8 learning (G9) on in MR |
| lit_scenarios.list.REALISTIC.mixed.type_field = TYPE | yes | code/lit.py:194 | data field naming the site type used by the lift rule (G8) and S11 |
| lit_scenarios.list.REALISTIC.mixed.short.haul / long.haul = mu0.38 / mu0.1 | yes (via cache) | (none found) | haul tables cache/haul/sites_haul_mu0.38.csv and _mu0.1.csv (runs/2026-10-29-bugfix); same mu as H7 / H8 |
| v11.webster_day_fix = true | yes | code/alliance.py:1893; code/lit.py:87; code/model.py:297 | switch for T5 (Webster man-days at 5 h / 8 h); Part 2 B1 row 10c |
| sea.extra_speeds_kn = [2] | yes (via SEA_TABLES) | code/tools/sea_routes.py:526 | makes tools/sea_routes.py build the 2-kn tables MR uses (S1 sea_kn 2) |
| sea.sea_grid_factor = 3 | yes (via SEA_TABLES) | code/tools/sea_routes.py:229 | boats routed on 90 m blocks; block = water if >= 50% sea cells. NOT in the audit (S5 lists bands, beach, hoist, walk, embark only) |
| sea.attach_radius_blocks = 2 | yes (via SEA_TABLES) | code/tools/sea_routes.py:263 | a landing attaches to water within 2 blocks (180 m). NOT in the audit |
| sea.people_max_h = 6.0 | yes (via SEA_TABLES) | code/tools/sea_routes.py:483 | people sea journeys > 6 h are not tabulated. NOT in the audit |
| sea.dem / sea.slope | yes (via SEA_TABLES) | code/tools/sea_routes.py:238 | input rasters (GLO30 DEM, slope); data, not parameters |
| sea.boat_pull_kg_per_person (absent -> transport.pull_kg_per_person 100) | yes | code/sea.py:27 | boat crew factor = crew x pull / payload (sea.py:27); falls back to H3 |
| stones4 / lithology_field / materiale.map (token -> stone class) | yes (via cache) | code/preprocess.py:173 | the recorded-stone token map (e.g. Porfido -> granite + other intrusive; Scisto -> schist allowed for those sites) feeds the hybrid rule (K1) but is not itself an audited row |
| rasterize_all_touched = false | yes (via cache) | code/preprocess.py:73; code/preprocess.py:222 | outcrop rasterisation (cell-centre rule) in preprocess.py; NOT in the audit |
| nodata_snap_radius_cells = 20 | yes (via cache) | code/preprocess.py:106; code/preprocess.py:245; code/tools/kbest_quarries.py:135 | site snapping to valid cells (preprocess.py, tools/kbest_quarries.py); NOT in the audit |
| unreachable_policy = local_min_haul | yes (via cache) | code/preprocess.py:143 | 6 San Pietro sites kept with a local quarry at min_haul_flatm; NOT in the audit |
| alliance.kbest_max_settle = 3000000 | yes (via cache) | code/tools/kbest_quarries.py:127; code/tools/kbest_quarries.py:139 | search cap of the k-best face search (technical) |
| alliance.max_ranks = 8 | no (technical) | code/alliance.py:1967 | MPI ranks; results are per seed and rank-independent |
| alliance.start_rate, alliance.max_seasons = 3000 | no | code/alliance.py:1681 | start_rate replaced by P10 cohorts; max_seasons overridden by MR 20000 (X1) |
| builders.* (base 50, per_extra_tower 25, rand 0.9-1.1, min 50, max 200) | no | code/alliance.py:324; code/model.py:208 | MR uses builders_rule; base is computed (alliance.py:318) but unused; X_nurtime overrides builders_rule with this schema |
| lit_scenarios.webster_md_per_tower.transport = 1100 | no | code/alliance.py:734; code/alliance.py:918; code/lit.py:96 | never used as labour (hauling is simulated) |
| lit_scenarios.ramp.* | no (MR_P10); yes for S4b, S4d, S4e, X_nurtime ramp | code/lit.py:52; code/census_v12.py:153 | ramp earth rates and geometry act only with a ramp lift |
| lit_scenarios.oxen.*, complex_far_*, webster_classes, duration.*, community_threshold_ph, defaults.*, baseline_mu | no (MR_P10) | (none found) | lit-family scenarios / reporting only; defaults are overwritten by REALISTIC.mixed |
| census_v12.*, cz_*, gaps_*, wl_* anchors | no (MR_P10); yes in the census / gaps / WL scenarios | code/census_v12.py:136 | parameters of single switches; each queued switch is listed in PARAM_TRACE 'queued MR scenarios varying' |
| other_mandays_per_tower, max_days, verify.*, scenarios.help_radius_m / help_walk_ms / coupled_max_ranks | no | code/model.py:300; code/model.py:303 | model.py cooperation family / verification only |

## 3. Literature alternatives -> queue (LIT_ALT_COVERAGE.csv)

146 alternatives. Covered by a queued entry now: **83** = COVERED 54 (on the MR family, incl. the audited baseline) + APPROX 4 + PARTIAL 14 (with a second change or another mechanism) + OTHER-FAMILY 11 (lit / cooperation / TOST / A5 sensitivity only). Not covered: **63** = UNCOVERED 57 + NOT-QUEUED 3 (only obsolete or v10 runs) + NEEDS-CODE 3. LIT_ALTERNATIVES.md counted 58 uncovered against the pre-audit queue; the audited values (now the baseline) and the 7 LOO runs (added later) changed the picture: drag 0.6 is now covered by LOO_drag, height 15 / top 8 only jointly by LOO_geometry.

| row | label | value | realism | coverage | queued | note |
|---|---|---|---|---|---|---|
| 1 | drag_press0.6 | 0.6 | 2 | COVERED | MOST_REALISTIC_LOO_drag_P10 | leave-one-out config copy config_full_audited_loo_drag.yaml (own 0.6 m/s sea tab |
| 2 | drag_harris_peak1.0 | 1.0 | 1 | COVERED | MR_P10_v12_drag10 | config copy config_full_audited_drag10.yaml |
| 3 | drag_press_mph0.447 | 0.447 | 2 | PARTIAL | MOST_REALISTIC_C1_all_slow_P10 | with Harris crews (100 kg per person on mu 0.3 moves) |
| 4 | drag_boswinkel_walk0.83 | 0.83 | 2 | UNCOVERED |  |  |
| 5 | drag_power_hertzberg0.355 | 0.355 | 4 | UNCOVERED |  |  |
| 6 | drag_dehaan0.27 | 0.27 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline (all entries) |
| 7 | drag_power_dehaan0.19 | 0.19 | 3 | UNCOVERED |  |  |
| 8 | drag_oxwagon0.46 | 0.46 | 1 | PARTIAL | MOST_REALISTIC_S24_carts_P10 | 0.464 m/s is the loaded ox-wagon speed of S24 (complexes, routes > 1 km), not a  |
| 9 | drag_dehaan_test0.9 | 0.9 | 1 | UNCOVERED |  |  |
| 10 | drag_lipo_walk0.042 | 0.042 | 1 | COVERED | MOST_REALISTIC_M4_1t_P10; MOST_REALISTIC_M4_any_P10 |  |
| 11 | pull_RW_30kgf | 30 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 12 | pull_RW_exp38kgf | 38 (31-46) | 3 | UNCOVERED |  |  |
| 13 | pull_dehaan20kgf | 20 | 3 | UNCOVERED |  |  |
| 14 | pull_sustained125N | 12.7 | 3 | COVERED | MR_P10_v11_pull125 | config copy config_full_audited_pull125.yaml |
| 15 | pull_rankine118N | 12.0 | 2 | APPROX | MR_P10_v11_pull125 | 12.7 kgf queued vs 12.0 |
| 16 | pull_hertzberg_static178N | 18.1 | 1 | UNCOVERED |  |  |
| 17 | pull_harris_10perT | 100 | 3 | COVERED | MOST_REALISTIC_C1_rails_P10; MOST_REALISTIC_C1_all_P10 | also transport.pull_kg_per_person 100 at mu 0.3 in the baseline |
| 18 | pull_harris_relay41.7 | 41.7 | 2 | COVERED | MOST_REALISTIC_C1_rails_relay_P10 |  |
| 19 | pull_atkinson_grass47 | 47 | 3 | UNCOVERED |  |  |
| 20 | pull_dehaan_table2_50 | 50 (34-91) | 3 | UNCOVERED |  |  |
| 21 | pull_atkinson_rollers500 | 500 | 2 | OTHER-FAMILY | S3b_rails_grease | approx. (lit family; mu 0.05 = 600 kg per person) |
| 22 | pull_RW_grease300 | 300 (3.3/t uphill) | 3 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | MR long-rule rails: 30 kgf / mu 0.1 = 300 kg per person; also S3a/S3b (lit) |
| 23 | walk_tobler1.39 | 1.39 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 24 | walk_dehaan1.39 | 1.39 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 25 | walk_murtagh_usual1.31 | 1.31 | 4 | UNCOVERED |  |  |
| 26 | walk_murtagh_medium1.47 | 1.47 | 3 | UNCOVERED |  |  |
| 27 | walk_browning1.42 | 1.42 | 3 | UNCOVERED |  |  |
| 28 | walk_tobler_offpath0.83 | 0.83 | 3 | UNCOVERED |  |  |
| 29 | load_current0.25 | 0.25 h/block | 3 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 30 | load_dehaan0.33 | 0.33 h/block | 2 | UNCOVERED |  |  |
| 31 | load_boswinkel_both0.5 | 0.5 h/block | 2 | UNCOVERED |  |  |
| 32 | load_boswinkel_1.2pht | 1.2 ph/t | 4 | COVERED | MOST_REALISTIC_C3_load_P10; MOST_REALISTIC_C3_all_P10 |  |
| 33 | minhaul_boswinkel100 | 100 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 34 | minhaul_webster200 | 200 | 3 | UNCOVERED |  | C2_sled200 is a per-tonne carry rule for hauls <= 200 m, not a 200 m minimum hau |
| 35 | minhaul_mycenae210 | 210 | 3 | UNCOVERED |  |  |
| 36 | minhaul_mycenae300 | 300 | 2 | UNCOVERED |  |  |
| 37 | mu_dry0.38 | 0.38 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | MR short rule |
| 38 | mu_dehaan0.25 | 0.25 | 3 | UNCOVERED |  | needs a new move-cost table |
| 39 | mu_CK_grass0.25 | 0.25 | 3 | UNCOVERED |  | needs a new move-cost table |
| 40 | mu_dehaan_pavement0.48 | 0.48 | 3 | OTHER-FAMILY | S3d_rough | approx. (lit family, mu 0.5) |
| 41 | mu_dehaan_max0.5 | 0.5 | 3 | OTHER-FAMILY | S3d_rough | lit family |
| 42 | mu_egypt_bare0.55 | 0.55 | 2 | UNCOVERED |  |  |
| 43 | mu_drysand0.57 | 0.57 | 2 | UNCOVERED |  |  |
| 44 | mu_stone_on_stone0.60 | 0.60 | 1 | UNCOVERED |  |  |
| 45 | mu_atkinson_sledge0.19 | 0.19 | 2 | COVERED | MOST_REALISTIC_M3_all_half_P10 |  |
| 46 | mu_fall_wet0.30 / 0.281 / 0.228 | 0.30; 0.281; 0.228 | 2 | COVERED | MOST_REALISTIC_M3_sand26_P10; MOST_REALISTIC_M3_sand40_P10; MOST_REALI | 0.30 = mu 0.3 moves of C1 / the raster |
| 47 | mu_tallow0.1 | 0.1 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | MR long rule |
| 48 | mu_grease0.05 | 0.05 | 3 | OTHER-FAMILY | S3b_rails_grease | lit family |
| 49 | mu_CK_lubricated0.175 | 0.175 (0.15-0.20) | 3 | UNCOVERED |  | needs a new move-cost table |
| 50 | mu_shimotsuma_track0.03 | 0.03 (0.02-0.04) | 2 | UNCOVERED |  | needs a new move-cost table |
| 51 | mu_raster0.3 | 0.3 | 3 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | raster / k-best routes; C1 moves c03 |
| 52 | tonnes_webster1350 | 1350 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 53 | tonnes_trenta800m3 | 1909 (800 m3 × 2386) | 3 | UNCOVERED |  |  |
| 54 | tonnes_geometry1040m3 | 2481 (1040 m3 × 2386) | 2 | UNCOVERED |  |  |
| 55 | tonnes_montalbano842m3 | 2009 | 1 | UNCOVERED |  |  |
| 56 | tonnes_webster_classes | 1350/3100/6700 by class | 3 | OTHER-FAMILY | S7_webster_classes | lit family |
| 57 | tonnes_floor_draw | 0.6/1.0/1.4 × 1350 | 2 | COVERED | MOST_REALISTIC_S25_size_P10 |  |
| 58 | block_webster450 | 450 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 59 | block_lilliu_suNuraxi549 | 549 (0.23 m3 × 2386) | 3 | UNCOVERED |  |  |
| 60 | block_tost300 / block_tost1000 | 300 / 1000 | 2 | OTHER-FAMILY | *_TOST_block_median_kg_min / _max | cooperation family (24 TOST entries over 6 levels) |
| 61 | sigma_extremes0.41 | 0.41 | 3 | UNCOVERED |  |  |
| 62 | sigma_pct0.72 | 0.72 | 3 | UNCOVERED |  |  |
| 63 | sigma_current0.6 | 0.6 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline; TOST 0.3 / 0.9 on the cooperation family |
| 64 | blockmin_webster143 | 143 | 2 | UNCOVERED |  |  |
| 65 | blockmax_lintel3000 | 3000 | 3 | COVERED | MOST_REALISTIC_S20_lintels_3t0_P10 | as an unsplittable 3 t lintel; block_max_kg itself stays 2400 |
| 66 | height_webster_mid14 | 14 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 67 | height_rassu10.8 | 10.8 | 3 | UNCOVERED |  |  |
| 68 | height_webster10 / height_webster18 | 10 / 18 | 3 | UNCOVERED |  |  |
| 69 | height_suNuraxi18.6 | 18.6 | 2 | UNCOVERED |  |  |
| 70 | height_current15 | 15 | 3 | PARTIAL | MOST_REALISTIC_LOO_geometry_P10 | LOO reverts height 15 AND top diameter 8 together (two keys) |
| 71 | base_lilliu10.75 | 10.75 | 4 | UNCOVERED |  |  |
| 72 | base_lilliu88_11.24 | 11.24 | 3 | UNCOVERED |  |  |
| 73 | base_scintu12.5 / 13.3 | 12.5 / 13.3 | 3 | UNCOVERED |  |  |
| 74 | base_webster_mid13.5 | 13.5 | 3 | UNCOVERED |  |  |
| 75 | base_current12 | 12 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 76 | top_batter10.5_6.8 | 6.8 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 77 | top_batter8_8.1 | 8.1 | 3 | PARTIAL | MOST_REALISTIC_LOO_geometry_P10 | top 8.0 (~8.1) but together with height 15 (two keys) |
| 78 | top_batter13_5.5 | 5.5 | 3 | UNCOVERED |  |  |
| 79 | course_measured0.5 | 0.5 (with lever 0.206) | 3 | UNCOVERED |  | two keys (course height + lever rate) must change together |
| 80 | rho_basalt3000 | 3000 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 81 | rho_basalt2386 | 2386 | 1 | OTHER-FAMILY | webster and lit scenarios without S6 | lit family |
| 82 | rho_basalt2300 | 2300 | 1 | UNCOVERED |  |  |
| 83 | rho_basalt2750 | 2750 (2700-2800) | 2 | UNCOVERED |  |  |
| 84 | rho_granite2700 | 2700 | 5 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 85 | rho_granite2750 | 2750 | 3 | UNCOVERED |  |  |
| 86 | rho_lime2420 / rho_marble2711 | 2420 / 2711 | 3 | UNCOVERED |  |  |
| 87 | rho_meta2600 / 2800 | 2600 / 2800 | 3 | UNCOVERED |  |  |
| 88 | hard_hurst1.83 | 1.83 | 3 | NEEDS-CODE |  | separate dressing hardness factor |
| 89 | hard_marble5 | 5 | 1 | UNCOVERED |  |  |
| 90 | hard_current2 | 2 | 3 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | S6 hardness in MR |
| 91 | day_mixed5588 | {5, 5, 8, 8} | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 92 | day_all5 | 5 for dress and build | 2 | COVERED | MOST_REALISTIC_C2_day5_P10 |  |
| 93 | day_all8 | 8 everywhere | 2 | NOT-QUEUED |  | v10 runs only (webster_day_fix false) |
| 94 | wall_erasmus10.5 | 10.5 | 3 | COVERED | MOST_REALISTIC_C2_wall_P10 |  |
| 95 | wall_hurst6.29 / wall_devolder10 / wall_devolder7.85 | 6.29 / 10.0 / 7.85 | 3 | COVERED | MOST_REALISTIC_C3_set_low_P10; MOST_REALISTIC_C3_set_high_P10; MOST_RE |  |
| 96 | wall_mayes29 | 29.4 (blocks ≤ 0.2 m3) | 2 | UNCOVERED |  |  |
| 97 | quarry_devolder11.1 | 11.1 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 98 | quarry_abrams17.5 | 17.5 | 3 | COVERED | MOST_REALISTIC_C3_quarry_P10; MOST_REALISTIC_C3_all_P10 | also S1b_joints_high (lit) |
| 99 | quarry_brysbaert10 | 10.0 | 3 | UNCOVERED |  |  |
| 100 | quarry_abrams_high8.8 | 8.8 | 2 | UNCOVERED |  |  |
| 101 | quarry_erasmus4.4 | 4.4 | 2 | OTHER-FAMILY | webster | lit family (Webster quarry stage) |
| 102 | scree_abrams1.56-2.13 | 1.85 | 4 | APPROX | MOST_REALISTIC_AUDITED_LIT_P10 | scree 2.0 in MR off-outcrop rule lies in 1.56-2.13 |
| 103 | dress_increment90.65 | 90.65 | 3 | APPROX | MOST_REALISTIC_AUDITED_LIT_P10 | audited midpoints give 131.2 - 40.95 = 90.25 (listed 90.65 = old midpoints); neg |
| 104 | dress_C3_59.5 / dress_hurst57 / dress_devolder62 | 59.5 / 57 / 62 | 4 | COVERED | MOST_REALISTIC_C3_dress_P10; MOST_REALISTIC_C3_all_P10 | 59.5 (57 and 62 are its range ends) |
| 105 | dress_pegoretti75 / dress_klapisch182 | 75 / 182 | 1 | UNCOVERED |  |  |
| 106 | facing_blockdepth0.5 | 0.5 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 107 | lever_hodges0.37 | 0.37 | 3 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 108 | lever_masscaled | 0.37 × m/2500 kg | 3 | PARTIAL | MOST_REALISTIC_S4_graded_rate_P10 | queued scaling is 0.37 x m / 450 kg (census_v12.lift_ref_kg), not m / 2500 kg |
| 109 | ramp_loader0.2 | 0.2 | 3 | COVERED | MOST_REALISTIC_S4e_laner_h3_P10; MOST_REALISTIC_S4e_laner_h4_P10 | slope 0.2 on MR; also S4b_ramp (lit) |
| 110 | ramp_surachi0.12 | 0.12 | 3 | COVERED | MOST_REALISTIC_S4d_spiral_7m5_P10; MOST_REALISTIC_S4d_spiral_full_P10 |  |
| 111 | ramp_dehaan0.3 / ramp_brysbaert0.1 | 0.3 / 0.1 | 2 | UNCOVERED |  |  |
| 112 | ramp_laner3m / 4m | ramp to 3 / 4 m | 3 | COVERED | MOST_REALISTIC_S4e_laner_h3_P10; MOST_REALISTIC_S4e_laner_h4_P10 |  |
| 113 | rampw_boswinkel4 / rampw_laner2 | 4 / 2 | 3 | UNCOVERED |  |  |
| 114 | earth_boswinkel1500 / earth_terracruda1700 | 1500 / 1700 | 3 | UNCOVERED |  |  |
| 115 | b_wright0.80 | 0.80 | 3 | UNCOVERED |  |  |
| 116 | b_wright_combined0.83-0.90 | 0.85 / 0.95 / 1.0 | 3 | OTHER-FAMILY | A5_SENSITIVITY_27cells | A5_full factorial, 10 seeds; 0.85 = MR baseline |
| 117 | learn_current0.15 | 0.15 | 2 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | S8 in MR; also S8_learning (lit) |
| 118 | learn_wright_unit | factor i^log2(0.85) | 3 | NEEDS-CODE |  | Wright per-unit form |
| 119 | hours8 | 8 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 120 | hours5 / hours10 | 5 / 10 | 3 / 2 | OTHER-FAMILY | *_TOST_hours_per_day_min / _max | cooperation family at 6 / 10 h; 5 h not run |
| 121 | season90 | 90 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 122 | season40 / 45 / 60-100 / 75 / 120 | 40; 45; 80 (60-100); 75; 120 | 3 | NOT-QUEUED |  | 40 / 120-day runs of 29 Oct are obsolete (pre-fix code) |
| 123 | season220 / 290 / 328 | 220; 290; 328 | 1 | NOT-QUEUED |  | 210-day run of 29 Oct obsolete |
| 124 | sea_HF2kn | 2 | 3 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | MR sea 2 kn; also S9_sea_2kn (cooperation) |
| 125 | sea_HF_paddled0.67kn | 0.67 (0.54-0.81) | 3 | UNCOVERED |  | needs a 0.67-kn sea table |
| 126 | sea_unladen5kn / sea_PI4-6kn / sea_doran10kn | 5; 4-6; 10 | 2 | OTHER-FAMILY | S9_sea_4kn; S9_sea_5kn; S9_sea_6kn; S9_alliance_sea_6; S9_pre_sea_5; G | cooperation / A* / pre-network families; 10 kn not run |
| 127 | crew_HF10 / crew_severin7 | 10 / 7 | 3 | PARTIAL | MOST_REALISTIC_AUDITED_LIT_P10 | crew 10 = baseline; crew 7 uncovered |
| 128 | payload_HF2000 | 2000 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 129 | transfer0.25 | 0.25 | 2 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 130 | hands_hodges6 | 6 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 131 | hands_dozen12 | 12 | 3 | UNCOVERED |  |  |
| 132 | hands_RW4 / hands_lipo6 | 4 / 6 | 2 | PARTIAL | MOST_REALISTIC_AUDITED_LIT_P10 | quarry 4 = baseline; 6 uncovered |
| 133 | hands_dress2 | 2 | 2 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 134 | split1.0 | 1.0 | 2 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline |
| 135 | setup200 / setup0 | 200 / 0 | 3 | PARTIAL | A0_verify | 200 = baseline; 0 only in A0_verify (A family) |
| 136 | pop_lilliu30 | flat 30 | 2 | PARTIAL | MOST_REALISTIC_POP_lilliu30_P10 | queued with adult_share 0.5 (audited baseline 0.4): two changes |
| 137 | pop_webster_household | TWR1 5-6 | 3 | PARTIAL | MOST_REALISTIC_POP_webster_household_P10 | adult_share 0.5: two changes |
| 138 | pop_webster_density | flat 34-40 | 2 | PARTIAL | MOST_REALISTIC_POP_webster_density_P10 | adult_share 0.5: two changes |
| 139 | pop_webster_density_voronoi | 10-12/km2 x Voronoi cell | 3 | NEEDS-CODE |  | Voronoi population allocation |
| 140 | pop_calo_6km2 | MR x 0.4985 | 2 | PARTIAL | MOST_REALISTIC_POP_calo_6km2_P10 | adult_share 0.5: two changes |
| 141 | pop_ugas_high | MR x 1.897 (x1.38 / x2.41) | 2 | PARTIAL | MOST_REALISTIC_POP_ugas_high_P10; MOST_REALISTIC_POP_ugas400_P10; MOST | adult_share 0.5 and no ceiling: two-three changes |
| 142 | pop_anchored | 5-40 / 70-320 / 80-350 / 85-37 | 3 | PARTIAL | MOST_REALISTIC_POP_anchored_P10 | adult_share 0.5: two changes |
| 143 | adult_webster_men0.2 | 0.2 | 2 | COVERED | MOST_REALISTIC_POP_men_only_P10 | one change vs audited baseline |
| 144 | adult_derived0.4 | 0.4 | 4 | COVERED | MOST_REALISTIC_AUDITED_LIT_P10 | audited baseline (MOST_REALISTIC_POP_adult04_P10 is a duplicate of it) |
| 145 | adult_abrams0.2-0.33 | 0.27 | 2 | APPROX | MOST_REALISTIC_POP_men_only_P10 | 0.2 = lower end of 0.2-0.33 |
| 146 | adult_wunderlich0.6 | 0.6 | 2 | COVERED | MOST_REALISTIC_POP_adult06_P10 | one change vs audited baseline |

## 4. Scenario provenance relabel (specified by the authors)

SCENARIO_PROVENANCE_v2.csv = SCENARIO_PROVENANCE.csv with every non-literature origin set to "Authors' idea" (specified by the authors), in `origin` and `idea_group_origin`; the old labels are kept in `origin_v1` / `idea_group_origin_v1`, and the former 'literature-anchored' qualifier in `origin_anchoring`. Rows: 502; origin now: Authors' idea 389, Literature (comparative) 36, Literature 77; literature-anchored 62. This includes MOST_REALISTIC, REALISTIC and S8_learning (previously 'Agent's design choice, accepted by the authors, literature-anchored'). Parameter labels in PARAM_AUDIT are unchanged.

