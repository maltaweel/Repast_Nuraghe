# outputs/summary (audit step e)

Not yet shipped: generated from the part files of the full audited run when it has finished. Expected files and
columns (read by `notebooks/repro.py`, `headline_from_summaries`):

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

The rule is that of `code/tools/v12_summary.py` (`per_seed`), applied to `seed_NNNN.sites.csv.gz` part files.

`summary_full_audited.csv`: one row per `label`, with at least `n_seeds`, `years_mean`, `years_min`, `years_max`,
`mh_M_mean`, `mh_M_min`, `mh_M_max` (man-hours in millions), computed from the per-seed table.
