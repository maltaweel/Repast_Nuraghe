#!/usr/bin/env bash
# chain_halves.sh (staged 11 Nov 2026; revised 11 Nov: no-signal handover) = chain.sh with the DISPATCH ORDER
# "halves-first" and a PARKED-OLD-CHAIN handover instead of stopping chain.sh:
#   order: 1) pending gids with base_row < 256 (row < 3328) in none, then mixed, then full (= a complete Saltelli N=256
#          design per scenario: SALib sobol.sample(N=256, same seed, scramble) == the first 3,328 rows of design.csv,
#          verified 11 Nov), then 2) pending gids with base_row >= 256 in none, mixed, full.
#   own lock  /tmp/nuraghe_coopsobol_v17_halves.lock (one chain_halves at a time);
#   own pool  WORKERS_HALVES (re-read before every dispatch, 0-16; shipped at 0 = paused);
#   own log   logs/chain_halves.log (so logs/chain.log stays the old chain's log and its last line is its state);
#   own PID   CHAIN_PID_HALVES (written by the script itself).
#   OLD-CHAIN GUARD (no process is ever signalled): chain.sh is parked with `echo 0 > WORKERS` and idles in sleep loops.
#     At start this script REFUSES (exit 4) unless ALL of:
#       (a) ./WORKERS reads 0;
#       (b) the old chain is parked: the last line of logs/chain.log is a "PAUSED (WORKERS 0; nothing running)" line,
#           OR the old chain is not running at all (its lock /tmp/nuraghe_coopsobol_v17_chain.lock is free; this script
#           then HOLDS that lock too, on fd 8, so chain.sh cannot be (re)started while chain_halves runs);
#       (c) no `coopsobol_v17.py eval` process is running (pgrep -f '[c]oopsobol_v17.py eval').
#     Before EVERY dispatch it re-checks (a) and (b); if either fails (somebody raised WORKERS, the old chain logged
#     anything after PAUSED): no new dispatch, running evaluations finish, exit 8.
#   Everything else as chain.sh: .ok skip, oom guard (exit 9), code-sum + mapping check, memrun, nice 10, env.
#   `bash chain_halves.sh --dry` prints the pending order (first 20 + counts per segment) and the guard status, and
#   exits; it takes no lock, writes nothing, dispatches nothing.
#   switch: README.md, "Switch to halves-first order".
set -uo pipefail
D=@WORK_DIR@
FA=@RUN_DIR@
PY=@PYTHON@
MR=$FA/code_v17/memrun.py
LOG=$D/logs/chain_halves.log
OLDLOG=$D/logs/chain.log
OLDLOCK=/tmp/nuraghe_coopsobol_v17_chain.lock
LOCK=/tmp/nuraghe_coopsobol_v17_halves.lock
WF=$D/WORKERS_HALVES
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export OMPI_MCA_btl=self NUMBA_CACHE_DIR=$D/numba_cache
# COOPSOBOL_MAX_DAYS=200000 (the authors, 10 Nov): the safety stop max_days 20,000 censored the slow-corner
# pilot row; a stop only (finished runs are unchanged). Set before the first evaluation, so all evaluations agree.
export COOPSOBOL_MAX_DAYS=200000
unset PYTHONPATH

