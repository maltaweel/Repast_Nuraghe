#!/usr/bin/env bash
# Night chain, 29-30 Oct 2026 (CPU, 100 seeds): every new scenario from the MERGED code, outputs to RUN/output_new/.
# NOT launched by the merge session. Start:  nohup bash merged/night_chain.sh > RUN/output_new_chain.out 2>&1 &
# Run it AFTER the base rerun chain (RUN/cache/logs/base_rerun_chain.log) has finished: both need the 8 GB cgroup.
#
# Every step: START/END line with wall time, memory (memrun.py: peak tree RSS / PSS, cgroup peak) and the cgroup
# oom_kill counter; the chain STOPS if oom_kill rises. Every simulation runs under `flock /tmp/nuraghe_dev.lock`.
# Steps are resumable: model.py / alliance.py skip seeds already on disk (part files in output_new/cache/runs).
# STEPS="g a b" (etc.) runs only those steps. Order: MOST_REALISTIC first (the headline run, specified by the authors).
#
# Wall-time estimate (min), updated 15:20. Sources: today's base rerun (RUN/cache/logs/base_rerun_chain_resume.log,
# 6 ranks: pre-network batches 2,692-2,885 s per 14 scenarios = ~200 s per scenario incl. merge; alliance_networks
# 56 s per scenario; alliance_all 1,154 s for 8 = 144 s each), REF cache/logs (lit 131-179 s / 100 seeds on 8 ranks,
# coop 125-132 s, high 542 s on 2 ranks, sensitivity 10 min on 8 ranks), the full-island 1-seed 1-rank timings in
# merged/subset/timing (handover: MR_P10 15.3 s/seed, MR_P20 20.8, MR_P100 71.3, MR_alone_P10 6.3, A5_full_P10 14.6,
# P_G50_hub_P10 5.2) and the measured 100-seed MR_P10 (handover) on 6 ranks: 307 s. 100 seeds on 6 ranks = 17 seeds
# per rank x 1.2 (contention) + ~60 s merge. JOIN: per-seed cost taken = handover (300-site subset walls equal:
# 5.1-5.2 s vs 5.2-5.7 s per 3 seeds); a full-island join timing was not allowed under the subset-only rule.
#   g  MR join P10/P20/P100 (~5 + 8 + 25), handover P10 (rescued: merge only, ~1) / P20 (~8) / P100 (~25),
#      alone P10/P20/P100 (~3 + 4 + 11) ......................................................  ~91
#   r  Morris MR_P10 join: 60 runs x 1 seed, 6 parallel x ~30 s ...............................   ~6
#   a  lit REALISTIC, REALISTIC_oxen (8 ranks) ................................................   ~6
#   b  S9_sea_2kn/4kn/5kn/6kn (8 ranks) .........................................................  ~10
#   c  high_sea (2 ranks, coupled) ..............................................................  ~10
#   d  A1..A5 + A5_full_freerider _sea (6 ranks) ................................................  ~16
#   e  5 named pre-networks _sea, 100 seeds (~200 s each) ~17; 56-cell grid _sea at 10 seeds ~34 ..  ~51
#   f1 high_P10/_P20 (2 ranks) ~20; A1..A5 + freerider _P10 (~6 each) / _P20 (~8 each) ~83 .........  ~103
#   s  alliance sensitivity, 27 cells x 10 seeds (RUN code + config -> RUN/output) ..............  ~13
#   h  workforce_years + phased_posthoc (~8), centrality 2 layers for ~35 non-grid network scenarios
#      (~30 s each, ~18), MR networks/formation/components/figures (~14), network need, master table (~7)  ~50
#   f2 pre-network grid _P10 / _P20, 56 x 2 runs (~146 / ~184 s): 100 seeds ~308; 10 seeds ~65
#   h2 centrality of the grids (base 56 + _sea 56 + phased 112, ~25 s each, ~93) + refresh (~20) ......  ~115
#   m  RUN pre_analysis then master_comparison (pre rows included) ..............................   ~3
# TOTAL ~13.0 h with f2 at 100 seeds; ~9.0 h with PH_GRID_SEEDS=1-10 (proposed). Dropping h2's phased-grid
# centrality saves ~50 min more. MOST_REALISTIC (g) is done after ~1.5 h.
set -uo pipefail
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix
M=$R/merged
ON=$R/output_new
PY=${PYTHON:-python3}
STEPS=${STEPS-"g r a b c d e f1 s h f2 h2 m"}          # unset -> all; STEPS="" -> nothing (":-" would run ALL, see 11:37 incident)
PH_GRID_SEEDS=${PH_GRID_SEEDS:-1-100}           # f2: set 1-10 if the night is too short (~70 min instead of ~4.8 h)
SEEDS=1-100
MPI="mpirun --allow-run-as-root --oversubscribe -n"
export PYTHONDONTWRITEBYTECODE=1
has() { [[ " $STEPS " == *" $1 "* ]]; }
[ -z "${STEPS// }" ] && { echo "STEPS empty: nothing to do"; exit 0; }
# never share the 8 GB cgroup with another simulation (29 Oct 11:37: a concurrent 6-rank run OOM-killed the base chain)
if pgrep -f "model.py .*config" >/dev/null; then echo "another model.py is running: start the night chain alone"; exit 3; fi

