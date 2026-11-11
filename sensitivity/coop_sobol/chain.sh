#!/usr/bin/env bash
# COOPERATION-MODEL SOBOL on code_v17 (STAGED 10 Nov 2026; PI option (b): N=512, 11 factors of the 28 Oct Sobol,
# scenarios none, mixed, full). README.md. 19,968 evaluations = 6,656 design rows (Saltelli N=512, k=11) x 3 scenarios,
# one seed each (seed = base_row + 1). One evaluation per process (python coopsobol_v17.py eval --gid G, wrapped in
# memrun), run by a pool of W parallel workers. Order: all of none, then mixed, then full (gid = s * 6656 + row).
# W = the integer in ./WORKERS, re-read before EVERY dispatch. SHIPPED AT 0 = paused: launching the chain runs NOTHING
# until WORKERS is raised (echo 2 > WORKERS). Lowering it lets the running evaluations finish; 0 pauses again.
# No /tmp/nuraghe_dev.lock (it would serialise everything); the pool is the semaphore. nice 10 (set here, children
# inherit). OMPI_MCA_btl=self (MPI singleton, no /dev/shm segment); 1 BLAS/OMP/numba thread; numba cache in ./numba_cache.
# Resumable: evaluations with evals/<scen>/NN/eval_RRRRR.ok are skipped; an eval killed mid-way leaves no .ok and no
# result (the CSV is written atomically before the marker).
# oom_kill rises (cgroup memory.events) => no new dispatch, running evals finish, STOP (exit 9).
# When all 19,968 are done: analyse.py -> COOPSOBOL_RESULTS.md.
#   start / RESUME (nothing runs while WORKERS is 0):
#     cd @WORK_DIR@ && \
#     nohup bash chain.sh >> logs/chain.out 2>&1 < /dev/null & echo $! > CHAIN_PID
#   then: echo N > WORKERS
#   progress: tail logs/chain.log ; find evals -name '*.ok' | wc -l   (19968 = done)
set -uo pipefail
D=@WORK_DIR@
FA=@RUN_DIR@
PY=@PYTHON@
MR=$FA/code_v17/memrun.py
LOG=$D/logs/chain.log
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export OMPI_MCA_btl=self NUMBA_CACHE_DIR=$D/numba_cache
# COOPSOBOL_MAX_DAYS=200000 (the authors, 10 Nov): the safety stop max_days 20,000 censored the slow-corner
# pilot row; a stop only (finished runs are unchanged). Set before the first evaluation, so all evaluations agree.
export COOPSOBOL_MAX_DAYS=200000
unset PYTHONPATH

