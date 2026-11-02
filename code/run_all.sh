#!/usr/bin/env bash
# One command for everything: ./run_all.sh [N_RANKS] [PYTHON]
# Steps (each is skipped/resumed safely if already done):
#   1 preprocess (baseline haul)     2 cost rasters per friction mu     3 haul tables for the literature scenarios
#   4 baseline 100 runs              5 cooperation scenarios            6 literature scenarios          7 verification
#   8 adaptive alliance scenarios (k-best quarry routes, 7 scenarios x 100 seeds, A0 check, sensitivity, verification),
#     cooperation networks, savings decomposition, scenario key, fastest-scenario analysis, report
# Set STEPS="1 2 3" (etc.) to run only some steps.
set -euo pipefail
cd "$(dirname "$0")"
N=${1:-4}
PY=${2:-python}
CFG=config.yaml
STEPS=${STEPS:-"1 2 3 4 5 6 7 8"}
MPI="mpirun -n $N"
[ "$(id -u)" = "0" ] && MPI="mpirun --allow-run-as-root --oversubscribe -n $N"
export MPIRUN="${MPI% -n *}"          # the tests' own mpirun calls (verify_scenarios, verify_lit, reproducibility, alliance)
has() { [[ " $STEPS " == *" $1 "* ]]; }
mkdir -p cache/cost_mu

if has 1; then echo "== 1 preprocess"; $PY preprocess.py $CFG; fi
if has 2; then
  echo "== 2 cost rasters per mu"
  $PY tools/build_cost_mu.py $CFG 0.3 --check
  for mu in 0.1 0.05 0.38 0.5; do
    f=cache/cost_mu/drag_cost_8dir_mu${mu}_int.tif
    [ -s "$f" ] || $PY tools/build_cost_mu.py $CFG $mu "$f"
  done
fi
if has 3; then
  echo "== 3 haul tables"
  for mu in 0.1 0.05 0.38 0.5; do
    $PY preprocess.py $CFG --tag mu$mu --cost-raster cache/cost_mu/drag_cost_8dir_mu${mu}_int.tif
  done
  $PY preprocess.py $CFG --tag buildstone --stones BUILDSTONE
  $PY preprocess.py $CFG --tag buildstone_mu0.1 --stones BUILDSTONE --cost-raster cache/cost_mu/drag_cost_8dir_mu0.1_int.tif
  $PY tools/haul_far.py $CFG
fi
if has 4; then echo "== 4 baseline";               $MPI $PY model.py $CFG; fi
if has 5; then echo "== 5 cooperation scenarios";  $MPI $PY model.py $CFG --scenario all; fi
if has 6; then echo "== 6 literature scenarios";   $MPI $PY model.py $CFG --lit all; fi
if has 7; then
  echo "== 7 verification"
  $PY tests/test_dijkstra.py
  $PY tests/verify_hauls.py $CFG
  $PY tests/verify_webster.py $CFG
  $PY tests/verify_scenarios.py $CFG
  $PY tests/verify_lit.py $CFG
  $PY tests/test_reproducibility.py $CFG
fi
if has 8; then
  echo "== 8 alliance scenarios"
  [ -s cache/alliance/kbest.npz ] || $PY tools/kbest_quarries.py $CFG
  $MPI $PY model.py $CFG --alliance all
  $MPI $PY model.py $CFG --alliance A0_verify
  $MPI $PY model.py $CFG --alliance sensitivity
  $PY tests/verify_alliance.py $CFG
  $PY tests/verify_alliance_identity.py $CFG              # vs a saved reference (ALLIANCE_REF); SKIPPED if none
  # pre-existing networks (P_none + main grid + extras), in 4 interleaved batches as in the delivered run (8 GB cap)
  PRE=$($PY -c "import sys; sys.path.insert(0, '.'); import pre_networks; from nbcommon import load_config; print(' '.join(pre_networks.expand(load_config('$CFG'))))")
  for b in 0 1 2 3; do
    L=$(echo $PRE | tr ' ' '\n' | awk -v b=$b '(NR - 1) % 4 == b' | paste -sd,)
    $MPI $PY model.py $CFG --pre "$L"
  done
  $PY tests/verify_pre.py $CFG
  $PY tools/alliance_emergence.py $CFG > cache/logs/alliance_emergence.log
  $PY tools/alliance_networks.py $CFG --jobs 4            # cooperation networks by layer (stone, transport, build, all)
  $PY tools/alliance_savings.py $CFG                      # savings by stage, time, pairwise matrix
  $PY tools/scenario_guide.py $CFG                        # scenario key (Appendix A)
  $PY tools/fastest.py $CFG                               # which scenarios build fastest, and why
  $PY tools/census.py $CFG --seeds 1-100                  # relationship census (a Nurnet collaborator's classes)
  $PY tools/formation.py $CFG                             # network formation over seasons
  $PY tools/components.py $CFG                            # connected help networks
  $PY tools/alliance_networks.py $CFG --pre --jobs 4      # pre-existing networks: networks, components, analysis
  $PY tools/components.py $CFG --pre
  $PY tools/pre_analysis.py $CFG
  $PY tools/master_comparison.py $CFG                     # all scenarios on one baseline
  $PY report/make_report.py                               # rebuild the PDF report
fi
echo "done"
