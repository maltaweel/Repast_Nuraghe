# Audited literature parameter checks

Nuraghe-construction ABM, v12 code (the version to be frozen). Headline scenario MOST_REALISTIC_P10. 2 November 2026.

## What this is
This audit checks every parameter that acts on the headline scenario, and every behaviour (mechanism) the model uses, against the published literature. For each parameter we record:
- the value;
- what it does;
- the source stated so far;
- its evidence status before the audit;
- what the literature says;
- its status after the audit;
- the proposed action.

The adopted values form a separate audited parameter set, AUDITED_LIT (specification, single-change runs and the combined run in AUDITED_LIT_SPEC.md). The current results stay as they are. Each changed value gets one MR_P10 run with only that value changed (MOST_REALISTIC_AUD_<parameter>_P10), and one combined run gets all of them (MOST_REALISTIC_AUDITED_LIT_P10). The population settings are decided from the population runs (POPULATION_SCENARIOS.md). Part 1 covers parameters; Part 2 covers behaviours. The population evidence is in POPULATION.md, and the optional literature alternatives (other published values, one at a time) are in the appendix, LIT_ALTERNATIVES.md.

## Method
- **Inventory.** Every parameter read by the code path of MOST_REALISTIC_P10, taken from the v12 configuration and code, the methods notes, the paper draft (Tables A1-A2) and the census of construction ideas. Parameters that exist in the configuration but do not act on the headline are listed separately.
- **Literature.**
  - The Nurnet Catalogue (public and copyrighted works), searched in Italian and English. Copyrighted works are quoted only in short passages, with author and year.
  - Open-access primaries found by web search. No person's identity was used in any query.
  - The project's earlier reviews and census, re-checked where a page was needed.
  - Sardinian sources first. Where none exist, published comparative work from other megalith-building contexts and from ethnography (Stonehenge, Mycenae, Egypt, Rapa Nui, Micronesia) and the general ABM literature. These are labelled "comparative (non-Sardinian)". They count as sources.
- **Evidence rules.**
  - A figure is SOURCED only if it was read at a page in the primary text. Otherwise it is REPORTED-ONLY, and the reporter is named.
  - Confirming a citation is not confirming a number.
  - Measurement and experiment are kept apart from opinion.

## Status categories
| Status | Meaning |
|---|---|
| SOURCED | Read at a page in the primary text (author, year, page). Comparative sources are marked as such. † = read in the primary, but the Catalogue excerpt prints no page; confirm the page before publication |
| REPORTED-ONLY | Known only from a second author, who is named (e.g. "Erasmus 1965: 283 via Boswinkel 2021: 145") |
| DERIVED | Computed by us from sourced numbers; the derivation is given |
| Authors' assumption (specified by the authors) | No published source; the value or rule is the principal investigator's specification, quoted with date and time |
| Authors' assumption (modelling agent's design choice, accepted by the authors) | No published source; chosen by the modelling agent, reported to the principal investigator and not contested |

Actions:
- **keep**: already sourced;
- **replace**: a sourced value replaces the current one in AUDITED_LIT (source and value given);
- **relabel only**: the value stays, its status changes;
- **keep as Authors' assumption**: no published source exists, and the reason is given.

## Main findings
1. **Nine values change in AUDITED_LIT.** The other 61 parameters stay; 16 of them are relabelled with a source found by this audit.
   - Large effect:
     - **drag speed 0.6 → 0.27 m/s.** The 0.6 was a press figure. The primary experiment (Harris 2016) gives only a 1 m/s peak. de Haan 2009: 7 gives about 980 m/h, calculated (power-based) at the same 200-300 N per person that the model uses (comparative; not a measurement).
     - **adult share 0.5 → 0.4.** Webster 1991: 854, "Men available = population/5", with an equal number of adult women.
   - Small effect: tower height 15 → 14 m and top diameter 8 → 6.8 m, basalt density 2,950 → 3,000 and granite 2,650 → 2,700 kg/m³.
   - Negligible (rounding to the source): joints_low 11.0 → 11.1 ph/m³, walk 1.4 → 1.39 m/s, facade/cyclopean midpoints 131.5 / 40.85 → 131.2 / 40.95.
2. **The population ceiling (300,000) is SOURCED** (Calò et al. 2008: 41, read). The sentence in Calò is uncited, and it never binds under P10. The model's island total, about 290,000 residents (40.5 per nuraghe), sits in the middle band of the published estimates (100,000-700,000; POPULATION.md).
3. **Two source corrections.**
   - Duos Nuraghes housed about 70 people, not 70-110.
   - The canton figures attributed to "Ugas in Moravetti et al. 2009, p. ~361" come from a Catalogue item that cannot be by those authors in 2009, because it cites works of 2017. Its passages recur in the self-published Atzeni & Frau 2023 compilation. The figures stay REPORTED-ONLY until Ugas's own page is read. Ugas 2005: 40 itself gives just under 800 cantons, against the 2,700 seats in the compilation.
4. **About 28 parameters have no published source at all.** They stay Authors' assumptions, with reasons:
   - the social parameters (help radius, asks, trust, acceptance, learning step, imitation);
   - block clipping, lift share, the stair rule, the rails threshold, the raster μ, split and setup costs, and sea transfer time.

## Counts per status (70 parameter rows: those acting on MOST_REALISTIC_P10, plus household size, which acts only outside it, and two technical settings)
| Status | Before | After |
|---|---:|---:|
| SOURCED | 14 | 26 |
| REPORTED-ONLY | 5 | 2 |
| DERIVED | 3 | 11 |
| Authors' assumption (specified by the authors) | 4 | 3 |
| Authors' assumption (modelling agent's design choice, accepted by the authors) | 44 | 28 |
| **Total** | 70 | 70 |

Actions: keep 19; relabel only 16; replace 9; keep as Authors' assumption 26.

# Part 1. Parameters

