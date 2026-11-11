#!/usr/bin/env bash
# SOBOL RUN 2 on the v17 headline (10 Nov 2026; approved by the authors 9 Nov). README.md.
# 14,336 evaluations (design.csv; Saltelli N=512, k=26), one evaluation (= one design row x seeds 1-3) per process
# (python sobol2_v17.py eval --id N, wrapped in memrun), run by a pool of W parallel workers.
# W = the integer in ./WORKERS, re-read before EVERY dispatch (raise it to 8 later without a restart; 0 = pause;
# lowering it lets the running evaluations finish). No /tmp/nuraghe_dev.lock (it would serialise everything); the
# pool is the semaphore. nice 10 (set here, children inherit). OMPI_MCA_btl=self (single-process MPI singleton:
# no 16 MB /dev/shm segment per process; /dev/shm is 64 MB).
# PRECONDITION: waits until the v17 lift rerun chain (full_audited/v17/rerun_v17_lift.sh) has ENDED: no process
# 'bash .../rerun_v17_lift.sh' left (found via /proc, never pgrep -f) AND its log v17/logs/chain_v17.log ends with
# its final line "CHAIN END" (written after "QUEUE DONE (n/41 rows ok ...)"). If the chain is gone without that line
# (STOP / crash), HOLD: log and recheck every 10 min (a relaunched v17 chain is waited for again). SOBOL2_FORCE=1
# skips the log-line test (never the process test).
# PRECONDITION 2 (9 Nov): ALSO wait until full_audited/v17/SAMPLE_REF_DONE exists (the short side chain of
# reference reruns for the docking sample runs right after the v17 chain and creates it); checked every 5 min, logged
# at the first check and hourly. Both conditions are rechecked together until both hold.
# Resumable: evaluations with evals/NN/eval_NNNNN.ok are skipped; an eval killed mid-way leaves no .ok and no result.
# oom_kill rises (cgroup memory.events) => no new dispatch, running evals finish, STOP (exit 9).
# When all 14,336 are done: analyse.py -> SOBOL2_RESULTS.md.
#   start / RESUME:
#     cd @WORK_DIR@ && \
#     nohup bash chain.sh >> logs/chain.out 2>&1 < /dev/null & echo $! > CHAIN_PID
#   progress: tail logs/chain.log ; find evals -name '*.ok' | wc -l   (14336 = done)
set -uo pipefail
D=@WORK_DIR@
FA=@RUN_DIR@
V17LOG=$FA/v17/logs/chain_v17.log
REFDONE=$FA/v17/SAMPLE_REF_DONE        # created by the docking-sample reference side chain (runs after the v17 chain)
PY=@PYTHON@
MR=$FA/code_v17s/memrun.py
LOG=$D/logs/chain.log
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export OMPI_MCA_btl=self
unset PYTHONPATH

if [ "$(nice)" -lt 10 ]; then exec nice -n $((10 - $(nice))) bash "$0" "$@"; fi
exec 9> /tmp/nuraghe_sobol2_v17_chain.lock
if ! flock -n 9; then echo "$(date '+%F %T') another sobol2 chain holds /tmp/nuraghe_sobol2_v17_chain.lock"; exit 3; fi
cd $D
mkdir -p logs evals
lg() { echo "== $(date '+%F %T') $*" >> $LOG; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }

