#!/usr/bin/env bash
# FIX1030 rerun, 30 Oct 2026: ONLY what the 30 Oct fixes change (BUGFIX_REPORT B14-B16): the MOST_REALISTIC family and
# its derived products, from the FIXED merged code, into a NEW root RUN/output_1030/ (old results stay in output_new/).
#   start (detached):  nohup bash merged/rerun1030.sh > RUN/output_1030_chain.out 2>&1 &
# Season-length runs (40/120/210 d) are NOT rerun (specified by the authors); only the 90-day runs.
# Census: not run for MR (tools/census.py has no --names and was never run for MR; formation + components cover MR).
#
# Every step: START/END line with wall time, memory (memrun.py) and the cgroup oom_kill counter; the chain STOPS if
# oom_kill rises or a step fails (except the Morris runs, see r). Every simulation runs under flock /tmp/nuraghe_dev.lock.
# Progress lines go to RUN/NEW_SCENARIOS.md with the prefix FIX1030. Resumable: model.py skips seeds on disk.
# STEPS="g r h" (default all); STEPS="h" reruns only the post-processing.
#
# Wall-time estimate (min) from the 29 Oct night chain (output_new/logs/night_chain.log, same 6 ranks / 8 GB cgroup),
# plus a margin for the longer post-fix builds:
#   g  MR join P10 353 s, P20 744 s, P100 1,545 s; handover P10 ~360 s (29 Oct: rescued, merge only 34 s; per-seed
#      cost = join), P20 397 s, P100 1,274 s; alone P10 141 s, P20 145 s, P100 157 s = 5,116 s ............... ~90
#   r  Morris MR_P10: design 4 s + 60 runs x 1 seed, 6 parallel 281 s + analyse ~5 s ......................   ~5
#   h  MR networks 401 s, formation 30 s, components 8 s, formation plot 2 s, centrality of the 6 MR network
#      scenarios ~30 s each (977 s / 35 scenarios on 29 Oct) ~180 s, workforce/years ~32 s, network need 62 s,
#      master table 128-151 s ..................................................................................  ~14
# TOTAL ~1 h 50 min (range 1 h 40 - 2 h 05).
set -uo pipefail
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix
M=$R/merged
ON=$R/output_new                                  # 29 Oct results (pre-fix MR; every non-MR new scenario)
O=$R/output_1030                                  # NEW root for the fixed MR family
PY=${PYTHON:-python3}
STEPS=${STEPS-"g r h"}
SEEDS=1-100
MPI="mpirun --allow-run-as-root --oversubscribe -n"
export PYTHONDONTWRITEBYTECODE=1
NS=$R/NEW_SCENARIOS.md
has() { [[ " $STEPS " == *" $1 "* ]]; }
note() { echo "- FIX1030 $(date '+%H:%M') rerun1030: $*" >> $NS; }
[ -z "${STEPS// }" ] && { echo "STEPS empty: nothing to do"; exit 0; }
# argv[0] must be a python interpreter (an unanchored pattern also matched an agent process whose argv quotes it)
if pgrep -f '^[^ ]*python[0-9.]* [^ ]*model\.py ' >/dev/null; then echo "another model.py is running: start the rerun alone"; exit 3; fi
grep -q 'TECH_VERSION = "2026-10-30-fix1030"' $M/alliance.py || { echo "merged/alliance.py is not the fixed code"; exit 2; }

# ---------------------------------------------------------------- setup: new root, its config and cache (inputs symlinked)
mkdir -p $O/logs $O/cache/runs $O/cache/alliance
for f in cost_mu haul materiale_use.csv outcrop_code.tif site_stone_sets.csv sites_haul.csv stones4 sea; do
  [ -e $O/cache/$f ] || ln -s "$(readlink -f $M/cache/$f)" $O/cache/$f
done
for f in kbest.npz kbest_mu038.npz; do
  [ -e $O/cache/alliance/$f ] || ln -s "$(readlink -f $M/cache/alliance/$f)" $O/cache/alliance/$f
