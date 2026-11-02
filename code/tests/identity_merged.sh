#!/usr/bin/env bash
# Identity of the MERGED code (features off = RUN; each feature on alone = its dev copy), on the dev copies' own
# subset inputs and invocations, seeds 1-3. Reference outputs already on disk (never rewritten):
#   RUN    : dev_sea/subset/orig (byte copy of RUN code; sea subset 300) and dev_real/subset/run (RUN code; real subset 300)
#   S9     : dev_sea/subset/dev       P10: dev_phase/scratch/phase_subset (302 sites, 2 ranks)    REAL: dev_real/subset/dev
# Every run under the shared lock, with memrun (time + memory) and the oom_kill counter.
set -uo pipefail
R=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix
M=$R/merged
PY=${PYTHON:-python3}
O=$M/subset/ident; rm -rf $O; mkdir -p $O/logs
SEA=$(cat $M/sites300_sea.txt); REAL=$(cat $M/sites300_real.txt); PH=$(cat $M/sites302.txt)
MPI1="mpirun --allow-run-as-root --oversubscribe -n 1"; MPI2="mpirun --allow-run-as-root --oversubscribe -n 2"
export PYTHONDONTWRITEBYTECODE=1
cd $M
oomk() { awk '/oom_kill /{print $2}' /sys/fs/cgroup/memory.events; }
step() { n=$1; shift; k0=$(oomk); flock /tmp/nuraghe_dev.lock $PY $M/memrun.py $O/logs/$n.log -- "$@" > $O/logs/$n.out 2>&1
         echo "== $n: $(grep memrun $O/logs/$n.log | tail -1 | cut -c1-60)"; [ "$(oomk)" = "$k0" ] || { echo "oom_kill rose"; exit 9; }; }
A="--seeds 1-3 --no-shapefile"
# --- features off vs RUN (sea subset): baseline, full, high, A1_ask + A5_full, P_G50_hub
step baseline $MPI1 $PY model.py config.yaml --sites $SEA $A --out $O/sea/baseline --parts-dir $O/sea/parts
step full     $MPI1 $PY model.py config.yaml --sites $SEA $A --scenario full --out $O/sea/full --parts-dir $O/sea/parts
step high     $MPI1 $PY model.py config.yaml --sites $SEA $A --scenario high --out $O/sea/high --parts-dir $O/sea/parts
step A1A5     $MPI1 $PY model.py config.yaml --sites $SEA $A --alliance A1_ask,A5_full --out $O/sea/alliance --parts-dir $O/sea/parts
step pre      $MPI1 $PY model.py config.yaml --sites $SEA $A --pre P_G50_hub --out $O/sea/pre --parts-dir $O/sea/parts
# --- S9 on (sea subset)
step S9_5kn   $MPI1 $PY model.py config.yaml --sites $SEA $A --scenario S9_sea_5kn --out $O/sea/S9_sea_5kn --parts-dir $O/sea/parts
step high_sea $MPI1 $PY model.py config.yaml --sites $SEA $A --scenario high_sea --out $O/sea/high_sea --parts-dir $O/sea/parts
step A_sea    $MPI1 $PY model.py config.yaml --sites $SEA $A --alliance A1_ask_sea,A5_full_sea --out $O/sea/alliance_sea --parts-dir $O/sea/parts
step pre_sea  $MPI1 $PY model.py config.yaml --sites $SEA $A --pre P_G50_hub_sea --out $O/sea/pre_sea --parts-dir $O/sea/parts
# --- features off vs RUN (real subset): webster, LOW; REALISTIC on
for n in webster LOW REALISTIC REALISTIC_oxen; do
  step lit_$n $MPI1 $PY model.py config.yaml --sites $REAL $A --lit $n --out $O/real/$n --parts-dir $O/real/parts
done
# --- phasing on (302 sites, 2 ranks, as dev_phase)
for n in full_P10 high_P10; do
  step $n $MPI2 $PY model.py config.yaml --scenario $n --sites $PH $A --parts-dir $O/ph/parts --out $O/ph/out/$n
done
step A5_P10 $MPI2 $PY model.py config.yaml --alliance A5_full_P10 --sites $PH $A --no-merge --parts-dir $O/ph/parts

# --- compare (bytes; .gz also compared decompressed if the bytes differ)
same() {  # same LABEL DIR_NEW DIR_REF
  local bad=0 n=0
  while IFS= read -r f; do
    n=$((n + 1)); g=$3/${f#$2/}
    if [ ! -e "$g" ]; then echo "  missing in ref: ${f#$2/}"; bad=$((bad + 1)); continue; fi
    cmp -s "$f" "$g" && continue
    if [[ $f == *.gz ]] && cmp -s <(zcat "$f") <(zcat "$g"); then echo "  gz-content-equal: ${f#$2/}"; continue; fi
    echo "  DIFF: ${f#$2/}"; bad=$((bad + 1))
  done < <(find "$2" -type f ! -name '*.log' | sort)
  echo "$1: $n files, $bad differ -> $([ $bad = 0 ] && echo PASS || echo FAIL)"
}
S=$R/dev_sea/subset; P=$R/dev_phase/scratch/phase_subset; L=$R/dev_real/subset
for x in baseline full high pre; do same "RUN $x" $O/sea/$x $S/orig/$x; done
same "RUN A1_ask" $O/sea/alliance/A1_ask $S/orig/alliance/A1_ask
same "RUN A5_full" $O/sea/alliance/A5_full $S/orig/alliance/A5_full
for t in $(ls $S/orig/parts); do
  [ -d $O/sea/parts/$t ] && same "RUN parts $t" $O/sea/parts/$t $S/orig/parts/$t
done
same "RUN webster" $O/real/webster $L/run/webster
same "RUN LOW" $O/real/LOW $L/run/LOW
same "S9 S9_sea_5kn" $O/sea/S9_sea_5kn $S/dev/S9_sea_5kn
same "S9 high_sea" $O/sea/high_sea $S/dev/high_sea
same "S9 A1_ask_sea" $O/sea/alliance_sea/A1_ask_sea $S/dev/alliance/A1_ask_sea
same "S9 A5_full_sea" $O/sea/alliance_sea/A5_full_sea $S/dev/alliance/A5_full_sea
same "S9 P_G50_hub_sea" $O/sea/pre_sea/P_G50_hub_sea $S/dev/pre/P_G50_hub_sea
same "REAL REALISTIC" $O/real/REALISTIC $L/dev/REALISTIC
same "REAL REALISTIC_oxen" $O/real/REALISTIC_oxen $L/dev/REALISTIC_oxen
same "P10 full_P10" $O/ph/out/full_P10 $P/out/full_P10
same "P10 high_P10" $O/ph/out/high_P10 $P/out/high_P10
same "P10 A5_full_P10 parts" $O/ph/parts/alliance_A5_full_P10 $P/parts/alliance_A5_full_P10
for t in lit_webster lit_LOW; do same "RUN parts $t" $O/real/parts/$t $L/run_parts/$t; done
for t in lit_REALISTIC lit_REALISTIC_oxen; do same "REAL parts $t" $O/real/parts/$t $L/dev_parts/$t; done
for t in S9_sea_5kn high_sea alliance_A1_ask_sea alliance_A5_full_sea alliance_P_G50_hub_sea; do
  [ -d $O/sea/parts/$t ] && same "S9 parts $t" $O/sea/parts/$t $S/dev/parts/$t
done
for t in full_P10 high_P10; do [ -d $O/ph/parts/$t ] && same "P10 parts $t" $O/ph/parts/$t $P/parts/$t; done
