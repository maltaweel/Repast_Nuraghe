#!/usr/bin/env bash
# V16_FINAL RUN (5 Nov 2026; approved by the authors). Code: code/ = code_v16_final (CHANGES_V16_FINAL.md,
# CODE_V16_FINAL_SHA256SUMS): add4 L2 bedrock_everywhere + L3 load_per_tonne default ON, L1 / L4 default OFF; fixes
# D3 (no dress work -> no dress help, walk, trust or credit), D6 (join parties priced at their own skill), D11 (site
# stone = class of its gated face 0); run signature = CODE_VERSION 2026-11-05-v16_final + effective add4 settings.
# queue_v16_final.tsv (432 entries: the model entries of queue_v15.tsv, same order, on the v16_final configs; no prep
# entry: the v16_final code needs no new table). Configs = the v15 configs with output_dir -> v16_final/outputs and one
# cache_dir PER CONFIG (v16_final/outputs/caches/<stem>: the prepared tables of that config's v15 cache, rebuilt with
# code/ (README), + its own runs/), so no v16_final run reuses a part file of an earlier version.
# Copy of v15_chain.sh (paths, lock name, note tag only). ONE serialized chain, every step under the shared lock
# /tmp/nuraghe_dev.lock, memrun per step, stop if the cgroup oom_kill counter rises. Failed entries are logged and the
# chain goes on. Resumable (q_<label>.ok). Outputs only under v16_final/outputs. Notes: "- V16F ..." lines.
#   start / RESUME:
#     cd $NURAGHE_RUN_DIR && \
#     nohup bash v16_final/v16f_chain.sh >> v16_final/outputs/logs/chain_v16f.out 2>&1 &
set -uo pipefail
W=${NURAGHE_RUN_DIR:?set NURAGHE_RUN_DIR to the run folder (see README)}
V=$W/v16_final
C=$W/code_v16_final
O=$V/outputs
PY=${PYTHON:-python3}
NS=$W/FULL_NOTES.md
LOG=$O/logs/chain_v16f.log
Q=$V/queue_v16_final.tsv
export PYTHONDONTWRITEBYTECODE=1
exec 9> /tmp/nuraghe_v16f_chain.lock
if ! flock -n 9; then echo "another v16f chain holds /tmp/nuraghe_v16f_chain.lock"; exit 3; fi
note() { echo "- V16F CHAIN $(date '+%m-%d %H:%M') $*" >> $NS; }
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
  echo "- V16F PROGRESS $dn/$tot ETA $(date -d "@$(( $(date +%s) + rem ))" '+%m-%d %H:%M') ($(date '+%m-%d %H:%M'))" >> $NS
}
A="--seeds 1-100 --no-shapefile"
note "START v16_final chain (code $C; queue $Q; outputs $O)"
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
