#!/usr/bin/env bash
# v12 (2 Nov 2026) census chain: ONE serialized chain, every simulation under the shared lock /tmp/nuraghe_dev.lock,
# wall time + memory per step (memrun.py), stop if the cgroup oom_kill counter rises. Seeds 1-100 everywhere. A failed
# run is logged and the chain goes on. Resumable (model.py skips seeds on disk; a finished queue entry has
# outputs/logs/q_<label>.ok). After every queue entry a line "PROGRESS done/total ETA hh:mm" goes to code/V12_NOTES.md.
#   start:  nohup bash code/v12_chain.sh > outputs/logs/chain.out 2>&1 &
#   STEPS:  i = identity (v12 code, census switches OFF, MR_P10 full island vs the v11 MR_P10 part files)
#           q = the queue (outputs/queue.tsv, tools/v12_queue.py)
#   CUTOFF: no queue entry is started whose estimated end (x 1.1) is after this time (default 2026-11-03 08:00);
#           such entries are listed in outputs/logs/dropped.tsv.
set -uo pipefail
W=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v12-census
C=$W/code
O=$W/outputs
REF=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v11/outputs/cache/runs/alliance_MOST_REALISTIC_P10
PY=${PYTHON:-python3}
STEPS=${STEPS-"i q"}
CUTOFF=${CUTOFF:-"2026-11-03 08:00"}
CUT=$(date -d "$CUTOFF" +%s)
NS=$C/V12_NOTES.md
LOG=$O/logs/chain_aud.log
export PYTHONDONTWRITEBYTECODE=1
has() { [[ " $STEPS " == *" $1 "* ]]; }
note() { echo "- CHAIN $(date '+%m-%d %H:%M') $*" >> $NS; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
if pgrep -f '^[^ ]*python[0-9.]* [^ ]*model\.py ' >/dev/null; then echo "another model.py is running: start the chain alone"; exit 3; fi
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
  done 4< <(tail -n +2 $O/queue_aud.tsv)
  echo "- PROGRESS $dn/$tot ETA $(date -d "@$(( $(date +%s) + rem ))" '+%m-%d %H:%M') ($(date '+%m-%d %H:%M'))" >> $NS
}
A="--seeds 1-100 --no-shapefile"
if has i; then
  step i_MOST_REALISTIC_P10_off mpirun --allow-run-as-root --oversubscribe -n 6 $PY model.py $O/config_v12.yaml $A \
       --alliance MOST_REALISTIC_P10 --out $O/identity/MOST_REALISTIC_P10 --parts-dir $O/identity/parts
  [ $RC != 0 ] && { note "STOP (identity run failed)"; exit 2; }
  step i_compare $PY $C/tools/compare_parts.py $REF $O/identity/parts/alliance_MOST_REALISTIC_P10 --out $O/identity/IDENTITY.txt
  [ $RC != 0 ] && { note "STOP (IDENTITY FAIL: see outputs/identity/IDENTITY.txt)"; exit 2; }
  note "IDENTITY PASS (full island, v12 code with every census switch off vs the v11 MR_P10 part files; outputs/identity/IDENTITY.txt)"
fi
if has q; then
  [ -f $O/logs/dropped.tsv ] || printf "prio\tlabel\test_s\treason\n" > $O/logs/dropped.tsv
  progress
  while IFS=$'\t' read -r -u 3 prio label kind est ranks cfg args; do
    [ -f $O/logs/q_$label.ok ] && continue
    now=$(date +%s)
    if [ $((now + est * 11 / 10)) -gt $CUT ]; then
      printf "%s\t%s\t%s\tnot started: estimated end after %s\n" "$prio" "$label" "$est" "$CUTOFF" >> $O/logs/dropped.tsv
      note "DROPPED q_$label (prio $prio, est $est s): would end after $CUTOFF"
      continue
    fi
    step q_$label mpirun --allow-run-as-root --oversubscribe -n $ranks $PY model.py $cfg $A $args
    if [ $RC = 0 ]; then touch $O/logs/q_$label.ok; else note "FAILED q_$label (exit $RC): continuing"; fi
    progress
  done 3< <(tail -n +2 $O/queue_aud.tsv)
  note "QUEUE DONE"
fi
