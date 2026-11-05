# code_v16_final (5 Nov 2026): the reference version (approved by the authors, 5 Nov 2026)

Base: the run's code_v16_flags (CHANGES_V16.md; = v15b (CHANGES_V15B_OUTCROP.md) + add4 flags + L5/S1-S3 + spread
statistics, relay leg-1 nearer-quarry filter removed). Changed files: lit.py, alliance.py, model.py, METHODS.md,
MOST_REALISTIC_NOTES.md (not published), tests/test_add4_flags.py (new defaults); new: tests/test_v16_final.py, this
note. Every other file is byte-identical (CODE_V16_FINAL_SHA256SUMS). D3, D6 and D11 are bugs found by a review of
the v15b code against the model specification.

## 1. add4 defaults (lit.ADD4_DEFAULTS)
L2 `bedrock_everywhere` and L3 `load_per_tonne` default ON (kept after the test of CHANGES_V16.md). L1
`rails_cost_choice` and L4 `sea_priced_as_charged` default OFF. All four flags remain; a row switches any of them with its own
top-level `add4:` block. L2 also acts in model.py `--lit REALISTIC` rows (lit.resolve_site).

## 2. D3: no dressing work = no dress task traffic (reference bug)
PM:20 "Dressing: none for 1 tower". Before, a 1-tower tower's 0-MH dress stage still gave a dress skill credit, could
ask for help (acceptance draw, trust up, alliance), and an accepted helper walked to the quarry. Now `perform()` routes
any skill stage with labour-before-skill 0 and no extra to `AllianceModel._no_work_task`: the owner's 0-MH task only
(chain order unchanged). No ask, no draw, no trust change, no levy, no helper walk, no credit. The req_dress strategy
dimension is still drawn (strategy stream unchanged). The removed acceptance draws shift later draws of the asked
communities' streams.

## 3. D11: the site's stone = the class of its gated face 0 (reference bug)
`Static._init_tech` took `quarry_stone` (S6 density -> block mass; hardness -> quarry and dress) from the mixed table
(sites_haul_mu0.38 or, past 1 km, sites_haul_mu0.1). Those tables come from separate least-cost searches and can name
another outcrop class than face 0, which the site actually hauls from. Now the stone is `quarry_stone` of the gated
mu 0.3 table `cache/sites_haul.csv` (`Static._face0_stone`). Its rows are face 0 of kbest.npz. The stone rule is the set
actually quarried, including fallback. The mixed table still decides friction (rails or dry ground, PM:22). The L1
cost choice uses the same face-0 stone for both options. Decision O1: one stone per site, so sea-face towers keep the
land face-0 class.
- **No table rebuild needed.** In both distinct caches used by the queue (hybrid and alt_stones7), the class at the
  kbest face-0 cell on the cache's outcrop raster equals sites_haul.csv quarry_stone at 7,167 / 7,167 sites
  (tests/test_v16_final.py test_D11_tables). No table was built or changed.
- **Sites whose model stone changes (headline cache):** 31 UIDs (22 rails row, 9 dry row). Tonnes change at 27
  (matches the diagnosis list exactly). Hardness changes at 9 under the config hardness table: the diagnosis's 6
  (NID0408700, NID9041200, NID1059200, NID1426200, NID9215300, NID9103900) plus 3 dry-row sites (NID0054500 andesite ->
  granite, NID0130500 granite -> limestone/marble, NID0440700 granite -> metamorphic).

## 4. D6: join mode, each party at its own skill
PM:23 "A helper uses its own skill". `_perform_join` prices the owner's share base x (1 - f) at `_owner_skill` (min of
A3 skill and S8 learning, under tech rules) and the helper's share base x f at the helper's A3 skill. Before, the main
performer's factor was used for the whole stage. Extras (setup, cuts, soil) stay undiscounted and are split by f.
`_join_task` takes the pre-priced parts. Relay leg 1 (no skill) is unchanged. The learning credit is unchanged: it goes
to the main performer.

## 5. Run signature covers code changes
`CODE_VERSION = "2026-11-05-v16_final"` (lit.py; alliance.CODE_VERSION is the same string). From 29 Oct to v16_flags it
was "2026-10-29-bugfix", so for example v15b and v15c headline parts shared signature 790cb032753e. alliance.signature now
always hashes ADD4_VERSION and the effective add4 settings; v16_flags hashed them only when a flag was on.
model.run_signature (coop/lit/tost/baseline rows) now also hashes the add4 settings and CODE_VERSION. An explicit add4
block equal to the defaults gives the same signature as no block. In addition, every v16_final config has its own
cache_dir (v16_final/outputs/caches/<config stem>, own runs/), so no v15b/v15c part file can be reused.

## 6. Docs
METHODS.md 9.1(c): the relay helper comes from the ordinary candidate list; the "nearer the quarry" filter is
recorded as removed. The alliance.py "# 4 transport" comment says the same. MOST_REALISTIC_NOTES.md: join skill (D6)
and the no-work rule (D3).

## Tests
- `tests/test_v16_final.py`: 10 tests, all pass.
  - D3: unit test, a source-order test, and a run-level test on the part files of a headline check run
    (V16F_PARTS=...): dress credits equal the towers with dressing, and 1-tower owners have no dress asks or help. It
    fails, as it should, on the parts of code_v16_flags.
  - D6: four unit tests (owner main performer, helper main performer, no tech rules, relay leg 1 unchanged).
  - D11: an alignment test, and real tables 7,167/7,167 with 27 tonnes sites.
  - Signature: CODE_VERSION and add4 in both signature functions.
- `tests/test_add4_flags.py`: 13 tests, all pass, after updating them for the new defaults.