# halves-first order of the pending gids (input: pending gids one per line in gid order, as `coopsobol_v17.py ids`)
order_halves() { awk '{ r = $1 % 6656; if (int(r / 13) < 256) print; else rest[++n] = $1 }
                      END { for (i = 1; i <= n; i++) print rest[i] }'; }
# ---- old-chain guard pieces (read-only checks; nothing is signalled) ----
old_workers_zero() { [ "$(tr -dc '0-9' < $D/WORKERS 2>/dev/null)" = "0" ]; }
old_parked_line() { tail -1 $OLDLOG 2>/dev/null | grep -q 'PAUSED (WORKERS 0; nothing running)'; }
evals_running() { pgrep -f '[c]oopsobol_v17.py eval' > /dev/null; }
old_lock_free() { flock -n $OLDLOCK true 2>/dev/null; }   # momentary test; no lasting effect

if [ "${1:-}" = "--dry" ]; then   # no lock, no log, no dispatch
  cd $D || exit 1
  ORD=$($PY coopsobol_v17.py ids | order_halves)
  echo "DRY RUN (nothing dispatched). ORDER halves-first; pending $(echo $ORD | wc -w) of 19968"
  echo "first 20 (gid scenario row base_row):"
  echo "$ORD" | head -20 | awk '{ s = int($1 / 6656); r = $1 % 6656; split("none mixed full", n, " ");
                                  printf "  %5d %-5s row %4d base_row %3d\n", $1, n[s + 1], r, int(r / 13) }'
  echo "pending per segment, in dispatch order:"
  echo "$ORD" | awk '{ s = int($1 / 6656); r = $1 % 6656; h = (int(r / 13) < 256) ? "base_row<256 " : "base_row>=256";
                       split("none mixed full", n, " "); k = h " " n[s + 1];
                       if (!(k in c)) { o[++m] = k; f[k] = $1 }; c[k]++; l[k] = $1 }
                     END { for (i = 1; i <= m; i++) printf "  %d. %s %-5s: %5d pending (gid %d .. %d)\n",
                                                            i, substr(o[i], 1, 13), substr(o[i], 15), c[o[i]], f[o[i]], l[o[i]] }'
  echo "start guard now (a launch would $( old_workers_zero && { old_parked_line || old_lock_free; } && ! evals_running \
        && echo PROCEED || echo 'REFUSE, exit 4')):"
  echo "  (a) WORKERS reads 0:                $(old_workers_zero && echo yes || echo "NO (reads '$(cat $D/WORKERS)')")"
  echo "  (b) old chain parked (last line PAUSED): $(old_parked_line && echo yes || echo NO)"
  echo "      or old chain not running (old lock free): $(old_lock_free && echo yes || echo NO)"
  echo "      last line of logs/chain.log: $(tail -1 $OLDLOG | cut -c1-110)"
  echo "  (c) no coopsobol_v17.py eval running: $(evals_running && echo "NO ($(pgrep -f '[c]oopsobol_v17.py eval' | tr '\n' ' '))" || echo yes)"
  echo "  own lock $LOCK: $(flock -n $LOCK true 2>/dev/null && echo free || echo HELD)"
  echo "  WORKERS_HALVES: $(cat $WF 2>/dev/null || echo missing)"
  exit 0
fi

