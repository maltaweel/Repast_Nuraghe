#!/usr/bin/env bash
# V15 RERUN (specified by the authors: min_haul_flatm 100 -> 15 and the near-site face rule, on every scenario):
# queue_v15.tsv (469 entries: 37 cmd prep, checkpoint set, haul10 sensitivity, rest of the 455 audited entries, 10 v13
# social entries, 2 radius) on code_v15_haul15 (v13 switches + near-face rule) with the v15 configs.
# Copy of code_v14_nearface/v14_chain.sh + cmd entries as in code/full_chain.sh (args = the full command).
# ONE serialized chain, every step under the shared lock /tmp/nuraghe_dev.lock, wall + memory per step (memrun.py),
# stop if the cgroup oom_kill counter rises. Failed entries are logged and the chain goes on. Resumable (finished
# entries have v15_haul15/outputs/logs/q_<label>.ok; model.py reuses seeds on disk). Outputs only under
# v15_haul15/outputs. Notes: "- V15 ..." lines in full_audited/FULL_NOTES.md.
#   start / RESUME:
#     cd $NURAGHE_RUN_DIR && \
#     nohup bash v15_haul15/v15_chain.sh >> v15_haul15/outputs/logs/chain_v15.out 2>&1 &
set -uo pipefail
W=${NURAGHE_RUN_DIR:?set NURAGHE_RUN_DIR to the run folder (see README)}
V=$W/v15_haul15
C=$W/code_v15_haul15
O=$V/outputs
PY=${PYTHON:-python3}
NS=$W/FULL_NOTES.md
LOG=$O/logs/chain_v15.log
Q=$V/queue_v15.tsv
export PYTHONDONTWRITEBYTECODE=1
exec 9> /tmp/nuraghe_v15_chain.lock
if ! flock -n 9; then echo "another v15 chain holds /tmp/nuraghe_v15_chain.lock"; exit 3; fi
note() { echo "- V15 CHAIN $(date '+%m-%d %H:%M') $*" >> $NS; }
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
  echo "- V15 PROGRESS $dn/$tot ETA $(date -d "@$(( $(date +%s) + rem ))" '+%m-%d %H:%M') ($(date '+%m-%d %H:%M'))" >> $NS
}
A="--seeds 1-100 --no-shapefile"
note "START v15 chain (code $C; queue $Q; outputs $O)"
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
