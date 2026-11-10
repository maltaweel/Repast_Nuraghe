# outputs/summary (audit step e)

Not in the repository: these tables are model results, a separate data input from the results package (the
headline of the v17 runs). Put them here (or point `SUMMARY_DIR` / `NB_SUMMARY_DIR` of 05 at them). Expected files
and columns (read by `notebooks/repro.py`, `headline_from_summaries`):

`per_seed_full_audited.csv`: one row per queue entry (`label` = the queue label, e.g. `MOST_REALISTIC_AUDITED_LIT_P10`)
and seed, with at least

| column | meaning |
|---|---|
| `label`, `seed` | queue label and seed (1-100) |
| `island_MH` | island man-hours: sum of `mh_total` over the 7,167 sites |
| `years` | island years: (last `finish_day` + 1) / 90 working days per season |
| `site_years_mean` | mean per-site build time in seasons (`days` / 90) |
| `transport_share` | `mh_transport` / `mh_total`, island sums |
| `tonnes` | stone moved, island sum |

The rule is that of `notebooks/repro.py` (`per_seed_from_parts`; the same rule as the summary tools in `code/tools/`),
applied to `seed_NNNN.sites.csv.gz` part files.

`summary_full_audited.csv`: one row per `label`, with at least `n_seeds`, `years_mean`, `years_min`, `years_max`,
`mh_M_mean`, `mh_M_min`, `mh_M_max` (man-hours in millions), computed from the per-seed table.
