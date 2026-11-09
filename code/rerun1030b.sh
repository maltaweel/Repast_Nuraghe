#!/usr/bin/env bash
# FIX1030B rerun, 30 Oct 2026: ONLY what the authors' N1 fix (BUGFIX_REPORT B22, maxcrew = max(n_coop, max hh_n)) changes,
# from the FIXED merged code, into a NEW root RUN/output_1030b/ (old results stay in output/, output_new/, output_1030/).
#   start (detached, only when told):  nohup bash merged/rerun1030b.sh > RUN/output_1030b_chain.out 2>&1 &
#
# What changes: a site-run can change only if 0 < n_coop < max hh_n <= household_size (5).
#   low:    the site-runs that qualify -> RERUN (100 seeds).
#   mixed, mostly: unchanged where no site-run qualifies (checked on the delivered seeds). Step v reruns them anyway
#           (100 seeds, ~5 min) and asserts content identity with the delivered runs; their delivered outputs stand.
#   none/full/high/patchwork, literature, S9, alliance, MOST_REALISTIC: unchanged (byte-identical on the subsets).
# Derived products that read low (all rebuilt here; every non-low row is checked against the delivered table in step k):
#   scenarios/scenario_comparison.csv + nuraghe_manhours_scenarios.shp (report.compare_scenarios, the 7 coop scenarios)
#   fastest_scenarios.csv, fastest_stage_decomposition.csv, fastest_combined_effects.csv (tools/fastest.py)
#   master_comparison.csv (tools/master_comparison.py)
#   analysis/base/phased_posthoc*.csv, workforce_years*.csv (post hoc P10/P20 and workforce/years of the base root)
#   master/master_table.csv  (= output_1030/master with the low row replaced; the report's MR rows come from here)
#   master_new/master_table.csv (= output_new/master with the low row replaced; the report asserts its non-MR rows
#                                equal output_1030/master's, so both are rebuilt)
# NOT here: a Nurnet collaborator's GPU products (Sobol/Morris/crew x drag grids, report/derived/fastest_gpu) - GPU code not on this
# machine; REF stones4 low run (stone_rule_comparison, REF product); TOST (no verdict can flip, see BUGFIX_REPORT B22).
#
# Layout: $O/base_root = a mirror of RUN/output built from symlinks, EXCEPT scenarios/low, the comparison files and the
# four regenerated top-level tables, which are real files written here (a guard refuses to write through any symlink).
# Every step: START/END with wall time, memory (memrun.py) and the cgroup oom_kill counter; stops on oom_kill or failure.
# Every simulation runs under flock /tmp/nuraghe_dev.lock. Progress lines -> RUN/NEW_SCENARIOS.md, prefix FIX1030B.
# STEPS="g v c d h k" (default all); resumable (model.py skips seeds on disk).
#
# Wall-time estimate (min) from the REF/base logs (8 ranks: low model 136.7 s, mixed 131.3 s, mostly 131.1 s per 100
# seeds; fastest 43.7 s; master_comparison 1 s) and the 29 Oct night chain (phased_posthoc_base 21-22 s,
# workforce_years_base 71-74 s, master_table 128-151 s):
#   g  low, 100 seeds, 8 ranks, + merge/summary/shapefile ..........................................  ~3.5
#   v  mixed + mostly verification, 100 seeds each, 8 ranks, + identity check ..........................  ~5.5
#   c  compare_scenarios (7 coop scenarios) ...........................................................  ~0.5
#   d  fastest + master_comparison ....................................................................  ~1
#   h  phased_posthoc + workforce_years (base root) ~1.6; master tables x2 ~5 ............................  ~6.5
#   k  checks vs delivered tables .....................................................................  ~0.5
# TOTAL ~17 min (range 15-22). Peak memory: 8 ranks ~4.9 GB PSS / ~7 GB cgroup (S9/lit/TOST runs of 29-30 Oct).
set -uo pipefail
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix
M=$R/merged
B=$R/output                                       # delivered base root (cooperation, lit, alliance, pre, crew, GPU)
ON=$R/output_new                                  # 29 Oct new scenarios
O30=$R/output_1030                                # 30 Oct MR fix
O=${O1030B_ROOT:-$R/output_1030b}                 # NEW root for the N1 fix (O1030B_ROOT: dry-run root)
BR=$O/base_root
PY=${PYTHON:-python3}
STEPS=${STEPS-"g v c d h k"}
MPI="mpirun --allow-run-as-root --oversubscribe -n"
export PYTHONDONTWRITEBYTECODE=1
NS=${NS_FILE:-$R/NEW_SCENARIOS.md}
COOP="none low mixed mostly full high patchwork"
has() { [[ " $STEPS " == *" $1 "* ]]; }
note() { echo "- FIX1030B $(date '+%H:%M') rerun1030b: $*" >> $NS; }
[ -z "${STEPS// }" ] && { echo "STEPS empty: nothing to do"; exit 0; }
if pgrep -f '^[^ ]*python[0-9.]* [^ ]*model\.py ' >/dev/null; then echo "another model.py is running: start the rerun alone"; exit 3; fi
grep -q 'SPLIT_VERSION = "2026-10-30b-maxcrew"' $M/model.py && grep -q 'maxcrew = max(self.n_coop' $M/model.py \
  || { echo "merged/model.py is not the N1-fixed code"; exit 2; }

