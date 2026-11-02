#!/usr/bin/env bash
# BUGFIX item 11 proof (v12): kbest_quarries.py and haul_far.py, v11 code (unsnapped row/col) vs v12 code (snapped
# cell), on a 60-site subset cache (40 sites + 20 with TWR_N >= 3), under the lock. Outputs must be identical.
set -uo pipefail
W=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v12-census
V11=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-11-02-v11/code
PY=${PYTHON:-python3}
T=$W/outputs/test_item11; rm -rf $T; mkdir -p $T/logs
for v in v11 v12; do
  mkdir -p $T/$v/cache/haul $T/$v/cache/alliance
  for f in outcrop_code.tif site_stone_sets.csv cost_mu; do ln -s $W/outputs/cache/$f $T/$v/cache/$f; done
  $PY -c "
import pandas as pd; h=pd.read_csv('$W/outputs/cache/sites_haul.csv')
s=pd.concat([h.iloc[::180].head(40), h[h.TWR_N>=3].iloc[::40].head(20)]).drop_duplicates('UID').sort_index()
s.to_csv('$T/$v/cache/sites_haul.csv', index=False)"
  sed -e "s#cache_dir: .*#cache_dir: $T/$v/cache#" -e "s#output_dir: .*#output_dir: $T/$v#" $W/outputs/config_v12.yaml > $T/$v/config.yaml
done
export PYTHONDONTWRITEBYTECODE=1
for v in v11 v12; do
  C=$V11; [ $v = v12 ] && C=$W/code
  for tool in kbest_quarries haul_far; do
    (cd $C && flock /tmp/nuraghe_dev.lock $PY $W/code/memrun.py $T/logs/${v}_$tool.mem -- $PY tools/$tool.py $T/$v/config.yaml > $T/logs/${v}_$tool.log 2>&1)
    echo "$v $tool exit $? $(tail -1 $T/logs/${v}_$tool.mem)"
  done
done
$PY - <<PYEOF
import numpy as np, filecmp
a = np.load("$T/v11/cache/alliance/kbest.npz"); b = np.load("$T/v12/cache/alliance/kbest.npz")
ok = sorted(a.files) == sorted(b.files) and all(np.array_equal(a[k], b[k]) for k in a.files)
c = filecmp.cmp("$T/v11/cache/haul/sites_haul_complexfar.csv", "$T/v12/cache/haul/sites_haul_complexfar.csv", shallow=False)
msg = f"kbest.npz arrays identical: {ok} ({len(a.files)} arrays); sites_haul_complexfar.csv byte-identical: {c}"
# unit check of snapped_cell on a fabricated snapped site
import sys; sys.path.insert(0, "$W/code"); from nbcommon import snapped_cell
v = np.zeros((50, 50), bool); v[10, 13] = True; v[13, 10] = True; v[20, 20] = True
r = snapped_cell({"row": 10, "col": 10, "snap_status": "snapped_nodata", "snap_dist_m": 90.0}, lambda ra, rb, ca, cb: v[ra:rb, ca:cb], 20, 50, 50, 30.0)
r0 = snapped_cell({"row": 10, "col": 10, "snap_status": "ok", "snap_dist_m": 0.0}, None, 20, 50, 50, 30.0)
msg += f"; unit: snapped site -> {r} (expected (10, 13), first in row order), ok site -> {r0}"
verdict = "ITEM 11 PASS" if ok and c and r == (10, 13) and r0 == (10, 10) else "ITEM 11 FAIL"
open("$T/ITEM11.txt", "w").write(msg + "\n" + verdict + "\n"); print(msg); print(verdict)
PYEOF