if [ "$(nice)" -lt 10 ]; then exec nice -n $((10 - $(nice))) bash "$0" "$@"; fi
exec 9> $LOCK
if ! flock -n 9; then echo "$(date '+%F %T') another chain_halves holds $LOCK"; exit 3; fi
cd $D
mkdir -p logs evals
lg() { echo "== $(date '+%F %T') $*" >> $LOG; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
echo $$ > $D/CHAIN_PID_HALVES
lg "ORDER halves-first (chain_halves.sh): base_row < 256 in none, mixed, full; then base_row >= 256 in none, mixed, full"
lg "COOPSOBOL HALVES CHAIN START pid $$ (-> CHAIN_PID_HALVES) nice $(nice); workers file $WF ($(cat $WF 2>/dev/null)); code $FA/code_v17"

# ---- old-chain start guard: (a) WORKERS 0, (b) old chain PAUSED or not running, (c) no eval running ----
OLDHELD=0
if ! old_workers_zero; then lg "REFUSE: ./WORKERS reads '$(cat $D/WORKERS 2>/dev/null)', not 0 (park chain.sh first); exit 4"; exit 4; fi
exec 8> $OLDLOCK
if flock -n 8; then OLDHELD=1; lg "guard (b): old chain not running; holding $OLDLOCK so chain.sh cannot start"
else
  exec 8>&-
  if ! old_parked_line; then
    lg "REFUSE: old chain holds $OLDLOCK and the last line of logs/chain.log is not PAUSED: $(tail -1 $OLDLOG | cut -c1-160); exit 4"; exit 4
  fi
  lg "guard (b): old chain parked: $(tail -1 $OLDLOG | cut -c1-120)"
fi
if evals_running; then lg "REFUSE: coopsobol_v17.py eval running (pids $(pgrep -f '[c]oopsobol_v17.py eval' | tr '\n' ' ')); exit 4"; exit 4; fi
lg "guard: WORKERS 0, old chain parked/absent, no eval running: PASS"
guard_ok() { old_workers_zero && { [ $OLDHELD = 1 ] || old_parked_line; }; }

# ---- code and mapping check (no simulation) ----
BADSUM=$(cd $FA/code_v17 && sha256sum -c ../CODE_V17_SHA256SUMS 2>/dev/null | grep -v ': OK$' | grep -v '^\./tests/')
if [ -n "$BADSUM" ]; then   # tests/test_v17_lift.py already differed when staged (10 Nov); tests are not run here
  lg "STOP: code_v17 differs from CODE_V17_SHA256SUMS outside tests/: $(echo $BADSUM | cut -c1-300)"; exit 5
fi
if ! $PY coopsobol_v17.py check > logs/check_mapping_prestart_halves.log 2>&1; then
  lg "STOP: coopsobol_v17.py check failed (logs/check_mapping_prestart_halves.log)"; exit 5
fi
lg "code_v17 sums OK (outside tests/); mapping check PASS (logs/check_mapping_prestart_halves.log)"

TOT=19968
ndone() { find evals -name 'eval_*.ok' 2>/dev/null | wc -l; }
read_workers() {   # integer 0-16 from ./WORKERS_HALVES; anything else: keep the previous value (0 at start)
  local w; w=$(tr -dc '0-9' < $WF 2>/dev/null)
  if [ -n "$w" ] && [ "$w" -le 16 ]; then echo $w; else echo ${WCUR:-0}; fi
}
okpath() { local s=$(( $1 / 6656 )) r=$(( $1 % 6656 )) n; n=(none mixed full)
  printf 'evals/%s/%02d/eval_%05d' ${n[$s]} $((r / 1000)) $r; }
IDS=$($PY coopsobol_v17.py ids | order_halves)
DN0=$(ndone); T0=$(date +%s); K0=$(oomk); WCUR=$(read_workers)
lg "DISPATCH READY: $(echo $IDS | wc -w) of $TOT evaluations to run ($DN0 done); workers $WCUR$([ "$WCUR" = 0 ] && echo ' (PAUSED: echo N > WORKERS_HALVES to start)'); oom_kill $K0; cgroup memory.max $(cat /sys/fs/cgroup/memory.max), cpu.max $(cat /sys/fs/cgroup/cpu.max)"

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
    [ "$W" != "$WCUR" ] && { lg "WORKERS_HALVES $WCUR -> $W"; WCUR=$W; }
    n=$(jobs -rp | wc -l)
    if [ "$n" -lt "$W" ]; then
      guard_ok && break
      STOP=2; break 2   # old chain no longer parked (WORKERS raised or chain.log moved on): never dispatch alongside it
    fi
    if [ "$n" -gt 0 ]; then wait -n 2>/dev/null; else
      [ $((npause % 60)) = 0 ] && lg "PAUSED (WORKERS_HALVES 0; nothing running); rechecking every 60 s, logged hourly"
      npause=$((npause + 1)); sleep 60; fi
  done
  npause=0
  [ -f $(okpath $gid).ok ] && continue   # re-check: done meanwhile (cannot happen while the old chain is parked)
  run_one $gid &
done
if [ $STOP = 2 ]; then
  lg "STOP: old-chain guard failed (WORKERS '$(cat $D/WORKERS 2>/dev/null)', logs/chain.log last: $(tail -1 $OLDLOG | cut -c1-120)); no new dispatch; waiting for the $(jobs -rp | wc -l) running evaluations"
  wait
  lg "STOP: running evaluations finished; done $(ndone)/$TOT; exit 8 (re-park chain.sh: echo 0 > WORKERS, wait for its PAUSED, relaunch)"
  exit 8
fi
if [ $STOP = 1 ]; then
  lg "STOP: oom_kill rose ($K0 -> $(oomk)); no new dispatch; waiting for the $(jobs -rp | wc -l) running evaluations"
  wait
  lg "STOP: running evaluations finished; done $(ndone)/$TOT; exit 9 (fix memory / lower WORKERS_HALVES, then relaunch)"
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