| id | Config key | MR_P10 value | What it does | Stated source (before) | Status before | Literature found (author, year, page) | Status after | Proposed action | AUDITED value (adopted) |
|---|---|---|---|---|---|---|---|---|---|
| P1 | `alliance_extra.MOST_REALISTIC.builders_rule.residents_by_towers (mr_work_party)` | [5,40],[40,110],[110,185],[185,260],[260,330],[330,400],[330,400] | Residents per nuraghe, drawn U[lo,hi] by tower count | Webster 2015: 51; Webster 1991: 853; Webster & Webster 1998 (Duos 70-110); Ugas via a secondary source; interpolation ours | DERIVED | Anchors read: 5 per homestead (Webster 1991: 854, Table 2 n. 2); 5-6 per tholos (Webster 1996); Borore village <= 40 (Webster 1991); Duos about 70, NOT 70-110 (Webster & Webster 1998; Webster 2001); Su Nuraxi about 90 (Lilliu & Zucca 2005) / 95-110 (Webster 1996); Palmavera 240-320 (Webster 1996 after Moravetti 1992a); Porcarzos about 400 (Webster 1991: 853). See POPULATION.md | DERIVED | relabel only (correct the Duos anchor; the 110 bound of TWR2 has no anchor); alternatives in the population family | [5,40],[40,110],[110,185],[185,260],[260,330],[330,400],[330,400] |
| P2 | `mr_work_party.adult_share` | 0.5 | Builders = round(share x residents) | ASSUMPTION (adults of both sexes) | Authors' assumption (modelling agent's design choice, accepted by the authors) | Webster 1991: 854, Table 2 note 4: 'Men available = population/5' (0.2, men only; SOURCED). Equal adult women -> 0.4 (DERIVED). Comparative: Abrams 1987: 493 20-33% (REPORTED-ONLY via Boswinkel 2021: 149); Wunderlich et al. 2024 about 60% (section 7.2) | DERIVED | replace: 0.4 (DERIVED from Webster 1991: 854); bounds 0.2 (Webster literal) and 0.5 (current) | **0.4** (provisional; final from the population runs) |
| P3 | `alliance_extra.MOST_REALISTIC.population_ceiling` | 300000 | Ceiling on residents of simultaneously active communities | Calò et al. 2008: 41, second-hand via Day 1988 | REPORTED-ONLY | Calò et al. 2008: 41 read: 'never exceeded 300,000 inhabitants' prehistory-AD 1700, about 6/km2; the sentence itself is uncited (Day 1988 is on the sentence before, medieval-early modern). Range of literature 100,000-700,000 (POPULATION.md) | SOURCED | relabel only (SOURCED, uncited in Calò; never binds under P10) | 300000 |
| P4 | `scenarios.household_size (not in MR)` | 5 | Households of the cooperation scenarios | Webster 1991 | SOURCED | Webster 1991: 852-854 (5 per homestead); Webster 1996 5-6 | SOURCED | keep (does not act on MR_P10) | 5 |
| T1 | `phase fraction (name suffix _P10)` | 0.1 | 10% cohorts; next starts when all previous are built | specified by the authors | Authors' assumption (specified by the authors) | PI words (specified by the authors). No literature sets cohorts; gradual growth by fission (Webster 1991: 853; Ialongo 2018: 29) | Authors' assumption (specified by the authors) | keep as Authors' assumption (specified by the authors) | 0.1 |
| T2 | `cohort membership` | random per seed | Which sites fall in which cohort | agent design | Authors' assumption (modelling agent's design choice, accepted by the authors) | No chronology used; no source | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | random |
| T3 | `alliance.season_days` | 90 | Communal working days per season; one season = one year | Renfrew 1973 via Webster 1991: 853 | REPORTED-ONLY | specified by the authors. Renfrew 1973: 549 (90 days, emergent chiefdoms) and Erasmus 1965: 280-81 (40 days) both REPORTED-ONLY via Webster 1991: 853; Devolder 2013 90 days via Turner 2020: 81 | Authors' assumption (specified by the authors) | keep (Authors' assumption specified by the authors; literature context REPORTED-ONLY) | 90 |
| T4 | `hours_per_day` | 8 | Working hours per day | ASSUMPTION (standard day) | Authors' assumption (modelling agent's design choice, accepted by the authors) | de Haan 2009: 2, 7 (8 effective hours; SOURCED, comparative); Boswinkel 2021: 145-146 range 5-10 h (SOURCED); Erasmus 1965: 283 'most writers' use 8 h (REPORTED-ONLY via Boswinkel) | SOURCED | relabel only (SOURCED, comparative convention) | 8 |
| T5 | `v11.webster_day_hours` | quarry 5, transport 5, dress 8, build 8 | Converts Webster's man-days to hours at the source's day | Erasmus 1965: 283 via Boswinkel 2021: 145; Abrams via Boswinkel 2021: 109, 146 | REPORTED-ONLY | Same; primaries (Erasmus 1965, Abrams 1984/1994) not obtainable; Webster's Abrams-1984 day length unverified | REPORTED-ONLY | keep (REPORTED-ONLY) | quarry 5, transport 5, dress 8, build 8 |
| B1 | `stone.tonnes_per_tower` | 1350 | Stone mass per tower | Webster 1991: 852 | SOURCED | Webster 1991: 852-853, Table 1 (3,000 blocks, 0.19 m3 median, 2,386 kg/m3; 3,600 man-days per single tower). Caveat: the model's own frustum (12 -> 8 m, 15 m) is about 1,040 m3 net; Trenta 2026 (popular) about 800 m3 | SOURCED | keep (fill volume noted out of scope) | 1350 |
| B2 | `stone.block_median_kg` | 450 | Lognormal median block mass | Webster 1991: 852 | SOURCED | Webster 1991: 852 (75 x 50 x 50 cm, 0.19 m3, about 450 kg); Lilliu 1955 Su Nuraxi face blocks mean about 0.23 m3 | SOURCED | keep | 450 |
| B3 | `stone.block_sigma` | 0.6 | Lognormal sigma of block mass | ASSUMPTION | Authors' assumption (modelling agent's design choice, accepted by the authors) | DERIVED from Webster 1991: 852 range (< 0.06 to 1 m3): 0.41 (range = extremes of 3,000 draws) to 0.72 (2.5/97.5 percentiles) | DERIVED | relabel only (0.6 inside the DERIVED range; the central value depends on an unsourced reading of the range) | 0.6 |
| B4 | `stone.block_min_kg` | 60 | Lower clip | ASSUMPTION | Authors' assumption (modelling agent's design choice, accepted by the authors) | Webster 1991: 852 'less than 0.06 cu. m' (< 143 kg); no lower figure | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 60 |
| B5 | `stone.block_max_kg` | 2400 | Upper clip | ASSUMPTION | Authors' assumption (modelling agent's design choice, accepted by the authors) | Webster 1991: 848, 852: largest blocks about 1 m3, about 2,400 kg (SOURCED via the project review). Lintels 1.5-4 t exist (Webster 2001: 21; Murru 2018: 229) | SOURCED | relabel only (SOURCED) | 2400 |
| B6 | `lit_scenarios.webster_density_kg_m3` | 2386 | Webster's conversion density (S6 scales by rho/2386) | Webster 1991: 852 | SOURCED | Webster 1991: 852 (after Abrams 1984). Low for basalt (Turner 2020: 72) | SOURCED | keep (a scaling constant) | 2386 |
| B7 | `lit_scenarios.density_kg_m3.basalt` | 2950 | Basalt density (S6) | FREE (standard value) | Authors' assumption (modelling agent's design choice, accepted by the authors) | Lilliu 1955 assumes 'peso specifico' 3 (SOURCED, page n.r.); textbook mean 3.00 (2.70-3.30, REPORTED-ONLY); Scintu 2003: 249-250 uses 2,300 | SOURCED † | replace: 3000 (Lilliu 1955; textbook mean) | **3000** |
| B8 | `lit_scenarios.density_kg_m3.granite` | 2650 | Granite density (S6) | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Sanna & Atzeni n.d., Manuale tematico della pietra, Table 6.2 p. 96: 13 Sardinian granites 2,620-2,760, median 2,700 (SOURCED, measurement) | SOURCED | replace: 2700 (Sardinian measurements, median) | **2700** |
| B9 | `lit_scenarios.density_kg_m3.limestone/marble` | 2600 | Limestone density (S6) | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No Sardinian measurement; Turner 2020: 276-279 marble 2,711 (comparative); textbook limestone 2,420 (REPORTED-ONLY) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption (within comparative range) | 2600 |
| B10 | `lit_scenarios.density_kg_m3.metamorphic` | 2750 | Metamorphic density (S6) | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Textbook schist/phyllite/slate/gneiss 2.60-2.80, median about 2.77 (REPORTED-ONLY, no page) | REPORTED-ONLY | relabel only (REPORTED-ONLY textbook) | 2750 |
| B11 | `lit_scenarios.hardness (basalt, granite = 2; others 1)` | 2.0 / 1.0 | Multiplies quarrying and dressing hours | FREE (Turner critique) | Authors' assumption (modelling agent's design choice, accepted by the authors) | Dressing: granite vs limestone 1.83 (Hurst 1905: 382, REPORTED-ONLY via Boswinkel 2021: 120). Quarrying along joints: no ratio found | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption (dressing ratio has comparative support; quarrying none) | 2.0 / 1.0 |
| Q1 | `lit_scenarios.quarry_ph_m3.scree` | 2.0 | Collecting scree off outcrop (ph/m3) | Boswinkel 2021 Table 7.2 | SOURCED | Boswinkel 2021: 108, Table 7.2 (rubble 0.5 m3/ph; Abrams 1994 via Boswinkel) | SOURCED | keep | 2.0 |
| Q2 | `lit_scenarios.quarry_ph_m3.joints_low` | 11.0 | Breaking jointed bedrock on outcrop (ph/m3) | Boswinkel 2021 Table 7.2 | SOURCED | Boswinkel 2021: 108: 0.09 m3/ph -> 11.11 ph/m3 (config rounds) | SOURCED | replace: 11.1 (exact 1/0.09) | **11.1** |
| Q3 | `quarry rule (joints_low on outcrop, scree off)` | rule | Which rate each site uses | agent design (REALISTIC) | Authors' assumption (modelling agent's design choice, accepted by the authors) | Duos quarried under the site (Webster 1991: 848); collected stone (Lilliu & Zucca 2005: 41); rule itself ours | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | rule |
| Q4 | `dress rule (none 1 tower; Webster 2 towers; fine >= 3)` | rule | Dressing per tower class | agent design (REALISTIC) | Authors' assumption (modelling agent's design choice, accepted by the authors) | Simple towers cyclopean (NUR; GEN); fine masonry on complexes (Lilliu & Zucca 2005; Contu 2002: 29-32); thresholds ours | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | rule |
| Q5 | `lit_scenarios.webster_md_per_tower (quarry 500, dress 1300, build 700)` | 500 / 1300 / 700 md | Webster stage man-days per tower | Webster 1991: 852, Table 1 | SOURCED | Webster 1991: 852-853 Table 1 (stage cells read by the project review; total 3,600 md at p. 853 re-read) | SOURCED | keep | 500 / 1300 / 700 md |
| Q6 | `lit_scenarios.facade {facade_ph_m3_mid, cyclopean_ph_m3_mid}` | 131.5 / 40.85 | Extra all-stage cost of fine facing (difference 90.65 ph/m3) | Boswinkel 2021: 144, Table 8.3 | DERIVED | Boswinkel 2021: 144 Table 8.3: facade 95.7-166.7, cyclopean 6.7-75.2 -> exact midpoints 131.2 / 40.95 | DERIVED | replace (rounding): 131.2 / 40.95 | **131.2 / 40.95** |
| Q7 | `lit_scenarios.facing_thickness_m` | 0.5 | Depth of the fine-dressed facing | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Webster 1991: 852 median block depth 0.50 m; Lilliu 1955 assumes 0.50 m depth for face blocks | DERIVED | relabel only (DERIVED: one block deep) | 0.5 |
| G1 | `lit_scenarios.geometry.tower_height_m` | 15 | Tower height (mass by course, lift, ramp) | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Webster 1991 (pp. 842-847, page not printed in the excerpt): tholos towers '10-18 m in height if they have an upper storey'; Melis 2017: 37 chamber 11-12 m; Tran et al. 2025: 800 about 12 m | SOURCED † | replace: 14 (midpoint of Webster's 10-18 m) | **14** |
| G2 | `lit_scenarios.geometry.base_diam_m` | 12 | Base diameter | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Lilliu 1955: 68 mean 10.75 m; Contu 2002 10.75 m; Scintu 2003: 43 modes 12.5 / 13.3 m; Webster 1991 11-16 m; median of the central values 11.9 | DERIVED | relabel only (DERIVED median 11.9 ~ 12) | 12 |
| G3 | `lit_scenarios.geometry.top_diam_m` | 8 | Top diameter | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Contu 2002 measured batter 8-13 deg; top = base - 2 h tan(10.5 deg) = 6.8 m at h = 14 | DERIVED | replace: 6.8 (DERIVED from Contu 2002 batter midpoint) | **6.8** |
| G4 | `lit_scenarios.geometry.course_height_m` | 0.9 | Lift step per course (lever rate unit) | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Measured courses about 0.5 m (Moravetti 1998; Lilliu 1955; Webster 1991: 852), but the lever rate 0.37 ph is defined per 0.9 m lift (Boswinkel 2021: 124) | SOURCED | relabel only (the 0.9 m is Boswinkel's lift step, SOURCED; physical course height noted) | 0.9 |
| G5 | `lit_scenarios.lever_ph_per_block_course` | 0.37 | Person-hours per block per course lifted (lever/stair) | Hodges 1989 / de Haan 2009 via Boswinkel 2021: 116, 124 | SOURCED | Boswinkel 2021: 124 (0.9 m at 0.0041 m/s, 6 people -> 0.37 ph/block; for 2.5 t blocks) | SOURCED | keep | 0.37 |
| G6 | `lit_scenarios.lift_share_of_build` | 0.5 | Share of Webster's building stage that is lifting | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source; Webster's 0.8 m3/md 'includes time for setting up blocks' (1991: 853) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.5 |
| G7 | `lit_scenarios.stair_lever_last_m` | 1.0 | Metres levered per course on the internal stair | FREE (Laner) | Authors' assumption (modelling agent's design choice, accepted by the authors) | Laner 1999: 30, 33 (blocks carried up the stair; six men per 300 kg) gives no time | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 1.0 |
| G8 | `lift rule (lever for corridor nuraghi, stair otherwise)` | rule | Lift method by type | agent design; Laner 1999 | Authors' assumption (modelling agent's design choice, accepted by the authors) | Laner 1999: 30 (intramural stair as builders' ramp; opinion); NUR on corridor nuraghi without tholos stair | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | rule |
| G9 | `lit_scenarios.learning_rate (S8)` | 0.15 | Tower i of a site costs 0.85^i | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No archaeological learning rate found (GEN 91; this audit) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.15 |
| G10 | `alliance.b` | 0.85 | Wright progress ratio per doubling (A3 skill) | Wright 1936 | SOURCED | Wright 1936: 124-126: 80% curve for labour, 83-90% combined (SOURCED, aircraft); 0.85 = midpoint 0.80-0.90 (DERIVED) | DERIVED | relabel only (DERIVED midpoint of Wright's range) | 0.85 |
| H1 | `transport.drag_speed_ms` | 0.6 | Loaded sledge speed | press reports of Harris 2016 (v12: ASSUMPTION) | REPORTED-ONLY | Harris 2016 AAM p. 4: 1 m/s MAXIMUM only (SOURCED). de Haan 2009: 7: sledge speed 'about 980 m/hour' = 0.27 m/s, calculated (power-based) at 200-300 N and 55.5-83.3 W per man (pp. 6-7; SOURCED; comparative; not a measurement). Hertzberg 1972 via Boswinkel 2021: 52: 104 W sustained -> 0.355 m/s at 294 N | SOURCED | replace: 0.27 (de Haan 2009: 7, calculated (power-based), comparative); range 0.19-0.355 (power-derived) | **0.27** |
| H2 | `lit_scenarios.f_person_kgf` | 30 | Pulling force per person (crew = mass x mu / force) | Cotterell & Kamminga 1990: 219, de Haan 2009 via Boswinkel 2021: 47, 52, 111 (peak) | SOURCED | Richards & Whitby 1997: 237 (30 kgf effective per person), 242 (31-46 kgf measured with 130 people); de Haan 2009: 6 (20-30 kg); Harris 2016 crews consistent | SOURCED | keep | 30 |
| H3 | `transport.pull_kg_per_person` | 100 | Load per person at mu 0.3 (sea legs, raster) | press 'about 1 t per 10 people' (v12: ASSUMPTION) | REPORTED-ONLY | = 30 kgf / 0.3 (DERIVED); Harris 2016 AAM p. 4: 10 haulers minimum for about 0.75-1 t (Harris's popular AAM p. 5: 3/4 t) | DERIVED | relabel only (DERIVED from H2) | 100 |
| H4 | `transport.return_walk_ms` | 1.4 | Empty walk back; helper walks | normal walking speed | Authors' assumption (modelling agent's design choice, accepted by the authors) | Tobler 1993 p. 3: 5 km/h on flat = 1.39 m/s; de Haan 2009: 7: 5 km/h empty return; Murtagh et al. 2021: 1.31-1.47 | SOURCED | replace (rounding): 1.39 (Tobler 1993; de Haan 2009: 7) | **1.39** |
| H5 | `transport.load_unload_h` | 0.25 | Load + unload per trip (crew time) | ASSUMPTION | Authors' assumption (modelling agent's design choice, accepted by the authors) | Boswinkel 2021: 116 (15 min per 2.5 t loading operation, after Hodges 1989); de Haan 2009: 7 assumes 20 min (0.3 h) | DERIVED | relabel only (DERIVED, comparative; 0.25 = Boswinkel's per-operation time) | 0.25 |
| H6 | `transport.min_haul_flatm` | 100 | Haul for sites on their outcrop | Webster's local hauls <= 200 m | Authors' assumption (modelling agent's design choice, accepted by the authors) | Boswinkel 2021: 116 (100 m for a local quarry); Webster 1991: 852 (<= 200 m); Duos quarried under the site (Webster 1991: 848) | SOURCED | relabel only (SOURCED comparative analogue) | 100 |
| H7 | `REALISTIC.mixed.short mu (dry ground)` | 0.38 | Sledge friction on dry ground | GEN 64, 201 | SOURCED | Boswinkel 2021: 114, 124 (0.38, midpoint of de Haan 2009: 6 0.25-0.5) | SOURCED | keep | 0.38 |
| H8 | `REALISTIC.mixed.long mu (tallowed rails); alliance.track_mu` | 0.1 | Rails friction on long routes | GEN 65; Richards & Whitby 1997 | SOURCED | Richards & Whitby 1997: 239 (tallow about 0.1) | SOURCED | keep | 0.1 |
| H9 | `REALISTIC.mixed.long_min_haul_m` | 1000 | Routes above this use rails | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source for when rails were laid | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 1000 |
| H10 | `cost raster mu (routes, k-best faces)` | 0.3 | Friction used to build routes and haul costs | ASSUMPTION | Authors' assumption (modelling agent's design choice, accepted by the authors) | Within 0.25 (grass, Cotterell & Kamminga via Boswinkel 2021: 113) to 0.38; Fall et al. 2014 wet-sand optimum 0.3 | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption (comparative support) | 0.3 |
| H11 | `cost raster slope term max(0.5, /mu + tan theta/ / mu)` | formula | Slope cost per flat-metre | drag cost recipe | Authors' assumption (modelling agent's design choice, accepted by the authors) | F = m g (mu cos a + sin a) (Boswinkel 2021: 43-44; Richards & Whitby 1997: 237, SOURCED); the raster omits cos (< 1% below 8 deg); the 0.5 downhill floor has no source | SOURCED | relabel only (slope physics SOURCED; floor stays Authors' assumption) | formula |
| H12 | `relay_fractions / relay_min_flatm` | 0.25/0.5/0.75; 300 | Hand-off points for relay transport | spec / FREE | Authors' assumption (specified by the authors) | PI's mechanism (specified by the authors); values ours | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.25/0.5/0.75; 300 |
| H13 | `scenarios.split_cost_mh` | 1.0 | Man-hours per cut of a heavy block | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No per-split time found | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 1.0 |
| H14 | `alliance.join_hands_per_block (MR)` | quarry 4, dress 2, build 6 | Max hands per block when helpers join | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Build 6: lever crew 4 + 2 (Hodges 1989 via Boswinkel 2021: 116, 124; de Haan 2009: 22); Laner 1999: 33 six men per 300 kg. Quarry 4: lever teams of four (Richards & Whitby 1997: 238), weak. Dress 2: none | SOURCED | relabel only (build SOURCED comparative; quarry weak comparative; dress Authors' assumption); never binds | quarry 4, dress 2, build 6 |
| K1 | `stone_rule hybrid + allowed_stones (7)` | hybrid | Recorded stone, else nearest of 7 classes | specified by the authors | Authors' assumption (specified by the authors) | PI words (specified by the authors); local least-cost stone (Webster 2001: 122-123); Gallin 1989 via Webster 1991: 848 | Authors' assumption (specified by the authors) | keep (Authors' assumption, specified by the authors; literature consistent) | hybrid |
| K2 | `alliance.k_quarries` | 5 | Cheapest distinct faces per site | spec | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 5 |
| K3 | `alliance.setup_mh` | 200 | Man-hours to open a new face | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source; plausibility: soil stripping 1-2 m at Duos (Webster 1991: 848) at 4.2 ph/m3 (Boswinkel 2021: 122) -> 200 ph = 48-60 m3 | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 200 |
| A1 | `alliance.R_m` | 10000 | Radius for requests, relays, imitation | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No help-distance source; canton about 8.9 km2 (Ugas, REPORTED-ONLY); Marghine groups 10-50 km2 (Webster 2001) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 10000 |
| A2 | `alliance.max_asks` | 3 | Candidates asked per task | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 3 |
| A3 | `alliance.trust0 / delta_up / delta_down` | 0.5 / 0.1 / 0.2 | Trust start and updates | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Principle specified by the authors; values: no source | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.5 / 0.1 / 0.2 |
| A4 | `alliance.beta0..beta3` | 0 / 2 / 0.05 / 0.2 | Acceptance logit | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0 / 2 / 0.05 / 0.2 |
| A5 | `alliance.alliance_threshold` | 0.7 | Mutual trust for an alliance (recorded only in MR) | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | No source; no effect on MR labour or time | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.7 |
| A6 | `alliance.epsilon` | 0.1 | Exploration probability | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Sutton & Barto 2018: 28 (epsilon = 0.1 as the standard test value; SOURCED, methodological) | SOURCED | relabel only (methodological convention) | 0.1 |
| A7 | `alliance.alpha` | 0.5 | Value update step | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Sutton & Barto 2018: 32 (constant step size, form only; no value) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.5 |
| A8 | `alliance.p_imit` | 0.3 | Imitation probability per tower | FREE | Authors' assumption (modelling agent's design choice, accepted by the authors) | Gilbert 2020 s. 1.3.6 (concept only) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.3 |
| A9 | `help_mode join + specialisation (A3)` | rule | Helpers add hands; help builds skill | agent design accepted | Authors' assumption (modelling agent's design choice, accepted by the authors) | see Part 2 (behaviours) | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep (behaviour; Part 2) | rule |
| S1 | `sea_kn (MR)` | 2 | Laden craft speed | Hazell & Fitzpatrick 2006: 18 | SOURCED | H&F 2006: 18 (2 kn, laden; comparative, Micronesia); p. 16 paddled 0.54-0.81 kn | SOURCED | keep | 2 |
| S2 | `sea.payload_kg` | 2000 | Stone per craft | H&F 2006: 12, 18 | SOURCED | same | SOURCED | keep | 2000 |
| S3 | `sea.crew` | 10 | Crew per craft | H&F 2006: 18 (800 kg crew) / 80 kg ASSUMPTION | DERIVED | 800 kg / 80 kg per person (80 kg ours); Severin's raft crew 7 (H&F 2006: 17, REPORTED) | DERIVED | keep (DERIVED) | 10 |
| S4 | `sea.transfer_h` | 0.25 | Load/unload at each landing | ASSUMPTION | Authors' assumption (modelling agent's design choice, accepted by the authors) | H&F 2006: 21 exclude loading; no source | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | 0.25 |
| S5 | `sea bands, beach and hoist rules (2 km, 5 km, 10 m / 10 deg, 5 m, 2 km walk, 0.25 h embark)` | various | Where boats can operate and land | specified by the authors; values agent | Authors' assumption (specified by the authors) | PI words (Part 2); the numbers are the agent's translation, accepted | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep as Authors' assumption | various |
| X1 | `max_seasons (MR)` | 20000 | Safety stop | - | Authors' assumption (modelling agent's design choice, accepted by the authors) | technical, never binding | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep (technical) | 20000 |
| X2 | `seeds` | 1-100 | Replicates | - | Authors' assumption (modelling agent's design choice, accepted by the authors) | technical | Authors' assumption (modelling agent's design choice, accepted by the authors) | keep (technical) | 1-100 |

