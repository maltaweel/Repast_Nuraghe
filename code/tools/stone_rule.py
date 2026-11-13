"""Stone rule comparison: stones4 (the authors' original 4 classes) vs stones7 (7 classes) vs hybrid (recorded stone first).

  python tools/stone_rule.py config.yaml

Recorded stone: Nurnet's data (site building stone), `stone_material` (aggregate statistics only in outputs).
Writes to output/:
  stone_rule_hauls.csv        per rule: mean / median haul (flat-m and m), sites on an own-rule outcrop, quarry stone counts
  stone_rule_validation.csv   single-stone sites (9 classes): share whose model quarry stone matches the recorded stone
  stone_rule_use.csv          hybrid: sites using their recorded stone vs falling back, by recorded value (counts only)
  stone_rule_comparison.csv   island man-hours per family and scenario, stones4 vs hybrid (+ stones7 baseline)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
OUT = cfg["paths"]["output_dir"]; C = cfg["paths"]["cache_dir"]
H = {"stones4": pd.read_csv(os.path.join(C, "stones4", "sites_haul.csv")),
     "stones7": pd.read_csv(os.path.join(C, "haul", "sites_haul_stones7.csv")),
     "hybrid": pd.read_csv(os.path.join(C, "sites_haul.csv"))}
M = cfg["materiale"]
mat = pd.read_csv(M["file"] if os.path.isabs(M["file"]) else os.path.join(cfg["data_dir"], M["file"])).rename(columns={"codice": "UID"})
rows = []
for r, h in H.items():
    vc = h.quarry_stone.value_counts()
    rows.append({"rule": r, "haul_flatm_mean": h.haul_flatm.mean(), "haul_flatm_median": h.haul_flatm.median(),
                 "haul_m_mean": h.haul_m.mean(), "haul_m_p90": h.haul_m.quantile(0.9), "on_outcrop": int(h.on_outcrop.sum()),
                 "unreachable": int((h.haul_flag == "unreachable_local").sum()),
                 **{f"stone_{k}": int(v) for k, v in vc.items()}})
pd.DataFrame(rows).to_csv(os.path.join(OUT, "stone_rule_hauls.csv"), index=False, float_format="%.2f")
# validation on single-stone sites, 9 classes
NINE = {"Basalto": {"basalt"}, "Granito": {"granite"}, "Calcare": {"limestone/marble"}, "Trachite": {"acid volcanic", "trachyte"},
        "Andesite": {"andesite"}, "Porfido": {"granite", "other intrusive"}, "Scisto": {"schist", "metamorphic"},
        "Arenaria": set(), "Marna": set()}
PERM = {"stones4": {"Basalto", "Granito", "Calcare"}, "stones7": {"Basalto", "Granito", "Calcare", "Trachite", "Andesite"}}
val = []
for r, h in H.items():
    d = h.merge(mat[["UID", "stone_material"]], on="UID", how="left")
    single = d[d.stone_material.isin(NINE)]
    if r == "hybrid":
        base = single[single.stone_material.isin([k for k, v in NINE.items() if v])]
        ok = [q in NINE[m] or (m == "Trachite" and q == "tuff") for q, m in zip(base.quarry_stone, base.stone_material)]
        val.append({"rule": r, "single_stone_sites": len(single), "sites_with_rule_stone": len(base),
                    "agree": int(np.sum(ok)), "agree_pct": 100 * np.mean(ok) if ok else np.nan,   # B10
                    "excluded_stone_sites": len(single) - len(base),
                    "note": "recorded stone used by construction (Trachite also matches tuff, as in the mapping)"})
        continue
    base = single[single.stone_material.isin(PERM[r])]
    ok = [q in NINE[m] for q, m in zip(base.quarry_stone, base.stone_material)]
    val.append({"rule": r, "single_stone_sites": len(single), "sites_with_rule_stone": len(base), "agree": int(np.sum(ok)),
                "agree_pct": 100 * np.mean(ok) if ok else np.nan, "excluded_stone_sites": len(single) - len(base),   # B10
                "excluded_pct": 100 * (len(single) - len(base)) / len(single) if len(single) else np.nan, "note": ""})
pd.DataFrame(val).to_csv(os.path.join(OUT, "stone_rule_validation.csv"), index=False, float_format="%.2f")
use = H["hybrid"].merge(mat[["UID", "stone_material"]], on="UID", how="left")
use["value"] = use.stone_material.fillna("<empty>")
u = use.groupby(["value", "Q_SRC"]).size().unstack(fill_value=0).reset_index()
u.to_csv(os.path.join(OUT, "stone_rule_use.csv"), index=False)
# island totals, stones4 vs hybrid
S4 = os.path.join(OUT, "stones4")
cmp_ = []


def isl(path):
    r = pd.read_csv(path, usecols=["seed", "mh_total"]) if path.endswith(".gz") else None
    return float(r.groupby("seed").mh_total.sum().mean())


cmp_.append({"family": "baseline", "scenario": "baseline", "stones4": isl(os.path.join(S4, "nuraghe_manhours_runs.csv.gz")),
             "hybrid": isl(os.path.join(OUT, "nuraghe_manhours_runs.csv.gz"))})
p7 = os.path.join(OUT, "stones7", "nuraghe_manhours_runs.csv.gz")
if os.path.exists(p7):
    cmp_[-1]["stones7"] = isl(p7)
for fam, sub, fn in [("cooperation", "scenarios", "scenario_comparison.csv"), ("literature", "scenarios_lit", "scenario_comparison_lit.csv"),
                     ("alliance", "scenarios_alliance", "alliance_comparison.csv")]:
    a, b = os.path.join(S4, sub, fn), os.path.join(OUT, sub, fn)
    if os.path.exists(a) and os.path.exists(b):
        A, B = pd.read_csv(a).set_index("scenario"), pd.read_csv(b).set_index("scenario")
        for n in A.index.intersection(B.index):
            cmp_.append({"family": fam, "scenario": n, "stones4": float(A.loc[n, "island_mh_mean"]), "hybrid": float(B.loc[n, "island_mh_mean"])})
cm = pd.DataFrame(cmp_)
cm["pct_hybrid_vs_stones4"] = 100 * (cm.hybrid / cm.stones4 - 1)
if "stones7" in cm:
    cm["pct_stones7_vs_stones4"] = 100 * (cm.stones7 / cm.stones4 - 1)
cm.to_csv(os.path.join(OUT, "stone_rule_comparison.csv"), index=False, float_format="%.4f")
pd.set_option("display.width", 220)
print(pd.read_csv(os.path.join(OUT, "stone_rule_hauls.csv")).iloc[:, :8].to_string(index=False))
print(pd.DataFrame(val).round(2).to_string(index=False))
print("hybrid Q_SRC:", dict(H["hybrid"].Q_SRC.value_counts()))
print(cm.round(2).to_string(index=False))
