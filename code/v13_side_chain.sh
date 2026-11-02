#!/bin/bash
# Side chain for the 5 staged v13 social entries (run as specified by the authors). The main chain's p23 queue is already
# open through a pipe, so new rows cannot be inserted there; these entries take the same flock per run and
# interleave with the main chain. Same .ok markers and log as full_chain.sh; no CUTOFF needed (0.45 h total).
F=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v12-census/full_audited
O=$F/outputs; LOG=$O/logs/chain_full.log; PY=${PYTHON:-python3}; C=$F/code
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
while IFS=$'\t' read -r -u 3 prio label kind est ranks cfg args; do
  [ -f $O/logs/q_$label.ok ] && continue
  n=q_$label; k0=$(oomk)
  echo "== $(date '+%F %T') START $n (oom_kill $k0) [v13 side chain]" | tee -a $LOG
  flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $O/logs/$n.mem -- bash -c "$args" > $O/logs/$n.log 2>&1 < /dev/null
  RC=$?; k1=$(oomk)
  echo "== $(date '+%F %T') END $n exit $RC (oom_kill $k0 -> $k1) $(tail -1 $O/logs/$n.mem) [v13 side chain]" | tee -a $LOG
  [ $RC = 0 ] && touch $O/logs/q_$label.ok
  [ "$k1" != "$k0" ] && { echo "STOP side chain: oom_kill rose" | tee -a $LOG; exit 9; }
done 3< <(tail -n +2 $F/queue_v13_social_STAGED.tsv)
echo "== $(date '+%F %T') v13 side chain DONE" | tee -a $LOG
