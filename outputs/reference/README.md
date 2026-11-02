# outputs/reference (audit step d)

`reference_audit_sha256.csv` (not yet shipped: it is generated after the full audited run has finished) is the
fingerprint of one fixed rerun:

- scenario `MOST_REALISTIC_AUDITED_LIT_P10`, configuration `config/config_full_audited.yaml`;
- the 300 sites of `code/sites300_real.txt`, seeds 1-3, `--fresh`;
- the derived inputs of the full audited run (the prebuilt derived-input pack).

Columns: `item` (path under the rerun folder; part files of all ranks of one seed pooled as `...rank*.csv`), `kind`
(`bytes`, `gz_content` or `rows`), `sha256`, `n` (bytes, decompressed bytes or data rows). Written and compared by
`notebooks/repro.py` (`fingerprint`, `write_fingerprint`, `compare_reference`); made by `05_audit.ipynb` with
`MAKE_AUDIT_REFERENCE = True`, checked by the same notebook with the default settings. The number of MPI ranks does
not change the items.
