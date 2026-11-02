#!/usr/bin/env bash
# FULL AUDITED rerun (specified by the authors): every current scenario on config_full_audited.yaml (AUDITED_LIT, all 9 audited
# values, adult_share 0.4) with ONE frozen code version = this folder (full_audited/code, checksums in
# full_audited/CODE_SHA256SUMS). Adapted from code/aud_chain.sh: ONE serialized chain, every simulation under the shared
# lock /tmp/nuraghe_dev.lock, wall time + memory per step (memrun.py), stop if the cgroup oom_kill counter rises.
# Seeds 1-100 everywhere. A failed run is logged and the chain goes on. Resumable (model.py skips seeds on disk; a
# finished queue entry has full_audited/outputs/logs/q_<label>.ok). After every queue entry a line
# "PROGRESS done/total ETA" goes to full_audited/FULL_NOTES.md.
#   start:  cd $NURAGHE_RUN_DIR && \
#           nohup bash code/full_chain.sh > outputs/logs/chain_full.out 2>&1 &
#   QUEUES: full_audited/queue_full.tsv (priority 1), then full_audited/queue_full_p23.tsv (priorities 2-3) if it
#           exists. The second file is read when the chain reaches it, so it can be added while the chain runs.
#   STEPS:  q = the queues (there is no identity step: no reference exists for the audited parameter set)
#   CUTOFF: no queue entry is started whose estimated end (x 1.1) is after this time (default 2026-11-04 08:00);
#           such entries are listed in full_audited/outputs/logs/dropped.tsv.
# RESUME after a restart: same start command (STEPS=q is the default); finished entries are skipped by their .ok marker.
set -uo pipefail
W=${NURAGHE_RUN_DIR:?set NURAGHE_RUN_DIR to the run folder (see README)}
C=$W/code
O=$W/outputs
PY=${PYTHON:-python3}
STEPS=${STEPS-"q"}
CUTOFF=${CUTOFF:-"2026-11-04 08:00"}
CUT=$(date -d "$CUTOFF" +%s)
NS=$W/FULL_NOTES.md
LOG=$O/logs/chain_full.log
Q1=$W/queue_full.tsv
Q23=$W/queue_full_p23.tsv
export PYTHONDONTWRITEBYTECODE=1
has() { [[ " $STEPS " == *" $1 "* ]]; }
note() { echo "- CHAIN $(date '+%m-%d %H:%M') $*" >> $NS; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
queues() { tail -n +2 $Q1; [ -f $Q23 ] && tail -n +2 $Q23; true; }
if pgrep -f '^[^ ]*python[0-9.]* [^ ]*model\.py ' >/dev/null; then echo "another model.py is running: start the chain alone"; exit 3; fi
[ -f $W/config_full_audited.yaml ] || { echo "missing $W/config_full_audited.yaml"; exit 2; }
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
progress() {   # done/total and ETA from the remaining entries' estimates
  local tot=0 dn=0 rem=0
  while IFS=$'\t' read -r -u 4 prio label kind est rest; do
    tot=$((tot + 1))
    if [ -f $O/logs/q_$label.ok ]; then dn=$((dn + 1)); else rem=$((rem + est)); fi
  done 4< <(queues)
  echo "- PROGRESS $dn/$tot ETA $(date -d "@$(( $(date +%s) + rem ))" '+%m-%d %H:%M') ($(date '+%m-%d %H:%M'))" >> $NS
}
A="--seeds 1-100 --no-shapefile"
if has q; then
  [ -f $O/logs/dropped.tsv ] || printf "prio\tlabel\test_s\treason\n" > $O/logs/dropped.tsv
  note "START full audited chain (code $C; queues $Q1 + $([ -f $Q23 ] && echo $Q23 || echo 'no p23 file yet'); CUTOFF $CUTOFF)"
  progress
  for QF in $Q1 $Q23; do
    [ -f $QF ] || { note "queue $QF not present: skipped"; continue; }
    while IFS=$'\t' read -r -u 3 prio label kind est ranks cfg args; do
      [ -f $O/logs/q_$label.ok ] && continue
      now=$(date +%s)
      if [ $((now + est * 11 / 10)) -gt $CUT ]; then
        printf "%s\t%s\t%s\tnot started: estimated end after %s\n" "$prio" "$label" "$est" "$CUTOFF" >> $O/logs/dropped.tsv
        note "DROPPED q_$label (prio $prio, est $est s): would end after $CUTOFF"
        continue
      fi
      if [ "$kind" = cmd ]; then           # entries not runnable through model.py: the args column is the full command
        step q_$label bash -c "$args"
      else
        step q_$label mpirun --allow-run-as-root --oversubscribe -n $ranks $PY model.py $cfg $A $args
      fi
      if [ $RC = 0 ]; then touch $O/logs/q_$label.ok; else note "FAILED q_$label (exit $RC): continuing"; fi
      progress
    done 3< <(tail -n +2 $QF)
  done
  note "QUEUE DONE"
fi
