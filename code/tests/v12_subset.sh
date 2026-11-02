#!/usr/bin/env bash
# v12 (2 Nov 2026) subset test: 300 stratified sites (sites300_real.txt), seeds 1-2, 1 rank, under the shared lock.
#   STEPS=i : identity, MOST_REALISTIC_P10, v11 code vs v12 code (census switches off), part files compared
#   STEPS=s : smoke run of the census scenarios named in $SCEN (default: all 40 queue scenarios)
set -uo pipefail
W=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v12-census
V11=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v11/code
C=$W/code; O=$W/outputs
PY=${PYTHON:-python3}
T=$O/test_subset; mkdir -p $T/logs
S=$(cat $C/sites300_real.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n 1"
A="--sites $S --seeds ${SEEDS:-1-2} --no-shapefile"
export PYTHONDONTWRITEBYTECODE=1
step() { n=$1; d=$2; shift 2; echo "== $(date +%T) $n"; (cd $d && flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $T/logs/$n.mem -- "$@" > $T/logs/$n.log 2>&1); echo "   exit $? $(tail -1 $T/logs/$n.mem)"; }
if [[ " ${STEPS:-i s} " == *" i "* ]]; then
  step v11_MR_P10 $V11 $MPI $PY model.py $O/config_v12.yaml $A --alliance MOST_REALISTIC_P10 --out $T/v11 --parts-dir $T/v11_parts
  step v12_MR_P10 $C $MPI $PY model.py $O/config_v12.yaml $A --alliance MOST_REALISTIC_P10 --out $T/v12 --parts-dir $T/v12_parts
  $PY $C/tools/compare_parts.py $T/v11_parts/alliance_MOST_REALISTIC_P10 $T/v12_parts/alliance_MOST_REALISTIC_P10 --out $T/IDENTITY_subset.txt; tail -2 $T/IDENTITY_subset.txt
fi
if [[ " ${STEPS:-i s} " == *" s "* ]]; then
  for n in ${SCEN}; do
    step $n $C $MPI $PY model.py $O/config_v12.yaml $A --alliance $n --out $T/v12 --parts-dir $T/v12_parts
  done
fi