# ---------------------------------------------------------------- setup: new output folder + its config and cache
mkdir -p $ON/logs $ON/cache/runs $ON/cache/alliance
for f in cost_mu haul materiale_use.csv outcrop_code.tif site_stone_sets.csv sites_haul.csv stones4 sea; do
  [ -e $ON/cache/$f ] || ln -s "$(readlink -f $M/cache/$f)" $ON/cache/$f
done
for f in kbest.npz kbest_mu038.npz; do
  [ -e $ON/cache/alliance/$f ] || ln -s "$(readlink -f $M/cache/alliance/$f)" $ON/cache/alliance/$f
done
CFG=$ON/config_night.yaml                       # = merged/config.yaml with cache_dir / output_dir -> output_new
sed -e "s|^  cache_dir: cache$|  cache_dir: $ON/cache|" -e "s|^  output_dir: output$|  output_dir: $ON|" $M/config.yaml > $CFG
grep -q "cache_dir: $ON/cache" $CFG && grep -q "output_dir: $ON\$" $CFG || { echo "config rewrite failed"; exit 2; }
cd $M
LOG=$ON/logs/night_chain.log
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
step() {   # step NAME CMD... : under the lock, timed, memory-logged; stop on oom_kill increase or failure
  local n=$1; shift; local k0; k0=$(oomk)
  echo "== $(date '+%F %T') START $n (oom_kill $k0)" | tee -a $LOG
  flock /tmp/nuraghe_dev.lock $PY $M/memrun.py $ON/logs/$n.mem -- "$@" > $ON/logs/$n.log 2>&1
  local rc=$? k1; k1=$(oomk)
  echo "== $(date '+%F %T') END $n exit $rc (oom_kill $k0 -> $k1) $(tail -1 $ON/logs/$n.mem)" | tee -a $LOG
  if [ "$k1" != "$k0" ]; then echo "STOP: oom_kill rose during $n" | tee -a $LOG; exit 9; fi
  if [ $rc != 0 ]; then echo "STOP: $n failed (exit $rc)" | tee -a $LOG; exit $rc; fi
}
A="--seeds $SEEDS --no-shapefile"               # shapefiles: alliance_networks / centrality write their own
GRID=$($PY -c "import sys; sys.path.insert(0, '$M'); import pre_networks; from nbcommon import load_config; print(' '.join(pre_networks.expand(load_config('$CFG'))))")
sfx() { local s=$1; shift; echo "$@" | tr ' ' '\n' | sed "s/\$/$s/" | paste -sd,; }
batch() { local b=$1; shift; echo "$@" | tr ' ' '\n' | awk -v b=$b '(NR - 1) % 4 == b' | paste -sd' '; }
ASC="A1_ask A2_trust A3_trust_learning A4_trust_track A5_full A5_full_freerider"
PSEA="P_none P_G50_hub P_G20_system_hub P_G133_tribe_complete P_G20_kmesh4_track"
MR="MOST_REALISTIC_P10 MOST_REALISTIC_P20 MOST_REALISTIC_P100"                         # help_mode join (specified by the authors)
MRH="MOST_REALISTIC_handover_P10 MOST_REALISTIC_handover_P20 MOST_REALISTIC_handover_P100"   # the 11:30 behaviour
MRA="MOST_REALISTIC_alone_P10 MOST_REALISTIC_alone_P20 MOST_REALISTIC_alone_P100"

# ---------------------------------------------------------------- g: MOST_REALISTIC (headline) + A0-equivalents
if has g; then
  # the rescued 11:37 100-seed handover P10 (merged/subset/nc_rescue, renamed to its signature): only re-merged here
  RS=$M/subset/nc_rescue/runs/alliance_MOST_REALISTIC_handover_P10
  [ -d $RS ] && [ ! -e $ON/cache/runs/alliance_MOST_REALISTIC_handover_P10 ] && cp -al $RS $ON/cache/runs/
  for n in $MR $MRH $MRA; do step g_$n $MPI 6 $PY model.py $CFG $A --alliance $n; done
