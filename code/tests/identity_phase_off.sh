#!/usr/bin/env bash
# Phasing OFF must change nothing: run the RUN (bug-fixed) code and the DEV code on the same inputs (DEV/config.yaml,
# DEV/cache -> RUN/cache), 302-site subset, seeds 1-3, 2 ranks, and compare every per-seed part file byte for byte
# (alliance .csv.gz compared decompressed). Also checks that the run-signature hash directories are the same.
#   bash tests/identity_phase_off.sh
set -uo pipefail
RUN=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix
DEV=$RUN/dev_phase
PY=${PYTHON:-python3}
CFG=$DEV/config.yaml
S=$(cat $DEV/sites302.txt)
MPI="mpirun --allow-run-as-root --oversubscribe -n 2"
W=$DEV/scratch/identity
rm -rf $W; mkdir -p $W
for who in run dev; do
  CODE=$([ $who = run ] && echo $RUN || echo $DEV)
  P=$W/parts_$who; O=$W/out_$who
  cd $CODE
  echo "== $(date +%T) $who code: $CODE"
  flock /tmp/nuraghe_dev.lock $PY $DEV/memrun.py $W/$who.log -- bash -c "
    $MPI $PY $CODE/model.py $CFG --sites $S --seeds 1-3 --no-shapefile --parts-dir $P --out $O/baseline &&
    $MPI $PY $CODE/model.py $CFG --scenario all --sites $S --seeds 1-3 --no-shapefile --parts-dir $P --out $O/coop &&
    $MPI $PY $CODE/model.py $CFG --lit webster,S3e_oxen,LOW,HIGH --sites $S --seeds 1-3 --no-shapefile --parts-dir $P --out $O/lit &&
    $MPI $PY $CODE/model.py $CFG --alliance A0_alone,A2_trust,A5_full --sites $S --seeds 1-3 --no-merge --parts-dir $P &&
    $MPI $PY $CODE/model.py $CFG --pre P_G20_system_kmesh4,P_D8_G20_kmesh4_tieloss --sites $S --seeds 1-3 --no-merge --parts-dir $P"
  tail -1 $W/$who.log
done
echo "== compare"
$PY - <<EOF
import glob, gzip, os
W = "$W"
def files(root):
    return sorted(os.path.relpath(f, root) for f in glob.glob(os.path.join(root, "**", "*"), recursive=True)
                  if os.path.isfile(f) and (f.endswith(".csv") or f.endswith(".csv.gz")))
def body(p):
    return gzip.open(p).read() if p.endswith(".gz") else open(p, "rb").read()
ok = True
for kind in ("parts", "out"):
    a, b = os.path.join(W, kind + "_run"), os.path.join(W, kind + "_dev")
    fa, fb = files(a), files(b)
    same_names = fa == fb
    diff = [f for f in fa if f in fb and body(os.path.join(a, f)) != body(os.path.join(b, f))]
    print(f"{kind}: {len(fa)} files (run) vs {len(fb)} (dev); same file names/hash dirs: {same_names}; differing: {len(diff)}")
    ok = ok and same_names and not diff and len(fa) > 0
    for f in diff[:10]:
        print("   DIFF", f)
print("IDENTITY:", "PASS" if ok else "FAIL")
EOF
