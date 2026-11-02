#!/usr/bin/env bash
# MOST_REALISTIC_P10 at season_days 40/120/210 (specified by the authors), 100 seeds each, after the night chain. 90 = output_new.
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix; M=$R/merged; PY=${PYTHON:-python3}
cd $M
while pgrep -f 'merged/night_chain.sh' >/dev/null; do sleep 60; done
oom() { awk '$1=="oom_kill"{print $2}' /sys/fs/cgroup/memory.events; }
for d in 40 120 210; do
  O=$R/output_season$d; o0=$(oom); echo "== $(date +%T) START season$d (oom_kill $o0)"
  flock /tmp/nuraghe_dev.lock $PY $M/memrun.py $O/logs/MR_P10_season$d.mem -- mpirun --allow-run-as-root --oversubscribe -n 6 $PY model.py $O/config_season$d.yaml --seeds 1-100 --no-shapefile --alliance MOST_REALISTIC_P10 > $O/logs/MR_P10_season$d.log 2>&1; rc=$?
  o1=$(oom); echo "== $(date +%T) END season$d exit $rc (oom_kill $o0 -> $o1) $(tail -1 $O/logs/MR_P10_season$d.mem 2>/dev/null)"
  [ "$o1" != "$o0" ] && { echo "OOM: stop"; exit 9; }
done
echo "== $(date +%T) SEASONS DONE"
