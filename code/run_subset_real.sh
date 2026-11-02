#!/usr/bin/env bash
# REALISTIC subset runs: 300 stratified sites (sites300.txt), seeds 1-3, 1 rank, under the shared dev lock.
#   ident : all lit scenarios, RUN code vs DEV code (identity check)     (default: both steps)
set -uo pipefail
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix
DEV=$R/dev_real
PY=${PYTHON:-python3}
MEM=$R/scratch/memrun.py
S=$(cat $DEV/sites300.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n ${NR:-1}"
O=$DEV/subset; mkdir -p $O/logs
A="--sites $S --seeds 1-3 --no-shapefile"
export PYTHONDONTWRITEBYTECODE=1
step() { n=$1; shift; echo "== $(date +%T) $n"; flock /tmp/nuraghe_dev.lock $PY $MEM $O/logs/$n.log -- "$@" > $O/logs/$n.out 2>&1; tail -2 $O/logs/$n.log; }
step run_lit $MPI $PY $R/model.py $R/config.yaml $A --lit all --out $O/run --parts-dir $O/run_parts
step dev_lit $MPI $PY $DEV/model.py $DEV/config.yaml $A --lit all --out $O/dev --parts-dir $O/dev_parts
