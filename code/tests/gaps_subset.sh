#!/usr/bin/env bash
# 1 Nov 2026 scenario gaps: subset test (300 stratified sites, seeds 1-3, 1 rank) under the shared lock.
#   (1) identity: MOST_REALISTIC_P10 with the v8 code vs this code (switches off) -> outputs/test_subset/identity
#   (2) every new scenario once (smoke test + timing + memory)
set -uo pipefail
G=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-01-scenario-gaps
V8=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/merged
C=$G/code
CFG=$G/outputs/config_1101.yaml
PY=${PYTHON:-python3}
T=$G/outputs/test_subset; mkdir -p $T/logs
S=$(cat $C/sites300_real.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n 1"
A="--sites $S --seeds 1-3 --no-shapefile"
export PYTHONDONTWRITEBYTECODE=1
step() { n=$1; d=$2; shift 2; echo "== $(date +%T) $n"; (cd $d && flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $T/logs/$n.mem -- "$@" > $T/logs/$n.log 2>&1); echo "   exit $? $(tail -1 $T/logs/$n.mem)"; }
if [[ " ${STEPS:-1 2} " == *" 1 "* ]]; then
  step v8_MR_P10 $V8 $MPI $PY model.py $CFG $A --alliance MOST_REALISTIC_P10 --out $T/v8 --parts-dir $T/v8_parts
  step new_MR_P10 $C $MPI $PY model.py $CFG $A --alliance MOST_REALISTIC_P10 --out $T/new --parts-dir $T/new_parts
fi
if [[ " ${STEPS:-1 2} " == *" 2 "* ]]; then
  for n in ${NAMES:-$($PY -c "import yaml;print(' '.join(yaml.safe_load(open('$CFG'))['alliance_gaps']))")}; do
    step ${n}_P10 $C $MPI $PY model.py $CFG $A --alliance ${n}_P10 --out $T/new --parts-dir $T/new_parts
  done
fi