# ---- precondition: the v17 lift rerun chain has ended ----
v17_pids() {   # PIDs whose argv is 'bash <...>/rerun_v17_lift.sh|rerun_v17_sample_ref.sh [args]' (not --dry); /proc scan,
               # no pgrep -f (the sample-ref side chain is waited for too, so no v17 job is left when we start)
  local p a0 a1 a2
  for p in /proc/[0-9]*; do
    [ -r $p/cmdline ] || continue
    a0= a1= a2=
    { IFS= read -r -d '' a0; IFS= read -r -d '' a1; IFS= read -r -d '' a2; } < $p/cmdline 2>/dev/null || true
    [ "${a0##*/}" = bash ] || [ "${a0##*/}" = sh ] || continue
    [ "${a1##*/}" = rerun_v17_lift.sh ] || [ "${a1##*/}" = rerun_v17_sample_ref.sh ] || continue
    [ "${a2:-}" = --dry ] && continue
    echo ${p#/proc/}
  done
}
v17_last() { tail -1 $V17LOG 2>/dev/null | sed 's/^== [0-9-]* [0-9:]* //'; }
lg "SOBOL2 CHAIN START pid $$ nice $(nice); workers file $D/WORKERS ($(cat $D/WORKERS 2>/dev/null)); code $FA/code_v17s"
nlog=0; nref=0
while :; do
  vp=$(v17_pids | tr '\n' ' ')
  if [ -n "$vp" ]; then
    # log at the first check and then hourly (every 12th 5-min check)
    if [ $((nlog % 12)) = 0 ]; then lg "WAIT: v17 chain / sample-ref side chain running (pid $vp; v17 last: $(tail -1 $V17LOG | cut -c1-150))"; fi
    nlog=$((nlog + 1)); nref=0; sleep 300; continue
  fi
  last=$(v17_last)
  if [ "$last" != "CHAIN END" ] && [ "${SOBOL2_FORCE:-0}" != 1 ]; then
    lg "HOLD: no v17 chain process left but chain_v17.log does not end with 'CHAIN END' (last: $(tail -1 $V17LOG | cut -c1-160)); resume the v17 chain or relaunch with SOBOL2_FORCE=1; rechecking in 10 min"
    nlog=0; nref=0; sleep 600; continue
  fi
  if [ ! -e $REFDONE ]; then
    if [ $((nref % 12)) = 0 ]; then lg "WAIT: v17 chain ended ('$last'), waiting for $REFDONE (docking-sample reference side chain); rechecking every 5 min"; fi
    nref=$((nref + 1)); nlog=0; sleep 300; continue
  fi
  break
done
lg "PRECONDITION OK: v17 chain ended ($(grep -a 'QUEUE DONE' $V17LOG | tail -1 | cut -c1-90); last line '$(v17_last)'; force=${SOBOL2_FORCE:-0}); no v17 / sample-ref process left; $REFDONE exists ($(stat -c '%y' $REFDONE | cut -c1-19))"

# ---- import / mapping check (no simulation) ----
if ! $PY sobol2_v17.py check > logs/check_mapping_prestart.log 2>&1; then
  lg "STOP: sobol2_v17.py check failed (logs/check_mapping_prestart.log)"; exit 5
fi
lg "mapping check PASS ($(grep -c . logs/check_mapping_prestart.log) lines; logs/check_mapping_prestart.log)"

TOT=$(($(wc -l < design.csv) - 1))
ndone() { find evals -name 'eval_*.ok' 2>/dev/null | wc -l; }
read_workers() {   # integer 0-16 from ./WORKERS; anything else: keep the previous value
  local w; w=$(tr -dc '0-9' < $D/WORKERS 2>/dev/null)
  if [ -n "$w" ] && [ "$w" -le 16 ]; then echo $w; else echo ${WCUR:-4}; fi
}
IDS=$($PY sobol2_v17.py ids)
DN0=$(ndone); T0=$(date +%s); K0=$(oomk); WCUR=$(read_workers)
export D LOG PY MR TOT DN0 T0
lg "DISPATCH START: $(echo $IDS | wc -w) of $TOT evaluations to run ($DN0 done); workers $WCUR; oom_kill $K0; cgroup memory.max $(cat /sys/fs/cgroup/memory.max), cpu.max $(cat /sys/fs/cgroup/cpu.max)"

run_one() {   # one evaluation; START / END lines with wall, peak memory, oom_kill, progress, ETA
  local id=$1 f b k0 k1 RC m dn el eta
  f=$(printf 'eval_%05d' $id); b=evals/$(printf '%02d' $((id / 1000)))
  mkdir -p $b
  k0=$(oomk)
  echo "== $(date '+%F %T') START $f (oom_kill $k0)" >> $LOG
  $PY $MR $b/$f.mem -- $PY sobol2_v17.py eval --id $id < /dev/null > /dev/null 2>&1
  RC=$?; k1=$(oomk)
  m=$(tail -1 $b/$f.mem 2>/dev/null | cut -c1-220)
  dn=$(find evals -name 'eval_*.ok' | wc -l); el=$(( $(date +%s) - T0 ))
  if [ $((dn - DN0)) -gt 0 ]; then eta=$(date -d "@$(( $(date +%s) + el * (TOT - dn) / (dn - DN0) ))" '+%m-%d %H:%M'); else eta=?; fi
  echo "== $(date '+%F %T') END $f exit $RC $([ -f $b/$f.ok ] && echo ok || echo NO-OK) (oom_kill $k0 -> $k1) $m | done $dn/$TOT ETA $eta" >> $LOG
  [ $RC = 0 ] || echo "== $(date '+%F %T') FAILED $f (exit $RC): continuing; rerun the chain to retry" >> $LOG
}

STOP=0
for id in $IDS; do
  [ -f evals/$(printf '%02d' $((id / 1000)))/$(printf 'eval_%05d' $id).ok ] && continue
  while :; do
    if [ "$(oomk)" != "$K0" ]; then STOP=1; break 2; fi
    W=$(read_workers)
    [ "$W" != "$WCUR" ] && { lg "WORKERS $WCUR -> $W"; WCUR=$W; }
    n=$(jobs -rp | wc -l)
    [ "$n" -lt "$W" ] && break
    if [ "$n" -gt 0 ]; then wait -n 2>/dev/null; else sleep 60; fi     # W = 0: paused
  done
  run_one $id &
done
if [ $STOP = 1 ]; then
  lg "STOP: oom_kill rose ($K0 -> $(oomk)); no new dispatch; waiting for the $(jobs -rp | wc -l) running evaluations"
  wait
  lg "STOP: running evaluations finished; done $(ndone)/$TOT; exit 9 (fix memory / lower WORKERS, then relaunch)"
  exit 9
fi
wait
DN=$(ndone)
lg "QUEUE DONE ($DN/$TOT evaluations ok)"
if [ "$DN" = "$TOT" ]; then
  lg "START analyse"
  $PY analyse.py > logs/analyse.log 2>&1; lg "END analyse exit $? (SOBOL2_RESULTS.md)"
else
  lg "not all evaluations ok: relaunch the chain to retry the missing ones (analyse.py runs when all are done)"
fi
lg "CHAIN END"
