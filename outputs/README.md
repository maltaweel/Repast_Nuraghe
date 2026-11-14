# outputs

Everything a run or a notebook writes goes here (work copies, runs, logs). Not committed, except the sensitivity
tables and two small folders shipped for the audit (`notebooks/05_audit.ipynb`):

- `sensitivity/`: the sensitivity results of the final model (designs, one row per run or evaluation, Sobol / Morris
  indices with confidence intervals), island level only; see its README.

Audit folders:

- `reference/`: the fingerprint of a fixed run of the headline scenario (step d of the audit);
- `summary/`: the per-seed and summary tables of the full audited run (step e).

Neither file set is included in the repository (the audit reports these steps as NOT INCLUDED); the README in each
folder describes the files and how to make or supply them.
