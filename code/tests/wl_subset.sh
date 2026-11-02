#!/usr/bin/env bash
# 1 Nov 2026 (b) wider-literature scenarios: subset test (300 stratified sites, seeds 1-3, 1 rank) under the shared lock.
#   (1) identity: MOST_REALISTIC_P10 with the 1 Nov (S10-S14) code vs this code (switches off) -> outputs/test_subset
#   (2) every new scenario once (smoke test + timing + memory)
set -uo pipefail
W=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-01-wider-lit
G=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-01-scenario-gaps/code
C=$W/code
CFG=$W/outputs/config_wl.yaml
PY=${PYTHON:-python3}
T=$W/outputs/test_subset; mkdir -p $T/logs
S=$(cat $C/sites300_real.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n 1"
A="--sites $S --seeds 1-3 --no-shapefile"
export PYTHONDONTWRITEBYTECODE=1
step() { n=$1; d=$2; shift 2; echo "== $(date +%T) $n"; (cd $d && flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $T/logs/$n.mem -- "$@" > $T/logs/$n.log 2>&1); echo "   exit $? $(tail -1 $T/logs/$n.mem)"; }
if [[ " ${STEPS:-1 2} " == *" 1 "* ]]; then
  step gaps_MR_P10 $G $MPI $PY model.py $CFG $A --alliance MOST_REALISTIC_P10 --out $T/gaps --parts-dir $T/gaps_parts
  step new_MR_P10 $C $MPI $PY model.py $CFG $A --alliance MOST_REALISTIC_P10 --out $T/new --parts-dir $T/new_parts
  $PY $C/tools/compare_parts.py $T/gaps_parts/alliance_MOST_REALISTIC_P10 $T/new_parts/alliance_MOST_REALISTIC_P10 --out $T/IDENTITY_subset.txt; tail -3 $T/IDENTITY_subset.txt
fi
if [[ " ${STEPS:-1 2} " == *" 2 "* ]]; then
  for n in ${NAMES:-$($PY -c "import yaml;print(' '.join(yaml.safe_load(open('$CFG'))['alliance_wl']))")}; do
    step ${n}_P10 $C $MPI $PY model.py $CFG $A --alliance ${n}_P10 --out $T/new --parts-dir $T/new_parts
  done
fi