if [ "$(nice)" -lt 10 ]; then exec nice -n $((10 - $(nice))) bash "$0" "$@"; fi
exec 9> /tmp/nuraghe_coopsobol_v17_chain.lock
if ! flock -n 9; then echo "$(date '+%F %T') another coopsobol chain holds /tmp/nuraghe_coopsobol_v17_chain.lock"; exit 3; fi
cd $D
mkdir -p logs evals
lg() { echo "== $(date '+%F %T') $*" >> $LOG; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
lg "COOPSOBOL CHAIN START pid $$ nice $(nice); workers file $D/WORKERS ($(cat $D/WORKERS 2>/dev/null)); code $FA/code_v17"

# ---- code and mapping check (no simulation) ----
BADSUM=$(cd $FA/code_v17 && sha256sum -c ../CODE_V17_SHA256SUMS 2>/dev/null | grep -v ': OK$' | grep -v '^\./tests/')
if [ -n "$BADSUM" ]; then   # tests/test_v17_lift.py already differed when staged (10 Nov); tests are not run here
  lg "STOP: code_v17 differs from CODE_V17_SHA256SUMS outside tests/: $(echo $BADSUM | cut -c1-300)"; exit 5
fi
if ! $PY coopsobol_v17.py check > logs/check_mapping_prestart.log 2>&1; then
  lg "STOP: coopsobol_v17.py check failed (logs/check_mapping_prestart.log)"; exit 5
fi
lg "code_v17 sums OK (outside tests/); mapping check PASS (logs/check_mapping_prestart.log)"

TOT=19968
ndone() { find evals -name 'eval_*.ok' 2>/dev/null | wc -l; }
read_workers() {   # integer 0-16 from ./WORKERS; anything else: keep the previous value (0 at start)
  local w; w=$(tr -dc '0-9' < $D/WORKERS 2>/dev/null)
  if [ -n "$w" ] && [ "$w" -le 16 ]; then echo $w; else echo ${WCUR:-0}; fi
}
okpath() { local s=$(( $1 / 6656 )) r=$(( $1 % 6656 )) n; n=(none mixed full)
  printf 'evals/%s/%02d/eval_%05d' ${n[$s]} $((r / 1000)) $r; }
IDS=$($PY coopsobol_v17.py ids)
DN0=$(ndone); T0=$(date +%s); K0=$(oomk); WCUR=$(read_workers)
lg "DISPATCH READY: $(echo $IDS | wc -w) of $TOT evaluations to run ($DN0 done); workers $WCUR$([ "$WCUR" = 0 ] && echo ' (PAUSED: echo N > WORKERS to start)'); oom_kill $K0; cgroup memory.max $(cat /sys/fs/cgroup/memory.max), cpu.max $(cat /sys/fs/cgroup/cpu.max)"

run_one() {   # one evaluation; START / END lines with wall, peak memory, oom_kill, progress, ETA
  local gid=$1 f d k0 k1 RC m dn el eta
  f=$(okpath $gid); d=$(dirname $f)
  mkdir -p $d
  k0=$(oomk)
  echo "== $(date '+%F %T') START gid $gid $f (oom_kill $k0)" >> $LOG
  $PY $MR $f.mem -- $PY coopsobol_v17.py eval --gid $gid < /dev/null > /dev/null 2>&1
  RC=$?; k1=$(oomk)
  m=$(tail -1 $f.mem 2>/dev/null | cut -c1-200)
  dn=$(find evals -name 'eval_*.ok' | wc -l); el=$(( $(date +%s) - T0 ))
  if [ $((dn - DN0)) -gt 0 ]; then eta=$(date -d "@$(( $(date +%s) + el * (TOT - dn) / (dn - DN0) ))" '+%m-%d %H:%M'); else eta=?; fi
  echo "== $(date '+%F %T') END gid $gid exit $RC $([ -f $f.ok ] && echo ok || echo NO-OK) (oom_kill $k0 -> $k1) $m | done $dn/$TOT ETA $eta" >> $LOG
  [ $RC = 0 ] || echo "== $(date '+%F %T') FAILED gid $gid (exit $RC): continuing; rerun the chain to retry" >> $LOG
}

STOP=0; npause=0
for gid in $IDS; do
  [ -f $(okpath $gid).ok ] && continue
  while :; do
    if [ "$(oomk)" != "$K0" ]; then STOP=1; break 2; fi
    W=$(read_workers)
    [ "$W" != "$WCUR" ] && { lg "WORKERS $WCUR -> $W"; WCUR=$W; }
    n=$(jobs -rp | wc -l)
    [ "$n" -lt "$W" ] && break
    if [ "$n" -gt 0 ]; then wait -n 2>/dev/null; else
      [ $((npause % 60)) = 0 ] && lg "PAUSED (WORKERS 0; nothing running); rechecking every 60 s, logged hourly"
      npause=$((npause + 1)); sleep 60; fi
  done
  npause=0
  run_one $gid &
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
  $PY analyse.py > logs/analyse.log 2>&1; lg "END analyse exit $? (COOPSOBOL_RESULTS.md)"
else
  lg "not all evaluations ok: relaunch the chain to retry the missing ones (analyse.py runs when all are done)"
fi
lg "CHAIN END"
