#!/usr/bin/env bash
# V14 NEAR-FACE RERUN (specified by the authors): the affected entries of the audited
# 455-entry list (v14_nearface/AFFECTED.tsv) on code_v14_nearface with quarry.near_site_fixed_face_m = 1000.
# Copy of code/full_chain.sh: ONE serialized chain, every simulation under the shared lock /tmp/nuraghe_dev.lock,
# wall time + memory per step (memrun.py), stop if the cgroup oom_kill counter rises. Seeds 1-100. A failed run is
# logged and the chain goes on. Resumable (model.py skips seeds on disk; a finished entry has
# v14_nearface/outputs/logs/q_<label>.ok). Outputs only under v14_nearface/outputs (mirror of full_audited/outputs);
# the audited outputs are never written. Notes: "- V14 ..." lines in full_audited/FULL_NOTES.md.
#   start / RESUME after a restart:
#     cd $NURAGHE_RUN_DIR && \
#     nohup bash code_v14_nearface/v14_chain.sh >> v14_nearface/outputs/logs/chain_v14.out 2>&1 &
set -uo pipefail
W=${NURAGHE_RUN_DIR:?set NURAGHE_RUN_DIR to the run folder (see README)}
V=$W/v14_nearface
C=$W/code_v14_nearface
O=$V/outputs
PY=${PYTHON:-python3}
NS=$W/FULL_NOTES.md
LOG=$O/logs/chain_v14.log
Q=$V/queue_v14.tsv
export PYTHONDONTWRITEBYTECODE=1
note() { echo "- V14 CHAIN $(date '+%m-%d %H:%M') $*" >> $NS; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
if pgrep -f '[m]odel\.py .*--(alliance|pre|scenario|lit)' >/dev/null; then echo "another model.py is running: start the chain alone"; exit 3; fi
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
  echo "- V14 PROGRESS $dn/$tot ETA $(date -d "@$(( $(date +%s) + rem ))" '+%m-%d %H:%M') ($(date '+%m-%d %H:%M'))" >> $NS
}
A="--seeds 1-100 --no-shapefile"
note "START v14 near-face chain (code $C; queue $Q; outputs $O)"
progress
while IFS=$'\t' read -r -u 3 prio label kind est ranks cfg args; do
  [ -f $O/logs/q_$label.ok ] && continue
  step q_$label mpirun --allow-run-as-root --oversubscribe -n $ranks $PY model.py $cfg $A $args
  if [ $RC = 0 ]; then touch $O/logs/q_$label.ok; else note "FAILED q_$label (exit $RC): continuing"; fi
  progress
done 3< <(tail -n +2 $Q)
note "QUEUE DONE"