fi
# ---------------------------------------------------------------- r: Morris screen of MOST_REALISTIC_P10 (join), specified by the authors
# 5 factors (other_mandays_per_tower: not used by the alliance model, skipped), r = 10 -> 60 runs x 1 seed, 6 at a time
# (1 rank each, ~0.9 GB). RANGES in tools/morris_mr.py are PLACEHOLDERS until a Nurnet collaborator's stage-2 ranges are copied in.
if has r; then
  MO=$ON/morris_most_realistic_P10
  step r_morris_design $PY tools/morris_mr.py design --cfg $CFG --out $MO --r 10 --seed 2026
  step r_morris_runs bash -c "xargs -P 6 -I CMD bash -c 'CMD > /dev/null 2>&1 || echo FAILED: CMD' < $MO/commands.txt | tee $MO/failed.txt; [ ! -s $MO/failed.txt ]"
  step r_morris_analyse $PY tools/morris_mr.py analyse --out $MO
fi
# ---------------------------------------------------------------- a: literature REALISTIC
if has a; then step a_lit_realistic $MPI 8 $PY model.py $CFG $A --lit REALISTIC
               step a_lit_realistic_oxen $MPI 8 $PY model.py $CFG $A --lit REALISTIC_oxen; fi
# ---------------------------------------------------------------- b: S9 sea speeds (stand-alone, independent sites)
if has b; then for n in S9_sea_2kn S9_sea_4kn S9_sea_5kn S9_sea_6kn; do step b_$n $MPI 8 $PY model.py $CFG $A --scenario $n; done; fi
# ---------------------------------------------------------------- c: high with sea (coupled: 2 ranks)
if has c; then step c_high_sea $MPI 2 $PY model.py $CFG $A --scenario high_sea; fi
# ---------------------------------------------------------------- d: alliance A1..A5 + freerider, sea 5 kn
if has d; then step d_alliance_sea $MPI 6 $PY model.py $CFG $A --alliance "$(sfx _sea $ASC)"; fi
# ---------------------------------------------------------------- e: pre-networks with sea
if has e; then
  step e_pre_sea $MPI 6 $PY model.py $CFG $A --pre "$(sfx _sea $PSEA)"
  for b in 0 1 2 3; do                          # 4 interleaved batches, as run_all.sh step 8 (8 GB cap)
    step e_pre_grid10_sea_b$b $MPI 6 $PY model.py $CFG --seeds 1-10 --no-shapefile --pre "$(sfx _sea $(batch $b $GRID))" \
         --out $ON/scenarios_pre_grid10_sea
  done
fi
# ---------------------------------------------------------------- f1: simulated phasing, high + alliance
if has f1; then
  for p in _P10 _P20; do step f1_high$p $MPI 2 $PY model.py $CFG $A --scenario high$p; done
  for p in _P10 _P20; do step f1_alliance$p $MPI 6 $PY model.py $CFG $A --alliance "$(sfx $p $ASC)"; done