**Parameters in the configuration that do not act on MOST_REALISTIC_P10:**

| Key | Value | Why it does not act |
|---|---|---|
| `alliance.start_rate` | 1/450 | replaced by cohorts under P10 |
| `builders (base 50 + 25/tower)` | default rule | MR uses builders_rule (except X_nurtime) |
| `other_mandays_per_tower` | 2500 | not read by the alliance model |
| `scenarios.help_radius_m, help_walk_ms` | 10 km, 1.4 | the cooperation scenario 'high' only (not MR) |
| `lit_scenarios.quarry_ph_m3.joints_high` | 17.5 | S1b_joints_high / C3_quarry only |
| `ramp.*, oxen.*` | - | S4b / S3e only |

**v13 opt-in social switches (scenario keys; off in MOST_REALISTIC_P10 and in every run of the full audited queue; not counted in the 70 rows above).** They exist only in the v13 code (`alliance.py`: `_social_gate`, `_partner_order`, `_imit_pool`, `_bad`) and act only in the five v13 scenarios (`A5_full_freerider_V13rep`, `A5_full_freerider_V13pc`, `A5_full_freerider_V13reppc`, `MOST_REALISTIC_AUDITED_LIT_V13tie_P10`, `MOST_REALISTIC_AUDITED_LIT_V13all_P10`) and the three v13g scenarios with the gentle reputation rule (`A5_full_freerider_V13repg`, `A5_full_freerider_V13repgpc`, `MOST_REALISTIC_AUDITED_LIT_V13allg_P10`; row A13). With every switch off the outputs are identical to the frozen v12 code. They add no numeric parameter. "Authors' idea" = a rule set by the authors for which the literature gives the form but no value.

