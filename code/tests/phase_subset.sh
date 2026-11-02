#!/usr/bin/env bash
# Subset test of the simulated phasing (DEV code): 302 sites, seeds 1-3, 2 ranks.
#   full / full_P10 / full_P20 (independent: simulated phasing must equal the post hoc rule exactly),
#   high / high_P10 (coupled), A5_full / A5_full_P10 (alliance cohorts replace start_rate). No 100-seed runs.
set -uo pipefail
DEV=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/dev_phase
PY=${PYTHON:-python3}
CFG=$DEV/config.yaml
S=$(cat $DEV/sites302.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n 2"
W=$DEV/scratch/phase_subset; rm -rf $W; mkdir -p $W
cd $DEV
flock /tmp/nuraghe_dev.lock $PY memrun.py $W/run.log -- bash -c "
  for n in full full_P10 full_P20 high high_P10; do
    $MPI $PY model.py $CFG --scenario \$n --sites $S --seeds 1-3 --no-shapefile --parts-dir $W/parts --out $W/out/\$n || exit 1
  done
  $MPI $PY model.py $CFG --alliance A5_full,A5_full_P10 --sites $S --seeds 1-3 --no-merge --parts-dir $W/parts"
tail -1 $W/run.log
$PY tools/phased_sim_summary.py --out $DEV/output/phased_sim_subset302.csv \
  --model $W/out/full $W/out/full_P10 $W/out/full_P20 $W/out/high $W/out/high_P10 \
  --alliance $W/parts/alliance_A5_full/* $W/parts/alliance_A5_full_P10/* \
  --posthoc full:$W/out/full