fi
# ---------------------------------------------------------------- h: post hoc analyses
is_grid() {   # names (stdin) -> those that belong to the 56-cell grid families (base grid, grid _sea, grid _P10/_P20)
  local G="$(echo $GRID | tr ' ' '\n' | grep -v -x -E "$(echo $PSEA | tr ' ' '|')")"
  grep -x -E "($(echo $G | tr ' ' '|'))(_sea|_P10|_P20)?"
}
post() {   # post TAG : analyses (TAG 2 = after f2: the grids' centrality + table refresh)
  local t=$1
  step h${t}_workforce_years_new $PY tools/workforce_years.py --root $ON --out $ON/analysis
  step h${t}_workforce_years_base $PY tools/workforce_years.py --root $R/output --out $ON/analysis/base
  step h${t}_phased_posthoc_new $PY tools/phased_posthoc.py --root $ON --out $ON/analysis
  step h${t}_phased_posthoc_base $PY tools/phased_posthoc.py --root $R/output --out $ON/analysis/base
  # centrality, cooperation (help MH) + communication (requests accepted + refused) layers: maps, top-20 (UID, name,
  # comune), score shapefiles. h: every network scenario except the 56-cell grids; h2: the grids (base, _sea at 10
  # seeds, _P10/_P20), --k 200 betweenness sources to keep it ~25 s per scenario.
  local NEW BASE
  NEW=$(cd $ON/cache/runs && ls -d alliance_* 2>/dev/null | sed 's/^alliance_//' | grep -v -E '_alone(_P[0-9]+)?$|^A0_|^SENS_')
  BASE=$(cd $R/cache/runs 2>/dev/null && ls -d alliance_* | sed 's/^alliance_//' | grep -v -E '^A0_|^SENS_')
  mkdir -p $ON/grid10_root; [ -e $ON/grid10_root/scenarios_pre ] || ln -s $ON/scenarios_pre_grid10_sea $ON/grid10_root/scenarios_pre
  if [ -z "$t" ]; then
    local N1 B1
    N1=$(echo "$NEW" | grep -v -x -F "$(echo "$NEW" | is_grid)" | grep -v '_alone_' | paste -sd' ')   # 19:40: _alone_ twins have no help network (empty layer -> ARPACK error); excluded from centrality by design
    B1=$(echo "$BASE" | grep -v -x -F "$(echo "$BASE" | is_grid)" | paste -sd' ')
    step h_centrality_new $PY tools/centrality.py $N1 --cache $ON/cache --out-root $ON --out $ON/centrality
    [ -n "$B1" ] && step h_centrality_base $PY tools/centrality.py $B1 --cache $R/cache --out-root $R/output --out $ON/centrality_base
  else
    local GS GP GB
    GS=$(echo "$NEW" | is_grid | grep '_sea$' | paste -sd' ')
    GP=$(echo "$NEW" | is_grid | grep -E '_P(10|20)$' | paste -sd' ')
    GB=$(echo "$BASE" | is_grid | paste -sd' ')
    [ -n "$GB" ] && step h2_centrality_grid_base $PY tools/centrality.py $GB --k 200 --cache $R/cache --out-root $R/output --out $ON/centrality_base
    [ -n "$GS" ] && step h2_centrality_grid_sea $PY tools/centrality.py $GS --k 200 --cache $ON/cache --out-root $ON/grid10_root --out $ON/centrality
    [ -n "$GP" ] && step h2_centrality_grid_phased $PY tools/centrality.py $GP --k 200 --cache $ON/cache --out-root $ON --out $ON/centrality
  fi
  # MOST_REALISTIC networks (specified by the authors): layer networks + shapefiles, formation over seasons, components, figures
  if [ -z "$t" ]; then
    step h_mr_networks $PY tools/alliance_networks.py $CFG $MR $MRH --jobs 2
    step h_mr_formation $PY tools/formation.py $CFG --names "$(echo $MR $MRH | tr ' ' ,)" --out-sub formation_most_realistic
    step h_mr_components $PY tools/components.py $CFG --names "$(echo $MR $MRH | tr ' ' ,)" --out-sub formation_most_realistic \
         --cuts 50,100,200,400,end
    step h_mr_formation_plot $PY tools/formation_plot.py $ON/formation_most_realistic
    # network need per tower class (specified by the authors): MR join and handover vs the A0-equivalent; A3 vs A0 (base rerun)
    step h_network_need $PY tools/network_need.py --root $R/output/scenarios_alliance $ON/scenarios_alliance \
         --out $ON/network_need --pairs MOST_REALISTIC_P10:MOST_REALISTIC_alone_P10 MOST_REALISTIC_P20:MOST_REALISTIC_alone_P20 \
         MOST_REALISTIC_P100:MOST_REALISTIC_alone_P100 MOST_REALISTIC_handover_P10:MOST_REALISTIC_alone_P10 \
         MOST_REALISTIC_handover_P20:MOST_REALISTIC_alone_P20 MOST_REALISTIC_handover_P100:MOST_REALISTIC_alone_P100 \
         A3_trust_learning:A0_alone
  fi
  # master table: every scenario a row (base rerun + new), realism from RUN/REALISM_RATINGS.md
  step h${t}_master_table $PY tools/master_table.py --roots $R/output $ON --caches $R/cache $ON/cache \
       --ratings $R/REALISM_RATINGS.md --out $ON/master
}
# ---------------------------------------------------------------- s: alliance sensitivity grid (B1 made the old one stale)
# Base product (A5_full cells, features off = RUN code identical): RUN code + RUN config -> RUN/output/scenarios_alliance/
# sensitivity, 10 seeds as REF cache/logs/alliance_sensitivity_run.log (27 cells, 10 min on 8 ranks; here 6).
if has s; then (cd $R && step s_alliance_sensitivity $MPI 6 $PY model.py config.yaml --alliance sensitivity) || exit $?; fi
if has h; then post ""; fi
# ---------------------------------------------------------------- f2: simulated phasing of the pre-network grid
if has f2; then
  for p in _P10 _P20; do for b in 0 1 2 3; do
    step f2_pre_grid${p}_b$b $MPI 6 $PY model.py $CFG --seeds $PH_GRID_SEEDS --no-shapefile --pre "$(sfx $p $(batch $b $GRID))"
  done; done
fi
if has h2; then post 2; fi
# ---------------------------------------------------------------- m: base master comparison AFTER pre_analysis
# (the base chain ran tools/master_comparison.py before pre_analysis, so its pre-network rows were missing)
if has m; then
  (cd $R && step m_pre_analysis $PY tools/pre_analysis.py config.yaml && step m_master_comparison $PY tools/master_comparison.py config.yaml) || exit $?
fi
echo "== $(date '+%F %T') night chain done" | tee -a $LOG
