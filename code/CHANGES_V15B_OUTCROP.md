# code_v15b_outcrop (5 Nov 2026)

Decision (specified by the authors, 5 Nov 2026): a site queries only the stones it is known to be built of; if there is
no record, or it cannot reach the recorded stone, it uses the allowed stones. The same rule applies to every arm.

Meaning: a site's on-outcrop test (joints_low 11.1 vs scree 2.0 ph/m3; the 15 m on-outcrop haul; the on/off-outcrop
network seed draw) is evaluated against the stone set the site ACTUALLY quarries: its recorded stone set if known and
reachable, otherwise the allowed fallback set (the 7 allowed classes); the site quarries from any class in its
stone set (ODD 7.6).

Base: the run's code_v15_haul15 (CODE_V15_SHA256SUMS). v15b was not published on its own; it is part of code_v16_final.

## The bug
preprocess.py run_rule (hybrid stone rule) set
`on_out = code[cell] > 0 and class(cell) in want[i]`, where want[i] is the RECORDED set. For a site whose recorded stone
has no reachable outcrop (Q_SRC = recorded_unreachable_fallback) the haul, quarry and site_stone_sets.csv already use the
fallback set, but the flag was still tested against the recorded set. Result: a site that sits on an outcrop of a
fallback class was flagged off-outcrop.

## The fix (one place)
preprocess.py run_rule: `used[i] = base if Q_SRC[i] == "recorded_unreachable_fallback" else want[i]` and the flag tests
`class(cell) in used[i]`. `used` is exactly the set written to site_stone_sets.csv (recorded set when reachable, else the
fallback list). Sites with a reachable recorded stone still test only their recorded classes;
fallback-only sites (no record) already tested the fallback list. main() (fixed --stones lists: every class allowed),
stones7 / stones4 rules (want = base for every site) and the buildstone tables cannot change.

Downstream tables that copy the flag (no code change needed, rebuilt from the fixed tables): tools/haul_far.py
(sites_haul_complexfar.csv: base rows copy sites_haul.csv; far rows are False by design), tools/sea_routes.py
(sites_haul_sea*kn.csv: land rows copy sites_haul.csv; sea rows False by design). model.py / alliance.py / lit.py read
the flag from those tables; kbest_* / wl_inputs do not use it.

Every other file was byte-identical to code_v15_haul15 (diff -rq lists preprocess.py, CODE_VERSION and this note).

## Sites affected (prepared tables)
- Sites whose flag changes: ONE, NID9220200 (TWR_N 1; recorded "Basalto" -> {basalt}, no reachable basalt ->
  Q_SRC recorded_unreachable_fallback; fallback set = the 7 allowed classes; the cell under the site is acid volcanic,
  in the fallback set; haul 0 at its own cell, quarry stone acid volcanic): on_outcrop False -> True in all 6 hybrid
  tables (mu 0.3 sites_haul.csv, mu 0.38 / 0.1 / 0.05 / 0.5, complexfar). It is the only recorded_unreachable_fallback
  site in every hybrid table. stones7 / buildstone tables: no change possible (already on its outcrop under stones7).
- Tables: every prepared table rebuilt with this code (hybrid tables, every cache's sea/ tables, the alt_stones7
  preparation); each table is either content-identical to v15 or differs in exactly one row (NID9220200) and one
  column (on_outcrop).
- Knock-on by design: the P_G20_kmesh4_on_outcrop / _off_outcrop seed draws (rng.choice over the eligible list)
  reshuffle.
