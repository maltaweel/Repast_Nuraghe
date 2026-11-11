# outputs

Everything a run or a notebook writes goes here (work copies, runs, logs). Not committed, except the sensitivity
tables and two small folders shipped for the audit (`notebooks/05_audit.ipynb`):

- `sensitivity/`: the sensitivity results of the final model (designs, one row per run or evaluation, Sobol / Morris
  indices with confidence intervals), island level only; see its README.

Audit folders:

- `reference/`: the fingerprint of a fixed rerun of the headline scenario (step d of the audit);
- `summary/`: the per-seed and summary tables of the full audited run (step e).

Both are placeholders until the full audited run has finished; see the README in each folder.