done
CFG=$O/config_1030.yaml                           # = merged/config.yaml with cache_dir / output_dir -> output_1030
sed -e "s|^  cache_dir: cache$|  cache_dir: $O/cache|" -e "s|^  output_dir: output$|  output_dir: $O|" $M/config.yaml > $CFG
grep -q "cache_dir: $O/cache" $CFG && grep -q "output_dir: $O\$" $CFG || { echo "config rewrite failed"; exit 2; }
cd $M
LOG=$O/logs/rerun1030.log
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
step() {   # step NAME CMD... : under the lock, timed, memory-logged; stop on oom_kill increase or failure
  local n=$1; shift; local k0; k0=$(oomk)
  echo "== $(date '+%F %T') START $n (oom_kill $k0)" | tee -a $LOG
  flock /tmp/nuraghe_dev.lock $PY $M/memrun.py $O/logs/$n.mem -- "$@" > $O/logs/$n.log 2>&1
  local rc=$? k1; k1=$(oomk)
  local mem; mem=$(tail -1 $O/logs/$n.mem | grep -o 'wall [0-9.]* s\|peak tree PSS [0-9]* MB\|cgroup peak [0-9]* MB' | paste -sd' ')
  echo "== $(date '+%F %T') END $n exit $rc (oom_kill $k0 -> $k1) $(tail -1 $O/logs/$n.mem)" | tee -a $LOG
  note "$n exit $rc; $mem; oom_kill $k0->$k1"
  if [ "$k1" != "$k0" ]; then echo "STOP: oom_kill rose during $n" | tee -a $LOG; note "STOP (oom_kill rose in $n)"; exit 9; fi
  if [ $rc != 0 ]; then echo "STOP: $n failed (exit $rc)" | tee -a $LOG; note "STOP ($n failed, exit $rc)"; exit $rc; fi
}
A="--seeds $SEEDS --no-shapefile"
MR="MOST_REALISTIC_P10 MOST_REALISTIC_P20 MOST_REALISTIC_P100"                         # help_mode join
MRH="MOST_REALISTIC_handover_P10 MOST_REALISTIC_handover_P20 MOST_REALISTIC_handover_P100"
MRA="MOST_REALISTIC_alone_P10 MOST_REALISTIC_alone_P20 MOST_REALISTIC_alone_P100"
note "START (STEPS '$STEPS'; root $O; ETA ~1 h 50 min)"

# ---------------------------------------------------------------- g: MOST_REALISTIC family, 100 seeds, 6 ranks (as 29 Oct)
if has g; then
  for n in $MR $MRH $MRA; do step g_$n $MPI 6 $PY model.py $CFG $A --alliance $n; done
fi
# ---------------------------------------------------------------- r: Morris screen of MOST_REALISTIC_P10 (join), 60 runs
# A run that cannot finish within max_seasons (29 Oct: run_019, pull 20 kg + drag 0.03 m/s + 2,000 t) is a feasibility
# limit, not a failure (specified by the authors): its command is listed in failed.txt and the analysis runs on the others.
if has r; then
  MO=$O/morris_most_realistic_P10
  step r_morris_design $PY tools/morris_mr.py design --cfg $CFG --out $MO --r 10 --seed 2026
  step r_morris_runs bash -c "xargs -P 6 -I CMD bash -c 'CMD > /dev/null 2>&1 || echo FAILED: CMD' < $MO/commands.txt > $MO/failed.txt; echo \"failed/censored runs: \$(wc -l < $MO/failed.txt) of \$(wc -l < $MO/commands.txt)\"; exit 0"
  note "Morris runs failed/censored: $(wc -l < $MO/failed.txt) of $(wc -l < $MO/commands.txt) ($(grep -o 'run_[0-9]*' $MO/failed.txt | sort -u | paste -sd' '))"
  step r_morris_analyse $PY tools/morris_mr.py analyse --out $MO
fi
# ---------------------------------------------------------------- h: MR-derived products
if has h; then
  step h_mr_networks $PY tools/alliance_networks.py $CFG $MR $MRH --jobs 2
  step h_mr_formation $PY tools/formation.py $CFG --names "$(echo $MR $MRH | tr ' ' ,)" --out-sub formation_most_realistic
  step h_mr_components $PY tools/components.py $CFG --names "$(echo $MR $MRH | tr ' ' ,)" --out-sub formation_most_realistic \
       --cuts 50,100,200,400,end
  step h_mr_formation_plot $PY tools/formation_plot.py $O/formation_most_realistic
  # centrality, cooperation + communication layers (the _alone twins have no help network: excluded, as 29 Oct)
  step h_centrality_mr $PY tools/centrality.py $MR $MRH --cache $O/cache --out-root $O --out $O/centrality
  step h_workforce_years $PY tools/workforce_years.py --root $O --out $O/analysis
  # network need: MR join and handover vs the alone twin (all from output_1030); A3 vs A0 from the base rerun
  step h_network_need $PY tools/network_need.py --root $R/output/scenarios_alliance $ON/scenarios_alliance $O/scenarios_alliance \
       --out $O/network_need --pairs MOST_REALISTIC_P10:MOST_REALISTIC_alone_P10 MOST_REALISTIC_P20:MOST_REALISTIC_alone_P20 \
       MOST_REALISTIC_P100:MOST_REALISTIC_alone_P100 MOST_REALISTIC_handover_P10:MOST_REALISTIC_alone_P10 \
       MOST_REALISTIC_handover_P20:MOST_REALISTIC_alone_P20 MOST_REALISTIC_handover_P100:MOST_REALISTIC_alone_P100 \
       A3_trust_learning:A0_alone
  # master table: every scenario a row; a name in a later root replaces the earlier one -> MR rows from output_1030
  step h_master_table $PY tools/master_table.py --roots $R/output $ON $O --caches $R/cache $ON/cache $O/cache \
       --ratings $R/REALISM_RATINGS.md --out $O/master
fi
echo "== $(date '+%F %T') rerun1030 done" | tee -a $LOG
note "DONE (outputs in output_1030/; old MR results kept in output_new/)"
