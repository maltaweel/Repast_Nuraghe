#!/usr/bin/env bash
# MOST_REALISTIC subset test: the REALISTIC 300-site stratified subset (sites300_real.txt), seeds 1-3, 1 rank, under the
# shared lock. Runs MOST_REALISTIC_P10/_P20/_P100, their A0-equivalents (_alone_*), A3_trust_learning, A0_alone;
# REALISTIC and webster (lit) come from tests/identity_merged.sh (subset/ident/real). Then tools/mr_subset_compare.py.
set -uo pipefail
M=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/merged
PY=${PYTHON:-python3}
O=$M/subset/mr; mkdir -p $O/logs
S=$(cat $M/sites300_real.txt)
MPI1="mpirun --allow-run-as-root --oversubscribe -n 1"
export PYTHONDONTWRITEBYTECODE=1
cd $M
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
step() { n=$1; shift; k0=$(oomk); flock /tmp/nuraghe_dev.lock $PY $M/memrun.py $O/logs/$n.log -- "$@" > $O/logs/$n.out 2>&1
         echo "== $n: $(grep memrun $O/logs/$n.log | tail -1)"; [ "$(oomk)" = "$k0" ] || { echo "oom_kill rose"; exit 9; }; }
A="--sites $S --seeds 1-3 --no-shapefile --out $O/alliance --parts-dir $O/parts"
for n in MOST_REALISTIC_P10 MOST_REALISTIC_P20 MOST_REALISTIC_P100 MOST_REALISTIC_alone_P10 MOST_REALISTIC_alone_P20 \
         MOST_REALISTIC_alone_P100 A3_trust_learning A0_alone; do
  step $n $MPI1 $PY model.py config.yaml $A --alliance $n
done
$PY tools/mr_subset_compare.py --alliance $O/alliance --lit $M/subset/ident/real --parts $O/parts | tee $O/compare.out
$PY tools/network_need.py --root $O/alliance --out $O/network_need --pairs MOST_REALISTIC_P10:MOST_REALISTIC_alone_P10 \
    MOST_REALISTIC_P20:MOST_REALISTIC_alone_P20 MOST_REALISTIC_P100:MOST_REALISTIC_alone_P100 A3_trust_learning:A0_alone