# ---------------------------------------------------------------- setup: new root, config, cache, base_root mirror
mkdir -p $O/logs $O/cache/runs $O/analysis/base $O/master $O/master_new $O/verify $O/check
for f in cost_mu haul materiale_use.csv outcrop_code.tif site_stone_sets.csv sites_haul.csv stones4 sea; do
  [ -e $O/cache/$f ] || ln -s "$(readlink -f $M/cache/$f)" $O/cache/$f
done
REGEN="scenarios fastest_scenarios.csv fastest_stage_decomposition.csv fastest_combined_effects.csv master_comparison.csv"
mkdir -p $BR/scenarios
for e in $(ls $B); do
  [[ " $REGEN " == *" $e "* ]] && continue
  [ -e $BR/$e ] || ln -s $B/$e $BR/$e
done
# DRY_LOW_LINK=1 (dry run of steps c d h k): base_root/scenarios/low -> the DELIVERED low, so every table must come
# out identical to its delivered version (checks the regeneration itself)
[ "${DRY_LOW_LINK:-0}" = 1 ] && [ ! -e $BR/scenarios/low ] && ln -s $B/scenarios/low $BR/scenarios/low
for n in $COOP; do [ $n = low ] && continue; [ -e $BR/scenarios/$n ] || ln -s $B/scenarios/$n $BR/scenarios/$n; done
# config = the base (RUN) config.yaml (7 coop scenarios, as the delivered base products) with cache/output -> new root
CFG=$O/config_1030b.yaml
sed -e "s|^  cache_dir: cache$|  cache_dir: $O/cache|" -e "s|^  output_dir: output$|  output_dir: $BR|" $R/config.yaml > $CFG
grep -q "cache_dir: $O/cache" $CFG && grep -q "output_dir: $BR\$" $CFG || { echo "config rewrite failed"; exit 2; }
CFGM=$O/config_1030b_merged.yaml                  # merged config (same coop parameters) for the verification runs
sed -e "s|^  cache_dir: cache$|  cache_dir: $O/cache|" -e "s|^  output_dir: output$|  output_dir: $O/verify|" $M/config.yaml > $CFGM
cd $M
LOG=$O/logs/rerun1030b.log
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
nolink() {   # refuse to write through a symlink into a delivered root
  for p in "$@"; do if [ -L "$p" ]; then echo "STOP: $p is a symlink (would overwrite a delivered file)" | tee -a $LOG; note "STOP ($p is a symlink)"; exit 4; fi; done; }
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
note "START (STEPS '$STEPS'; root $O; ETA ~17 min)"

# ---------------------------------------------------------------- g: low, 100 seeds, 8 ranks (as delivered: with shapefile)
if has g; then
  nolink $BR/scenarios/low
  step g_low $MPI 8 $PY model.py $CFG --scenario low --seeds 1-100
