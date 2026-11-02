#!/usr/bin/env bash
# v11 (2 Nov 2026) subset test: 300 stratified sites (sites300_real.txt), seeds 1-3, 1 rank, under the shared lock,
# with measured memory (memrun.py), BEFORE any full-island run.
#   (1) identity: MOST_REALISTIC_P10, v10 code (1 Nov wider-literature code) vs v11 code with the v11 switches OFF
#   (2) fix ON:   MOST_REALISTIC_P10 v11 vs v10 (contents; the run signature differs by design)
#                 MR_P10_v11_pull125 (sensitivity), A2_trust_P10 and lit 'webster' (scenarios that use Webster's
#                 quarry man-days: they must change), v10 vs v11
set -uo pipefail
W=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v11
V10=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-01-wider-lit/code
C=$W/code
O=$W/outputs
PY=${PYTHON:-python3}
T=$O/test_subset; mkdir -p $T/logs
S=$(cat $C/sites300_real.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n 1"
A="--sites $S --seeds 1-3 --no-shapefile"
export PYTHONDONTWRITEBYTECODE=1
step() { n=$1; d=$2; shift 2; echo "== $(date +%T) $n"; (cd $d && flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $T/logs/$n.mem -- "$@" > $T/logs/$n.log 2>&1); echo "   exit $? $(tail -1 $T/logs/$n.mem)"; }
one() { ls -d $1/*/ | head -1; }
if [[ " ${STEPS:-1 2} " == *" 1 "* ]]; then
  step v10_MR_P10 $V10 $MPI $PY model.py $O/config_v11_off.yaml $A --alliance MOST_REALISTIC_P10 --out $T/v10 --parts-dir $T/v10_parts
  step off_MR_P10 $C $MPI $PY model.py $O/config_v11_off.yaml $A --alliance MOST_REALISTIC_P10 --out $T/off --parts-dir $T/off_parts
  $PY $C/tools/compare_parts.py $T/v10_parts/alliance_MOST_REALISTIC_P10 $T/off_parts/alliance_MOST_REALISTIC_P10 --out $T/IDENTITY_subset_off.txt; tail -2 $T/IDENTITY_subset_off.txt
fi
if [[ " ${STEPS:-1 2} " == *" 2 "* ]]; then
  step on_MR_P10 $C $MPI $PY model.py $O/config_v11.yaml $A --alliance MOST_REALISTIC_P10 --out $T/on --parts-dir $T/on_parts
  $PY $C/tools/compare_parts.py $(one $T/v10_parts/alliance_MOST_REALISTIC_P10) $(one $T/on_parts/alliance_MOST_REALISTIC_P10) --out $T/SAME_subset_on_MR_P10.txt; tail -2 $T/SAME_subset_on_MR_P10.txt
  step on_pull125 $C $MPI $PY model.py $O/config_v11_pull125.yaml $A --alliance MOST_REALISTIC_P10 --out $T/pull125 --parts-dir $T/pull125_parts
  step v10_A2_trust_P10 $V10 $MPI $PY model.py $O/config_v11_off.yaml $A --alliance A2_trust_P10 --out $T/v10 --parts-dir $T/v10_parts
  step on_A2_trust_P10 $C $MPI $PY model.py $O/config_v11.yaml $A --alliance A2_trust_P10 --out $T/on --parts-dir $T/on_parts
  step v10_lit_webster $V10 $MPI $PY model.py $O/config_v11_off.yaml $A --lit webster --out $T/v10/lit_webster --parts-dir $T/v10_parts
  step on_lit_webster $C $MPI $PY model.py $O/config_v11.yaml $A --lit webster --out $T/on/lit_webster --parts-dir $T/on_parts
fi
if [[ " ${STEPS:-1 2} " == *" 3 "* ]]; then   # model.py coop path (other_mandays_per_tower): scenario full
  step v10_full $V10 $MPI $PY model.py $O/config_v11_off.yaml $A --scenario full --out $T/v10/full --parts-dir $T/v10_parts
  step on_full $C $MPI $PY model.py $O/config_v11.yaml $A --scenario full --out $T/on/full --parts-dir $T/on_parts
fi