| id | Config key | MR_P10 value | What it does | Stated source (before) | Status before | Literature found (author, year, page) | Status after | Proposed action | AUDITED value (adopted) |
|---|---|---|---|---|---|---|---|---|---|
| A10 | `reputation` (scenario switch; observation radius = the run's interaction radius `S.R`, i.e. A1 `alliance.R_m`) | off (rule; no numeric value) | Third-party shunning with standing: every decision of an asked community is logged (help = good, unjustified refusal = bad); an observer sees an act if it is the requester or lies within R of the requester; the observer judges by the last act it saw (none = good); a non-defector declines a requester it sees in bad standing; such justified refusals (and partner-choice refusals) are not logged | v13 specification (2 Nov) | Authors' idea | FORM: Boyd & Richerson 2022: 179, 189-190, 194 (comparative, foragers); Kasper & Borgerhoff Mulder 2015: 704, 713 (comparative, Tanzania; no values); Nowak & Sigmund 2005 (image scoring) ‡; Panchanathan & Boyd 2004 (standing) ‡ | Authors' idea (form from the literature; no value) | keep as scenario switch; rules = Authors' idea | off |
| A11 | `partner_choice` (scenario switch) | off (rule) | Candidate list reordered (stable) into exchange partners (j helped i, or i helped j), the others, and last the communities that cheated i (refused i after receiving i's help and have not helped i since; this group takes precedence); an asked community declines a requester that cheated it | v13 specification (2 Nov) | Authors' idea | FORM: Apicella et al. 2012: 500 (cooperator assortment; ties to defectors broken; comparative, Hadza); Boyd & Richerson 2022: 179; Kasper & Borgerhoff Mulder 2015: 708-711 (reciprocity the strongest predictor of help; partner selection, Table 4; no values) | Authors' idea (form from the literature; no value) | keep as scenario switch; 3-group order = Authors' idea | off |
| A12 | `tie_imitation` (scenario switch; uses A8 `p_imit` 0.3 unchanged) | off (rule) | Imitation models = the communities linked to i by help given or received so far (mh > 0, either direction), ordered by distance then id; communities with no help tie use the neighbours within R | v13 specification (2 Nov) | Authors' idea | FORM: Apicella et al. 2012: 500 (similarity follows social ties, not geography; comparative); Boyd & Richerson 2022: 194 | Authors' idea (form from the literature; no value) | keep as scenario switch | off |
| A13 | `reputation_rule` (scenario key, used with A10; values `all` (default) / `gentle`) | off (A10 off; default `all`) | Which refusals are logged as bad acts in the reputation log. `all`: every unjustified refusal (A10 as above). `gentle`: only a refusal by a defector, or by a community that has received help from the requester (ingratitude; the same condition as the `delta_down` trust update, A3); refusals for backlog, distance or capacity by a community that owes the requester nothing are not logged and cost no standing | v13g specification (2 Nov) | Authors' idea | FORM: Fafchamps 1992: 148 (help is owed by recipients and is contingent on need and affordability; comparative, ethnography); Boyd & Richerson 2022: 179 (reciprocity-sustained privileges withdrawn from those who do not reciprocate); Kasper & Borgerhoff Mulder 2015: 713 (sanction on kin who refuse; no values); Panchanathan & Boyd 2004 (standing: only unjustified defection costs reputation) ‡ | Authors' idea (form from the literature; no value) | keep as scenario key; the ingratitude condition = Authors' idea | `all` (A10 off) |
| - | `social_log` (bookkeeping switch) | off | Adds the `soc_*` columns (sites) and `gid`, `imit_src`, `imit_tie` (strategy); no change in behaviour | - | - | - | - | test / analysis only | off |

‡ Cited for the formal concept only (image scoring; standing); not read at a page in this project, so no page is given.

### Notes on Part 1
- **Drag speed and pulling force go together.** Drag labour per block is crew × time = ceil(m μ / F) × L / v, so it scales with 1 / (F × v), the power each hauler sustains.
  - The current pair (294 N at 0.6 m/s) implies about 176 W per hauler all day.
  - Day-long physiological figures are 55-104 W (de Haan 2009: 6; Hertzberg 1972 via Boswinkel 2021: 52). Experiments that size crews support about 300 N per hauler (Richards & Whitby 1997: 237, 242).
  - The audited pair (294 N at 0.27 m/s, about 80 W) is consistent with both. Keeping 0.6 m/s would require the sustained 125 N (Boswinkel 2021: 52), which the pull-125 sensitivity already covers.
- **Course height.** Measured Sardinian courses are about 0.5 m, but the lever rate (0.37 ph) is defined per 0.9 m of lift (Boswinkel 2021: 124). The two must change together or not at all.
- **Stone volume.** Webster's 1,350 t (about 566 m³) counts blocks. The model's own tower shape is about 1,040 m³ net of voids, and a popular calculation from a table of 345 towers gives about 800 m³ (Trenta 2026). Fill or core stone may be uncosted (see out of scope).
- **Pages to confirm (†).** Webster 1991 tower heights (pp. 842-847) and Lilliu 1955's basalt density.

### Noted, out of scope (parameters): mechanisms the literature implies and the model does not have
These are not proposed and are not in AUDITED_LIT.
1. Force-speed coupling (power per hauler), as above.
2. Haulers lifting their own weight on slopes, and the breakaway force (de Haan 2010 via Boswinkel 2021: 44; Richards & Whitby 1997: 237).
3. Team efficiency falling with crew size (Richards & Whitby 1997: 237; DeLaine 1997 via Boswinkel 2021: 44).
4. Track-relaying crews (Harris 2016). Only the C1_rails_relay variant includes them.
5. The lever rate charged per piece regardless of mass. It was measured on 2.5 t blocks (Boswinkel 2021: 124).
6. Core and fill volume beyond Webster's blocks.
7. Unsplittable lintels of 1.5-4 t (Webster 2001: 21; Murru 2018: 229).
8. The shape of the Wright curve (cumulative average per doubling) against the S8 per-tower factor.
9. Slope and off-path terms for walking (Tobler 1993).
10. Separate hardness factors for dressing and quarrying.

# Part 2. Behaviours

This part documents the mechanisms as implemented and what each rests on. It changes nothing; behaviours are not part of AUDITED_LIT. Status tags follow the categories above; a row can carry more than one.

Counts over 34 behaviour rows (multi-tagged):
- SOURCED 13 (7 comparative or methodological);
- REPORTED-ONLY 11;
- Authors' assumption (specified by the authors) 14;
- Authors' assumption (modelling agent's design choice, accepted by the authors) 28;
- convention 1.

With no published source at all:
- the acceptance logit;
- the number and order of asks;
- the trust increments;
- the alliance threshold;
- k = 5 faces and the face setup cost;
- block splitting;
- the relay fractions;
- the help radius;
- the within-site learning rate.

### B1. Behaviour table

| # | Behaviour | What it is (as implemented) | Basis | Source (author, year, page; or specified by the authors) | Status | Note |
|---|---|---|---|---|---|---|
| 1a | Who helps whom, and when | Each community is one agent. Everyone inside a site works together. When it starts a tower, a community decides separately for quarrying, dressing and building/lifting (and for the first transport leg, see 11) whether to build alone or ask a neighbour. The decision is learned (see 4b). | PI specification; Sardinian literature (interpretive) | Specified by the authors. Araque Gonzalez 2021: 192 says the villagers "cooperated with neighboring communities for monument building and land clearance" Araque Gonzalez 2021: 195: mutual aid, with site management that "shifted according to the stage of construction" (read in the census). Ugas, as summarised in the compilation catalogued as "Moravetti et al. 2009", p. 361 (REPORTED-ONLY; see the note on this source in Part 1): "I nuraghi complessi contavano sull'apporto di vari villaggi". | Authors' assumption (specified by the authors); SOURCED (Araque Gonzalez); REPORTED-ONLY (Ugas via the compilation) | The literature here is interpretation (opinion), not excavated evidence of inter-site help. |
| 1b | Acceptance of a request | The asked community j accepts with probability logistic(β0 + β1·trust(j→i) − β2·backlog in days − β3·distance in km), with β = 0, 2, 0.05/day and 0.2/km. In A1 the acceptance is fixed at 0.5. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Proposed by the modelling agent and accepted by the authors. Comparative context only: Dietrich et al. 2019 say work feasts mobilise people "across kinship or friendship networks" and the turnout depends on the food offered (PLoS ONE; article without print pages). | ASSUMPTION | No source exists for the logistic form or for any β. At trust 0.5 and 5 km, p = 0.5. |
| 1c | Help mode "join" (MR) | An accepted helper adds its work party's hands to the requester's stage (quarry, dress, first transport leg, build/lift). The stage then lasts MH / (owner + helper hands). Helper hands are capped per block: 4 for quarrying, 2 for dressing, 6 per block of one course for building, and each block's own crew for transport. | Authors' assumption (modelling agent's design choice, accepted by the authors); comparative context | Proposed by the modelling agent and accepted by the authors. Comparative: Richards & Whitby 1997: 251 (a team of about 200 that splits "into smaller teams" on easy gradients and combines for the largest stone). | ASSUMPTION; SOURCED (comparative, qualitative) | The hands-per-block caps have no source. The cap never bound in about 2,000 test joins. |
| 1d | Help mode "handover" (A-family; MR_handover variant) | The accepted helper takes the whole stage over with its own party. | PI specification | Specified by the authors. | Authors' assumption (specified by the authors) | MR moved to "join" because handover slowed large sites. |
| 2a | Help radius R (alliances, MR) | Requests, relays and imitation are limited to communities within 10 km in a straight line. A sensitivity run on A5 used 5, 10 and 20 km. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Listed as a free parameter in the 28 Oct alliance report; not contested. Sardinian context: a canton covers about 8.9 km² on average (Ugas, via the compilation catalogued as "Moravetti et al. 2009", p. 361). The Marghine groups cover 10-50 km² each (Webster 2001; Catalogue scan page, print page not checked). | ASSUMPTION; REPORTED-ONLY (context) | A 10 km radius covers about 314 km², far more than either territorial unit. No source gives a help distance. |
| 2b | Help radius (cooperation scenario "high") | When a site finishes, its cooperators walk at 1.4 m/s to the nearest unfinished site within 10 km. They move on each time that site finishes, and go home when none is in range. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Specified by the authors. Proposed by the modelling agent and accepted by the authors. | ASSUMPTION | Not part of MR_P10. |
| 3a | Asking: number and order of candidates | Up to 3 candidates are asked in turn. They are ordered by skill (when specialisation is on), then by the requester's trust in them, then by distance. If all refuse, the community does the task itself. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Free-parameter list of the 28 Oct alliance report. | ASSUMPTION | No source. |
| 3b | Brokers (pre-existing networks, reach > 1) | A request may travel up to h ties (h = 2 or 3). Each intermediate community sends one person who walks to the next one and back, and that walk is charged to the requester. | PI specification (networks); agent's design (brokers) | Specified by the authors. The agent proposed the plan with reach in hops. Proposed by the modelling agent and accepted by the authors. | Authors' assumption (specified by the authors) (aim); ASSUMPTION (broker rule) | Not part of MR_P10, which uses no pre-existing ties. |
| 4a | Trust update | Trust starts at 0.5. When j helps i, i's trust in j rises by 0.1. When j refuses i after having received help from i, it falls by 0.2. Trust stays within [0, 1]. | PI specification (principle); assumption (values); literature context | Specified by the authors. Context: Araque Gonzalez 2021 (section "Monuments and cooperation", page not printed in the excerpt) says large monuments required "cooperation, coordination, mutual trust and reliability" Comparative: Sahlins 1972 on balanced reciprocity, via Boswinkel 2021: 14-15. | Authors' assumption (specified by the authors); ASSUMPTION (0.5 / +0.1 / −0.2); REPORTED-ONLY (Sahlins via Boswinkel) | No source gives trust values. Dietrich et al. 2019 say that after a work feast "no obligations remain", which is the opposite of the model's memory of help received. |
| 4b | Learning of strategies | Each choice (quarry face, ask or not for each stage, relay fraction) has its own value table. Choices are made ε-greedily (ε = 0.1). After each tower, value ← value + α(reward − value), with α = 0.5. The reward is −(the community's own man-hours per tonne). The first value of an action is the first reward. Untried actions start at 0, which is optimistic because rewards are negative. Quarry-face values start from the community's own cost estimates. | ABM methodology; PI specification (that agents learn); assumption (values) | Sutton & Barto 2018: 28 (ε-greedy), 32 (constant step size, eq. 2.5), 34 (optimistic initial values). Specified by the authors. | SOURCED (method); Authors' assumption (specified by the authors) (aim); ASSUMPTION (α, ε, reward) | The notes call this "Q-learning". As implemented it is a stateless bandit update with no next-state term, which is not Q-learning in the strict sense. |
| 4c | Imitation | With probability 0.3 per tower, a community copies the last strategy of the neighbour within R with the lowest cost per tonne, if that cost is lower than its own. A quarry face is copied only if the same outcrop region is among its own five faces. | ABM methodology (social learning); assumption (value) | Gilbert 2020, section 1.3.6: social learning, "in which some agents imitate or are taught by other agents" (online edition, no print page). | SOURCED (concept, section only); ASSUMPTION (p_imit = 0.3) | No source gives an imitation rate. |
| 4d | Wright skill learning (A3, MR) | The unit labour of quarrying, dressing and building falls as (1 + towers done)^log2(b), with b = 0.85 per doubling. Under specialisation, help given also counts. | ABM / industrial methodology; assumption (rate) | Wright 1936: 124 (cost factor F = N^x; the "eighty percent" curve). Comparative: Richards & Whitby 1997: 249 (continued use "would improve the efficiency" of the sledge and rails). | SOURCED (form); ASSUMPTION (b = 0.85); SOURCED (comparative, qualitative) | No archaeological learning rate was found. 0.85 is the midpoint of Wright's 80-90% range (1936: 124-126). |
| 4e | Within-site learning (S8 in REALISTIC, used by MR) | Tower i of a site costs 0.85^i of the first tower's craft stages. Each task gets only one discount: the larger of S8 and the performer's Wright factor, never both. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Proposed by the modelling agent and accepted by the authors. | ASSUMPTION | The 15% rate has no source. |
| 5 | Alliance formation | A pair is an alliance when trust is at least 0.7 in both directions. In A4/A5 allies share trackways and (A5) quarry faces. **In MR an alliance is only recorded**: MR has no trackways and no shared faces, so alliances change no labour or time. | PI specification (concept); assumption (threshold) | Specified by the authors. | Authors' assumption (specified by the authors); ASSUMPTION (θ = 0.7) | No source for the threshold. In MR the alliance is an output (networks, centrality), not a cause. |
| 6a | Recorded-stone (hybrid) rule | A site whose building stone is recorded takes that stone. The others use the nearest outcrop of an allowed stone. The allowed list has 7 stones. | PI specification; Sardinian literature | Specified by the authors. Literature: least-cost siting and "opportunistic use of materials" (Webster 2001: 122-123, read in the census). Only 7 of 113 Marghine nuraghi used stone from more than 2 km away (Gallin 1989, via Webster 1991: 848). | Authors' assumption (specified by the authors); SOURCED (Webster 2001); REPORTED-ONLY (Gallin via Webster) | "Nearest" means least drag cost on the terrain, not straight-line distance. |
| 6b | Quarry choice among k = 5 faces | For each site, the 5 cheapest distinct outcrop regions are found, each with its route. The face used for each tower is a learned choice (see 4b), starting from the community's own cost estimates. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Proposed by the modelling agent and accepted by the authors. | ASSUMPTION | No source for k = 5. |
| 6c | Setup cost of a new face | Opening a face the community has not used before costs 200 man-hours. Reusing its own face is free. An ally's face is free only in A5. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Free-parameter list of the 28 Oct alliance report. | ASSUMPTION | No source found. |
| 7a | Crew formation | Each block is dragged by ceil(mass / pull per person) people. In MR the pull is 30 kgf / μ: about 79 kg per person on dry ground (μ 0.38) and 300 kg per person on tallowed rails (μ 0.1). | Comparative (non-Sardinian) basis for the force; authors' assumption for the rule | Boswinkel 2021: 52: men can sustain about 125 N and reach up to 300 N in bursts (de Haan 2009). The model uses the 300 N peak. Comparative checks: Richards & Whitby 1997: 235 (1.5 t needed 32 haulers on level grass, after Atkinson 1956) and 239 (with tallow, "a total of 200" people for 40 t). | SOURCED (Boswinkel's statement); REPORTED-ONLY (de Haan, Atkinson); ASSUMPTION (the rule) | The model's crews are smaller than the experiments': 19 people instead of 32 for 1.5 t on dry ground, and about 134 instead of 200 for 40 t on tallow. A 125 N sensitivity run exists. |
| 7b | Splitting heavy blocks to fit the work party | A block that needs more people than the work party has is cut into the fewest equal pieces that fit. Each cut costs 1 man-hour. Pieces are lifted separately (30 Oct fix). On sea faces, pieces must also fit the 2 t craft payload. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Proposed by the modelling agent and accepted by the authors. | ASSUMPTION | No source says nuragic builders cut blocks to suit the party. 1 man-hour per cut is a choice. |
| 8a | MR work party by tower count | Residents per site ~ uniform within a range set by tower count: 5-40 (1 tower), 40-110, 110-185, 185-260, 260-330, 330-400 (6-7 towers). Builders = round(0.5 × residents). | PI specification (rule); Sardinian literature (anchors); assumption (interpolation, 0.5) | Specified by the authors. Anchors: one household of about 5-6 per simple tower (Webster 2015: 51, our citation check); homesteads of five persons each (Webster 1991: 852); about 70 people at Duos (Webster & Webster 1998: 196); Porcarzos about 400 residents (Webster 1991: 853, in the census); 10-20 people per nuraghe (Trump, via Perra 2014: 141). | Authors' assumption (specified by the authors); SOURCED (Webster); REPORTED-ONLY (Trump via Perra); ASSUMPTION (class ranges between anchors, adult share 0.5) | Our citation check found that Duos supports "about 70", not "70-110", so the 110 bound of the 2-tower class has lost its anchor. The 166-259 per canton figure is our own division, not printed anywhere. Comparative: Abrams 1987: 493 puts the labour pool at 20-33% of the population (via Boswinkel 2021: 149); Wunderlich et al. 2024 (section 7.2) assume about 60% able to work. |
| 8b | Households of 5 (cooperation scenarios, not MR) | Builders are grouped in households of 5. Non-cooperators work only as one fixed crew of their household. | Sardinian literature; agent's design | Webster 1991: 852-854 (homesteads "with an average of five persons"; Table 2 note 2, p. 854). Proposed by the modelling agent and accepted by the authors. | SOURCED; ASSUMPTION (the crew rule) | Webster's five are residents, not workers, while the model treats the 5 as builders. |
| 8c | Population ceiling (MR) | The residents of communities building at the same time may not exceed 300,000. It never binds: the P10 peak is about 33,000. | PI instruction (relayed); Sardinian literature | Specified by the authors (relayed): use Calò et al. 2008, p. 41, as a ceiling, not a baseline. Calò et al. 2008: 41 (read): the population is believed never to have exceeded 300,000 before AD 1700. | SOURCED (Calò); not Authors' assumption (specified by the authors) in PROMPTS.md (second-hand) | The 300,000 sentence carries no citation in Calò et al. Ugas's Bronze Age estimates differ: about 200,000 at the end of the Middle Bronze Age, and 450,000-700,000 c. 1200 BC (reported by Atzeni & Frau 2023: 447). |
| 9a | Phasing P10 / P20 / P100 | P10: a random 10% of sites (drawn per seed) starts in season 1. The next 10% starts only when every tower of the earlier cohorts is finished, until 100%. P20 uses 20% steps. P100 starts every site at once. | PI specification | Specified by the authors. | Authors' assumption (specified by the authors); ASSUMPTION (random cohort membership) | Literature context: towers were added over centuries as the population grew (Webster 1991: 853, in the census). No source sets cohorts of 10%. |
| 9b | start_rate (alliance families only, not P10) | Without phasing, 1/450 of all sites start each season, so starts spread over about 450 seasons. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Chosen to match about 500 years of nuraghe building (Ialongo 2018: phases c. 1650-1100 BC; the "500 years" is our reading). | ASSUMPTION | MR_P10 does not use it. |
| 10a | Season = one year of 90 working days | One model tick is a season of 90 communal working days and stands for one year. | PI specification; Sardinian secondary literature | Specified by the authors. Renfrew 1973: 549, via Webster 1991: 853 and Webster 1996: 90 communal man-days a year in emergent chiefdoms, against 40 in simpler societies (Erasmus 1965: 280-81, same reporters). | Authors' assumption (specified by the authors); REPORTED-ONLY (Renfrew, Erasmus via Webster) | In the source, 90 is the communal days given per man per year in a chiefdom. Webster leans to 40 for simpler societies. Man-hours do not depend on season length; years do (30 Oct tests). |
| 10b | 8-hour working day | Every party works 8 h a day. | Authors' assumption (convention) | Erasmus 1965: 283, via Boswinkel 2021: 145: "most writers" use an 8-hour day, which Erasmus calls somewhat ethnocentric. | ASSUMPTION; REPORTED-ONLY (Erasmus via Boswinkel) | |
| 10c | Webster day fix (5 h / 8 h) | Webster's man-days for quarrying (and transport) are 5-hour days, after Erasmus. Those for dressing and walling are 8-hour days, after Abrams. Each is converted at its own day length. | Authors' assumption (modelling agent's design choice, accepted by the authors); comparative secondary literature | Proposed by the modelling agent and accepted by the authors. Erasmus's day of about 5 h: Erasmus 1965: 283, via Boswinkel 2021: 145. Abrams's 8-h man-day: via Boswinkel 2021: 109, 146. | ASSUMPTION; REPORTED-ONLY (Erasmus, Abrams via Boswinkel) | Webster himself states no day length. |
| 11a | Transport relay (hand-off) | A neighbour nearer the quarry drags the stone to a hand-off cell at 0.25, 0.5 or 0.75 of the route's drag cost. The requester drags the last leg. Relays apply only to routes costing at least 300 flat-metres. Each leg's load/unload time is half the usual. | PI specification (mechanism); assumption (values) | Specified by the authors. | Authors' assumption (specified by the authors); ASSUMPTION (fractions, 300 m minimum) | No source for hand-off points. In MR "join", helpers work on leg 1 alongside the owner. |
| 11b | Return walk and helper walks | Crews walk back empty at 1.4 m/s. A helper's whole party walks to the task once per task, and the walk is charged to the helped site. | Authors' assumption (modelling agent's design choice, accepted by the authors) | Logged in the methods parameter table as a "normal walking speed". | ASSUMPTION | No source read for 1.4 m/s. |
| 12a | Pre-existing networks: group sizes | G3 canton: groups seeded at multi-tower nuraghi, about 2.65 sites each. G20: territorial systems. G133: tribes, two-level over cantons. G5, G50 and G9 are free bounds or sensitivity. Requests go only along ties, accepted with p = 0.9. | PI specification (aim); Sardinian literature (sizes) | Specified by the authors. Sizes: about 2,700 canton seats and about 50 cantons per tribe (Ugas, via the compilation catalogued as "Moravetti et al. 2009", pp. 360-361). At least 350 territorial systems (Perra 2008: 664-665, via Bernardini 2016: 70 n. 15). | Authors' assumption (specified by the authors); REPORTED-ONLY (Ugas via Moravetti et al.; Perra via Bernardini); ASSUMPTION (p_tie, G5/G50) | Ugas 2005: 40 itself (read in our citation check) gives just under 800 cantons, which conflicts with 2,700. The G9 sensitivity covers that reading. |
| 12b | Pre-existing networks: shapes | Ties inside a group form a chain, k-nearest meshes (2/4/8), a hub (highest-tower site), a small world (the 4-mesh with each tie rewired with p = 0.1 to a community outside the group within 10 km), or a complete graph. | ABM methodology (small world); Sardinian literature (hub); agent's design | Watts & Strogatz 1998: 440 ("we rewire each edge at random with probability p"). Hub: complex nuraghi "dovevano guidare e coordinare" the smaller ones (Ugas, via the compilation catalogued as "Moravetti et al. 2009", p. 361). Proposed by the modelling agent and accepted by the authors. | SOURCED (method); REPORTED-ONLY (Ugas); ASSUMPTION (chain, mesh sizes, p = 0.1) | Departure from Watts & Strogatz: the rewiring is local (within 10 km, outside the group), not uniform at random. Not part of MR_P10. |
| 13 | Specialisation (A3, MR) | With specialisation on, help given also builds the helper's skill (see 4d). Skilled communities are asked first. | Authors' assumption (modelling agent's design choice, accepted by the authors); Sardinian literature (both views) | Part of the 28 Oct design accepted. A later question by the authors asked about this result; it is not a specification. For: complexes needed a large, skilled workforce (Melis 2017: 42, in the census). Against: no workshops or occupational specialists found (Webster 1991: 840-841, in the census). Comparative: communities of stone-working practice (Bevan & Bloxam 2016; page not printed in the Catalogue excerpt). | ASSUMPTION; SOURCED (Melis, Webster: opposing opinions) | The literature is split. MR keeps specialisation; the master-mason scenarios (M2) are separate. |
| 14a | Sea access (S9; MR uses 2 kn) | Sites and quarries within 2 km of the coast may use boats in a 2 km coastal water band (no open-sea crossing). Boats land on shore at most 10 m above sea level with slope under 10°, or hoist below cliffs of at most 5 m. People may also travel by sea. | PI specification | Specified by the authors. | Authors' assumption (specified by the authors); ASSUMPTION (2 km band, 10 m / 10°, 5 m: the agent's translation of his words, accepted with "ok", 10:30:05, line 718) | No Sardinian evidence of stone moved by sea. The bronze boat models (navicelle) show real boats existed (Moravetti et al. 2014; no page taken). |
| 14b | Laden craft speed and payload | The laden craft moves at 2 knots and carries 2,000 kg of stone with a crew of 10. Load/unload is 0.25 h at each landing. | Comparative (non-Sardinian) | Hazell & Fitzpatrick 2006: 18 ("a corrected speed of 2 knots" for laden craft; 800 kg of crew in the 2,000 kg-load craft); 12 (2,000 kg benchmark stone). Specified by the authors. | SOURCED (comparative, Yap / Palau); Authors' assumption (specified by the authors) (4-6 kn runs); ASSUMPTION (crew = 800 / 80 kg, transfer time) | The craft analogue comes from Micronesia, not the Mediterranean. |


### B2. Notes per behaviour

**1. Who helps whom, and when.**
- The request is made at the start of each tower, once for each stage.
- Whether to ask is a learned 0/1 choice, not a rule.
- The PI specified the core idea (cooperate inside the site, ask outside it). The Sardinian sources that support inter-community help are interpretive:
  - Araque Gonzalez 2021 (mutual aid, heterarchy);
  - Ugas as summarised by Moravetti et al. 2009 (complexes relied on several villages).
- Neither gives a rule for whom to ask or when.
- "Join" in MR (helpers add hands) was the agent's fix after handover slowed large sites (subset test, 29 Oct). The PI accepted it.

**2. Help radius.** The 10 km radius is a free choice. The Sardinian territorial units are much smaller:
- about 8.9 km² per canton (Ugas, via Moravetti et al.);
- 10-50 km² per Marghine group (Webster 2001).
A radius matching those units would be about 2-4 km. This is a fact about the parameter, not a proposal to change it. The A5 sensitivity (5/10/20 km) is the only check.

**3. Asking and brokering.**
- Three asks per task, with candidates ordered by skill, trust and distance: no source.
- Brokers exist only in the pre-network scenarios with reach 2-3, so they are not part of MR_P10.

**4. Trust and learning.**
- The PI's reciprocity principle (trust grows with reciprocated help) is implemented asymmetrically. Trust rises whenever help is given. It falls only when someone who has received help refuses.
- The learning rule is the standard bandit update with ε-greedy choice (Sutton & Barto 2018: 28, 32, 34). The notes call it Q-learning; strictly it is not, because there is no state.
- The reward is the community's own man-hours per tonne, not time. That is why, under handover, delegation was cheap but slow.
- The Wright curve form is read in Wright 1936: 124. The value b = 0.85 is ours.

**5. Alliance formation.** In MR the alliance threshold has no effect on labour or time: MR has no trackways and no shared quarry faces. Alliances are reported as a network output only.

**6. Quarry choice.**
- The hybrid rule is the PI's own specification. It matches the Sardinian view of local, least-cost stone (Webster 2001; Gallin via Webster 1991).
- k = 5 and the 200 man-hour setup cost are free choices.

**7. Crews and splitting.**
- The crew rule (people = mass / pull) is the agent's. The force is Boswinkel's 300 N peak.
- Against the Stonehenge experiments (Richards & Whitby 1997: 235, 239), the model's crews are lighter. The model is therefore optimistic on transport labour.
- Splitting blocks to fit a small party has no source.

**8. Work parties.**
- The PI specified the rule: scale by towers, random draw, literature base, adults only.
- The class ranges are an interpolation between few anchors. One of them (Duos 70-110) was found to be wrong ("about 70").
- The 0.5 adult share is ours. Webster 1991: 854 (Table 2, note 4) reads "Men available = population/5"; with an equal number of women this gives 0.4, the audited value (Part 1, P2). Comparative shares in the literature run from 20-33% (Abrams via Boswinkel) to about 60% (Wunderlich et al. 2024).
- The population ceiling was specified by the authors (relayed). Its source sentence in Calò et al. 2008: 41 is uncited.

**9. Phasing.**
- P10, P20 and P100 follow the PI's words exactly.
- Which sites fall in which cohort is random per seed. That is the agent's choice; no chronology is used.

**10. Seasons and days.**
- The PI fixed one season = 90 days = one year.
- The literature figure behind 90 is Renfrew's communal labour per man per year in emergent chiefdoms, known only via Webster. Webster also reports Erasmus's 40 days for simpler societies.
- The 8-h day is a convention.
- The 5 h / 8 h split of Webster's man-days follows Erasmus and Abrams, both reported via Boswinkel 2021.

**11. Relays.**
- The relay is the PI's own example: neighbours drag stone closer, the owner takes over.
- The fractions, the 300 m minimum and the 1.4 m/s walk are ours.

**12. Pre-existing networks.**
- The PI specified the aim (networks of varied size and access). The sizes come from Ugas (reported by Moravetti et al. 2009) and Perra 2008 (reported by Bernardini 2016).
- Ugas's own 2005 count (about 800 cantons) conflicts with the 2,700 seats in the summary.
- The small-world shape follows Watts & Strogatz 1998: 440, with local rather than random rewiring.

**13. Specialisation.**
- The agent's design.
- The Sardinian literature is split: Melis 2017 for a skilled workforce, Webster 1991 against occupational specialists.

**14. Sea.**
- The PI specified sea access, people by sea, landings near sea level, and hoists below low cliffs.
- The numbers are the agent's translation of his words, plus the Yap / Palau raft analogue: 2 kn and 2 t (Hazell & Fitzpatrick 2006: 12, 18).

### B3. Noted, out of scope (mechanisms the literature implies and MR_P10 does not have)

These are listed for completeness, not proposed.
- **Work feasts as the incentive for help.** Hosts with more food draw more helpers, and no obligation remains afterwards (Dietrich et al. 2019, after Dietler & Herbich 2001). In MR, acceptance depends on trust, backlog and distance, not on food. A food-cap / feast family (S12) exists outside MR.
- **Labour levy (corvée) by canton seats** (Ugas, via Moravetti et al. 2009). It exists only as S21, outside MR.
- **Team efficiency falling with crew size** (Richards & Whitby 1997: 237, 50% for large teams). Not modelled: crew labour scales linearly.
- **Seasonal timing**: building in the agricultural slack season, wet ground in winter (Turner 2020 via our review). The model has no calendar inside the season.
- **Mobile master masons / wandering specialist crews** (Araque Gonzalez 2021: 194). They exist only as M2, outside MR.
- **Regional building traditions** (Usai 2017, blog repost). Not modelled.


### B4. Literature used for Part 2 (as catalogued)

- Gary S. Webster (1991). Monuments, mobilization and Nuragic organization.
- Gary S. Webster (1996). A Prehistory of Sardinia 2300-500 BC. Sheffield Academic Press, Sheffield. ISBN 1 85075 508 6.
- Gary S. Webster (2001). Duos Nuraghes: A Bronze Age Settlement in Sardinia. Volume 1: The Interpretive Archaeology. BAR Publishing, Oxford. ISBN 9781841712413.
- Gary S. Webster (2015). The Archaeology of Nuragic Sardinia. Equinox, Sheffield.
- Giulia Albertazzi, Giulia Muti, Alessandra Saggio (2021). ISLANDS IN DIALOGUE (ISLANDIA). Editoriale Artemide s.r.l.. ISBN 978-88-7575-362-7. (contains Araque Gonzalez, "Monuments of cooperating communities")
- Alberto Moravetti, Paolo Melis, Lavinia Foddai, Elisabetta Alba (2009). LE FONTI SCRITTE DEL NEOLITICO.
- Giovanni Ugas (2005). L'alba dei nuraghi. Fabula editrice, Cagliari.
- ENRICO TRUDU, GIACOMO PAGLIETTI, MARCO MURESU (2016). LE TORRI NURAGICHE OLTRE LʼETÀ DEL BRONZO. UNIVERSITÀ DEGLI STUDI DI CAGLIARI. (contains Bernardini 2016, p. 70 n. 15)
- NICOLA IALONGO (2018). Crisis and Recovery: The Cost of Sustainable Development in Nuragic Sardinia. European Journal of Archaeology.
- Laura Dietrich, Julia Meister, Oliver Dietrich, Jens Notroff, Janika Kiep, Julia Heeb, André Beuger, Brigitta Schütt (2019). Cereal processing at Early Neolithic Göbekli Tepe, southeastern Turkey. PLoS ONE.
- Andrew Bevan, Elizabeth Bloxam (2016). Stonemasons and Craft Mobility in the Bronze Age Eastern Mediterranean.
- Alberto Moravetti, Elisabetta Alba, Lavinia Foddai (2014). LA SARDEGNA NURAGICA. Università degli Studi di Sassari. ISBN 978-88-7138-750-5.
- Alberto Moravetti, Paolo Melis, Lavinia Foddai, Elisabetta Alba (2017). LA SARDEGNA NURAGICA Storia e monumenti. Carlo Delfino editore. ISBN 978-88-7138-995-0. (Melis 2017)
- Gary S. Webster, Maud R. Webster (1996). The Duos Nuraghes Project in Sardinia: 1985-1996 Interim Report. Penn State University-Mont Alto Campus. (the census and citation check cite this doc as Webster & Webster 1998, JFA 25; the Catalogue metadata differ)
- Alessandro Usai (2017). Archeologia della Sardegna. Paesaggi nuragici Riflessioni di Alessandro Usai.
- Sergio Atzeni, Sergio Frau (2023). Volume 1 - 3 edizione - Nascita, sviluppo e declino della Civiltà Nuragica stampa Susil 29-4-2023.

Primary texts read outside the Catalogue (open access or project copies):
- Sutton, R.S. & Barto, A.G. 2018. *Reinforcement Learning: An Introduction*, 2nd ed., MIT Press. Read at pp. 28, 32, 34 .
- Watts, D.J. & Strogatz, S.H. 1998. Collective dynamics of 'small-world' networks. *Nature* 393: 440-442. Read at p. 440 .
- Wright, T.P. 1936. Factors affecting the cost of airplanes. *J. Aeronautical Sciences* 3(4): 122-128. Read at p. 124 .
- Richards, J. & Whitby, M. 1997. The engineering of Stonehenge. *Proc. British Academy* 92: 231-256. Read at pp. 235, 237, 239, 249, 251 .
- Hazell, L.C. & Fitzpatrick, S.M. 2006. *Archaeology in Oceania* 41: 12-24. Project copy (forwarded by the PI), read at pp. 12 and 18.
- Boswinkel, Y. 2021. *Labouring with large stones* (PhD thesis, Leiden, open access). Project copy, read at pp. 14-15, 52, 109, 145-146, 149.
- Gilbert, N. 2020. *Agent-Based Models*, 2nd ed., SAGE. Project copy, section 1.3.6.
- Calò et al. 2008, IJMA 1: 39-64. Project copy, p. 41 (read in the 31 Oct citation check).

Not read (REPORTED-ONLY wherever used):
- Erasmus 1965;
- Renfrew 1973;
- Abrams 1987;
- de Haan 2009;
- Atkinson 1956/1961;
- Gallin 1989;
- Perra 2008;
- Trump 1990;
- Sahlins 1972;
- Dietler & Herbich 2001 (no open-access copy found);
- Axelrod 1984 (not used as a source).

---