fi
# ---------------------------------------------------------------- v: mixed + mostly must be unchanged (proof run)
if has v; then
  for n in mixed mostly; do step v_$n $MPI 8 $PY model.py $CFGM --scenario $n --seeds 1-100 --no-shapefile --out $O/verify/$n; done
  step v_identity $PY -c "
import pandas as pd, sys
bad = 0
for n in ['mixed', 'mostly']:
    for f in ['nuraghe_manhours_runs.csv.gz', 'nuraghe_manhours_summary.csv']:
        a = pd.read_csv('$O/verify/%s/%s' % (n, f)); b = pd.read_csv('$B/scenarios/%s/%s' % (n, f))
        ok = list(a.columns) == list(b.columns) and len(a) == len(b) and all(a[c].equals(b[c]) for c in a.columns)
        print(n, f, len(a), 'rows: identical to the delivered run' if ok else 'rows: DIFFERENT'); bad += not ok
sys.exit(1 if bad else 0)"
fi
# ---------------------------------------------------------------- c: cooperation comparison + shapefile (7 scenarios)
if has c; then
  nolink $BR/scenarios/scenario_comparison.csv $BR/scenarios/nuraghe_manhours_scenarios.shp
  step c_compare $PY -c "
import sys; sys.path.insert(0, '$M')
import report; from nbcommon import load_config
report.compare_scenarios(load_config('$CFG'), '$COOP'.split())"
fi
# ---------------------------------------------------------------- d: fastest tables + master comparison (base products)
if has d; then
  nolink $BR/fastest_scenarios.csv $BR/fastest_stage_decomposition.csv $BR/fastest_combined_effects.csv $BR/master_comparison.csv
  step d_fastest $PY tools/fastest.py $CFG
  step d_master_comparison $PY tools/master_comparison.py $CFG
fi
# ---------------------------------------------------------------- h: post hoc phasing, workforce/years, master tables
if has h; then
  step h_phased_posthoc_base $PY tools/phased_posthoc.py --root $BR --out $O/analysis/base
  step h_workforce_years_base $PY tools/workforce_years.py --root $BR --out $O/analysis/base
  # replaces output_new/master (29 Oct night chain: --roots $R/output $ON)
  step h_master_table_new $PY tools/master_table.py --roots $BR $ON --caches $R/cache $ON/cache \
       --ratings $R/REALISM_RATINGS.md --out $O/master_new
  # replaces output_1030/master (rerun1030: --roots $R/output $ON $O30); MR rows from output_1030
  step h_master_table $PY tools/master_table.py --roots $BR $ON $O30 --caches $R/cache $ON/cache $O30/cache \
       --ratings $R/REALISM_RATINGS.md --out $O/master
fi
# ---------------------------------------------------------------- k: every regenerated table vs its delivered version
if has k; then
  step k_check $PY $M/tools/check1030b.py --out $O/check \
       $B/scenarios/scenario_comparison.csv:$BR/scenarios/scenario_comparison.csv:scenario \
       $B/fastest_scenarios.csv:$BR/fastest_scenarios.csv:code \
       $B/fastest_stage_decomposition.csv:$BR/fastest_stage_decomposition.csv:code \
       $B/fastest_combined_effects.csv:$BR/fastest_combined_effects.csv: \
       $B/master_comparison.csv:$BR/master_comparison.csv:code \
       $ON/analysis/base/phased_posthoc.csv:$O/analysis/base/phased_posthoc.csv:scenario \
       $ON/analysis/base/workforce_years.csv:$O/analysis/base/workforce_years.csv:scenario \
       $ON/master/master_table.csv:$O/master_new/master_table.csv:scenario \
       $O30/master/master_table.csv:$O/master/master_table.csv:scenario
  note "check: $(tail -1 $O/check/summary.txt)"
fi
echo "== $(date '+%F %T') rerun1030b done" | tee -a $LOG
note "DONE (outputs in output_1030b/; delivered results untouched)"
