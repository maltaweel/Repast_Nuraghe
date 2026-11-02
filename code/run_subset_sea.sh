#!/usr/bin/env bash
# S9 subset runs: 300 coastal-rich sites (sites300.txt), seeds 1-3, NR ranks (default 1; 3 ranks peaked at 2.1 GB).
#   ident : sea-off identity, original code (orig/) vs DEV code: baseline, full, high, A1_ask, P_G50_hub
#   sea   : DEV sea scenarios
set -uo pipefail
DEV=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/dev_sea
PY=${PYTHON:-python3}
MEM=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/scratch/memrun.py
S=$(cat $DEV/sites300.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n ${NR:-1}"
O=$DEV/subset; mkdir -p $O/logs
A="--sites $S --seeds 1-3 --no-shapefile"
step() { n=$1; shift; echo "== $(date +%T) $n"; flock /tmp/nuraghe_dev.lock $PY $MEM $O/logs/$n.log -- "$@" | tail -1; }
if [ "${1:-all}" != sea ]; then
for W in orig dev; do
  C=$DEV; [ $W = orig ] && C=$DEV/orig
  cd $C
  step ${W}_baseline $MPI $PY $C/model.py $C/config.yaml $A --out $O/$W/baseline --parts-dir $O/$W/parts
  step ${W}_full     $MPI $PY $C/model.py $C/config.yaml $A --scenario full --out $O/$W/full --parts-dir $O/$W/parts
  step ${W}_high     $MPI $PY $C/model.py $C/config.yaml $A --scenario high --out $O/$W/high --parts-dir $O/$W/parts
  step ${W}_A1       $MPI $PY $C/model.py $C/config.yaml $A --alliance A1_ask,A5_full --out $O/$W/alliance --parts-dir $O/$W/parts
  step ${W}_pre      $MPI $PY $C/model.py $C/config.yaml $A --pre P_G50_hub --out $O/$W/pre --parts-dir $O/$W/parts
done
fi
if [ "${1:-all}" != ident ]; then
cd $DEV
for sc in S9_sea_4kn S9_sea_5kn S9_sea_6kn high_sea; do
  step dev_$sc $MPI $PY $DEV/model.py $DEV/config.yaml $A --scenario $sc --out $O/dev/$sc --parts-dir $O/dev/parts
done
step dev_alliance_sea $MPI $PY $DEV/model.py $DEV/config.yaml $A --alliance A1_ask_sea,A5_full_sea --out $O/dev/alliance --parts-dir $O/dev/parts
step dev_pre_sea $MPI $PY $DEV/model.py $DEV/config.yaml $A --pre P_G50_hub_sea --out $O/dev/pre --parts-dir $O/dev/parts
fi
echo "== $(date +%T) done"
