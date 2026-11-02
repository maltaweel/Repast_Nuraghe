#!/usr/bin/env bash
# body of tests/mr_join_subset.sh (runs while holding /tmp/nuraghe_dev.lock)
set -uo pipefail
M=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/merged
PY=${PYTHON:-python3}
cd $M
echo "== $(date +%T) lock acquired; oom_kill $(awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events)"
bash tests/identity_merged_nolock.sh > subset/identity_merged_join.out 2>&1
echo "identity: $(grep -c PASS subset/identity_merged_join.out) PASS, $(grep -c 'differ -> FAIL' subset/identity_merged_join.out) FAIL (2 FAIL = rank-count part names, known)"
grep -E "FAIL|oom" subset/identity_merged_join.out
O=$M/subset/mr; S=$(cat $M/sites300_real.txt)
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
step() { n=$1; shift; k0=$(oomk); $PY $M/memrun.py $O/logs/$n.log -- "$@" > $O/logs/$n.out 2>&1
         echo "== $n: $(grep memrun $O/logs/$n.log | tail -1 | cut -c1-100)"; [ "$(oomk)" = "$k0" ] || { echo "oom_kill rose"; exit 9; }; }
# keep the 11:30 (pre-join) MR runs as the handover reference
[ -d $O/alliance_prejoin ] || { mv $O/alliance $O/alliance_prejoin; mkdir -p $O/alliance; for n in A3_trust_learning A0_alone MOST_REALISTIC_alone_P10 MOST_REALISTIC_alone_P20 MOST_REALISTIC_alone_P100; do cp -a $O/alliance_prejoin/$n $O/alliance/; done; }
A="--sites $S --seeds 1-3 --no-shapefile --out $O/alliance --parts-dir $O/parts"
MPI1="mpirun --allow-run-as-root --oversubscribe -n 1"
for n in MOST_REALISTIC_handover_P10 MOST_REALISTIC_handover_P20 MOST_REALISTIC_handover_P100 \
         MOST_REALISTIC_P10 MOST_REALISTIC_P20 MOST_REALISTIC_P100 \
         MOST_REALISTIC_alone_P10 MOST_REALISTIC_alone_P20 MOST_REALISTIC_alone_P100; do
  step $n $MPI1 $PY model.py config.yaml $A --alliance $n --fresh
done
$PY tools/mr_join_check.py --root $O | tee $O/join_check.out
$PY tools/mr_subset_compare.py --alliance $O/alliance --lit $M/subset/ident/real --parts $O/parts \
    --names MOST_REALISTIC_P10,MOST_REALISTIC_P20,MOST_REALISTIC_P100,MOST_REALISTIC_handover_P10,MOST_REALISTIC_handover_P20,MOST_REALISTIC_handover_P100,MOST_REALISTIC_alone_P10,MOST_REALISTIC_alone_P20,MOST_REALISTIC_alone_P100,A3_trust_learning,A0_alone \
    | tee $O/compare_join.out
$PY tools/network_need.py --root $O/alliance --out $O/network_need_join --pairs \
    MOST_REALISTIC_P10:MOST_REALISTIC_alone_P10 MOST_REALISTIC_handover_P10:MOST_REALISTIC_alone_P10 \
    MOST_REALISTIC_P20:MOST_REALISTIC_alone_P20 MOST_REALISTIC_handover_P20:MOST_REALISTIC_alone_P20 \
    MOST_REALISTIC_P100:MOST_REALISTIC_alone_P100 MOST_REALISTIC_handover_P100:MOST_REALISTIC_alone_P100 \
    A3_trust_learning:A0_alone > $O/network_need_join.out 2>&1
echo "== $(date +%T) done; oom_kill $(oomk)"
