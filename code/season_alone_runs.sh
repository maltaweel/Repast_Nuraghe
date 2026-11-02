#!/usr/bin/env bash
# alone twins + network need for the season runs (report agent 20:1x: needed for the network-need columns). Runs after season_runs.sh.
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix; M=$R/merged; PY=${PYTHON:-python3}
cd $M
sleep 120
while pgrep -f 'merged/season_runs.sh' >/dev/null || pgrep -f 'merged/night_chain.sh' >/dev/null; do sleep 60; done
oom() { awk '$1=="oom_kill"{print $2}' /sys/fs/cgroup/memory.events; }
for d in 40 120 210; do
  O=$R/output_season$d; o0=$(oom); echo "== $(date +%T) START alone season$d (oom_kill $o0)"
  flock /tmp/nuraghe_dev.lock $PY $M/memrun.py $O/logs/MR_alone_P10_season$d.mem -- mpirun --allow-run-as-root --oversubscribe -n 6 $PY model.py $O/config_season$d.yaml --seeds 1-100 --no-shapefile --alliance MOST_REALISTIC_alone_P10 > $O/logs/MR_alone_P10_season$d.log 2>&1; rc=$?
  o1=$(oom); echo "== $(date +%T) END alone season$d exit $rc (oom_kill $o0 -> $o1)"
  [ "$o1" != "$o0" ] && { echo "OOM: stop"; exit 9; }
  $PY tools/network_need.py --root $O/scenarios_alliance --out $O/network_need --pairs MOST_REALISTIC_P10:MOST_REALISTIC_alone_P10 > $O/logs/network_need.log 2>&1; echo "   network_need season$d exit $?"
done
echo "== $(date +%T) SEASON ALONE DONE"
