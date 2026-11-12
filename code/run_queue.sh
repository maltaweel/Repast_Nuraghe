#!/usr/bin/env bash
# Runs the queue of the model (config/queue.tsv) with code/, one entry at a time (README, "Run the queue").
# Run folder $NURAGHE_RUN_DIR: code -> the repository's code/, configs/ = config/scenarios/*.yaml (data_dir set),
# queue.tsv = config/queue.tsv with @RUN_DIR@ / @PYTHON@ replaced, outputs/caches/<config name>/ = the prepared
# tables of each config (+ its own runs/). ONE serialized chain, every step under the shared lock
# /tmp/nuraghe_dev.lock, memrun per step, stop if the cgroup oom_kill counter rises (Linux cgroup v2). Failed
# entries are logged and the chain goes on. Resumable (outputs/logs/q_<label>.ok). Notes: "- QUEUE ..." lines.
#   start / RESUME:
#     cd $NURAGHE_RUN_DIR && \
#     nohup bash code/run_queue.sh >> outputs/logs/chain.out 2>&1 &
set -uo pipefail
W=${NURAGHE_RUN_DIR:?set NURAGHE_RUN_DIR to the run folder (see README)}
C=$W/code
O=$W/outputs
PY=${PYTHON:-python3}
NS=$W/NOTES.md
LOG=$O/logs/chain.log
Q=$W/queue.tsv
export PYTHONDONTWRITEBYTECODE=1
exec 9> /tmp/nuraghe_queue_chain.lock
if ! flock -n 9; then echo "another queue chain holds /tmp/nuraghe_queue_chain.lock"; exit 3; fi
note() { echo "- QUEUE CHAIN $(date '+%m-%d %H:%M') $*" >> $NS; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
mkdir -p $O/logs
cd $C
RC=0
step() {
  local n=$1; shift; local k0; k0=$(oomk)
  echo "== $(date '+%F %T') START $n (oom_kill $k0)" | tee -a $LOG
  flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $O/logs/$n.mem -- "$@" > $O/logs/$n.log 2>&1 < /dev/null
  RC=$?; local k1; k1=$(oomk)
  local mem; mem=$(tail -1 $O/logs/$n.mem | grep -o 'wall [0-9.]* s\|peak tree PSS [0-9]* MB\|cgroup peak [0-9]* MB' | paste -sd' ')
  echo "== $(date '+%F %T') END $n exit $RC (oom_kill $k0 -> $k1) $(tail -1 $O/logs/$n.mem)" | tee -a $LOG
  note "$n exit $RC; $mem; oom_kill $k0->$k1"
  if [ "$k1" != "$k0" ]; then note "STOP (oom_kill rose in $n)"; exit 9; fi
}
progress() {
  local tot=0 dn=0 rem=0
  while IFS=$'\t' read -r -u 4 prio label kind est rest; do
    tot=$((tot + 1))
    if [ -f $O/logs/q_$label.ok ]; then dn=$((dn + 1)); else rem=$((rem + est)); fi
  done 4< <(tail -n +2 $Q)
  echo "- QUEUE PROGRESS $dn/$tot ETA $(date -d "@$(( $(date +%s) + rem ))" '+%m-%d %H:%M') ($(date '+%m-%d %H:%M'))" >> $NS
}
A="--seeds 1-100 --no-shapefile"
note "START queue chain (code $C; queue $Q; outputs $O)"
progress
while IFS=$'\t' read -r -u 3 prio label kind est ranks cfg args; do
  [ -f $O/logs/q_$label.ok ] && continue
  if [ "$kind" = cmd ]; then
    step q_$label bash -c "$args"
  else
    step q_$label mpirun --allow-run-as-root --oversubscribe -n $ranks $PY model.py $cfg $A $args
  fi
  if [ $RC = 0 ]; then touch $O/logs/q_$label.ok; else note "FAILED q_$label (exit $RC): continuing"; fi
  progress
done 3< <(tail -n +2 $Q)
note "QUEUE DONE"
