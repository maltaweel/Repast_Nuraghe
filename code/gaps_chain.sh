#!/usr/bin/env bash
# 1 Nov 2026 scenario gaps: ONE serialized chain of full-island runs (7,167 sites, seeds 1-100, 6 ranks as the 30 Oct
# MOST_REALISTIC runs), every run under the shared lock /tmp/nuraghe_dev.lock, wall time + memory per step
# (memrun.py), stop if the cgroup oom_kill counter rises or a step fails. Resumable (model.py skips seeds on disk).
#   start: nohup bash code/gaps_chain.sh > outputs/logs/chain.out 2>&1 &
#   STEPS: i = identity (MOST_REALISTIC_P10 with this code, compared with the delivered 30 Oct part files)
#          r = the S10-S14 runs (NAMES overrides the list); s = summary tables
set -uo pipefail
G=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-01-scenario-gaps
C=$G/code
O=$G/outputs
CFG=$O/config_1101.yaml
REF=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/output_1030/cache/runs
PY=${PYTHON:-python3}
MPI="mpirun --allow-run-as-root --oversubscribe -n 6"
STEPS=${STEPS-"i r s"}
SEEDS=1-100
NS=$C/NEW_SCENARIOS_1101.md
LOG=$O/logs/chain.log
export PYTHONDONTWRITEBYTECODE=1
has() { [[ " $STEPS " == *" $1 "* ]]; }
note() { echo "- CHAIN $(date '+%H:%M') $*" >> $NS; }
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
if pgrep -f '^[^ ]*python[0-9.]* [^ ]*model\.py ' >/dev/null; then echo "another model.py is running: start the chain alone"; exit 3; fi
cd $C
step() {
  local n=$1; shift; local k0; k0=$(oomk)
  echo "== $(date '+%F %T') START $n (oom_kill $k0)" | tee -a $LOG
  flock /tmp/nuraghe_dev.lock $PY $C/memrun.py $O/logs/$n.mem -- "$@" > $O/logs/$n.log 2>&1
  local rc=$? k1; k1=$(oomk)
  local mem; mem=$(tail -1 $O/logs/$n.mem | grep -o 'wall [0-9.]* s\|peak tree PSS [0-9]* MB\|cgroup peak [0-9]* MB' | paste -sd' ')
  echo "== $(date '+%F %T') END $n exit $rc (oom_kill $k0 -> $k1) $(tail -1 $O/logs/$n.mem)" | tee -a $LOG
  note "$n exit $rc; $mem; oom_kill $k0->$k1"
  if [ "$k1" != "$k0" ]; then note "STOP (oom_kill rose in $n)"; exit 9; fi
  if [ $rc != 0 ]; then note "STOP ($n failed, exit $rc)"; exit $rc; fi
}
A="--seeds $SEEDS --no-shapefile"
if has i; then
  step i_MOST_REALISTIC_P10 $MPI $PY model.py $CFG $A --alliance MOST_REALISTIC_P10 --out $O/identity/out
  step i_compare $PY $C/tools/compare_parts.py $REF/alliance_MOST_REALISTIC_P10 $O/cache/runs/alliance_MOST_REALISTIC_P10 \
       --out $O/identity/IDENTITY.txt
fi
NAMES=${NAMES:-$($PY -c "import yaml;print(' '.join(n + '_P10' for n in yaml.safe_load(open('$CFG'))['alliance_gaps']))")}
if has r; then
  for n in $NAMES; do step r_$n $MPI $PY model.py $CFG $A --alliance $n; done
fi
if has s; then
  step s_summary $PY tools/gaps_summary.py $CFG --parts $O/cache/runs --ref-parts $REF \
       --names "$(echo $NAMES | tr ' ' ,)" --out $O/summary
fi
note "DONE (STEPS '$STEPS')"
