"""v12 (2 Nov 2026) census queue: the 40 MR_P10 runs of census/TESTABLE_PLAN.md (tier 1, tier 2, tier 3 in the plan's
order), then the X_nurtime single-site predictions (21 small scenarios in one model.py call) and, last, the K5
sensitivity MR_P10_v12_drag10 (drag speed 1.0 m/s, upper bound from Harris 2016's peak; project team 2 Nov).
Estimated wall times: 360 s per MR_P10 run (v11 chain: 329-409 s), 400 s for M2 / levy / lintel, 450 s for S17,
600 s for the unphased S22, 150 s for X_nurtime.
  python tools/v12_queue.py W"""
import os
import sys

import yaml

W = sys.argv[1]
O = os.path.join(W, "outputs")
CFG = os.path.join(O, "config_v12.yaml")
cfg = yaml.safe_load(open(CFG))
names = [k for k in cfg["alliance_census"] if "X_nurtime" not in k]
TIER = {"S4_graded": 1, "S20_lintels": 1, "S15_found": 1, "S17_fill": 1, "S2c_vault": 1, "S22_demog": 1,
        "S4d_spiral": 2, "S4e_laner": 2, "S16_mud": 2, "S13_rifascio": 2, "S23_bichrome": 2, "S21_levy_R": 2,
        "M2_regional": 2, "S12b_feast": 2, "S21_levy_masters": 3, "S19_mudbrick": 3, "S18_clearance": 3,
        "S24_carts": 3, "S25_size": 3}


def tier(n):
    for k, v in TIER.items():
        if n.startswith("MOST_REALISTIC_" + k):
            return v
    raise KeyError(n)


def est(n):
    if "S22_demog" in n:
        return 600
    if "S17_fill" in n:
        return 450
    if any(k in n for k in ("M2_", "levy", "lintels")):
        return 400
    return 360


out = []
for n in sorted(names, key=lambda n: (tier(n), names.index(n))):
    run = n if "S22_demog" in n else n + "_P10"
    out.append((tier(n), n[len("MOST_REALISTIC_"):], "alliance", est(n), 6, CFG, f"--alliance {run}"))
nt = ",".join(k for k in cfg["alliance_census"] if "X_nurtime" in k)
out.append((4, "X_nurtime", "nurtime", 150, 6, CFG,
            f"--sites NID0529600 --alliance {nt} --out {O}/nurtime --parts-dir {O}/nurtime/parts"))
out.append((5, "MR_P10_v12_drag10", "alliance", 330, 6, os.path.join(O, "config_v12_drag10.yaml"),
            f"--alliance MOST_REALISTIC_P10 --parts-dir {O}/drag10/parts"))
with open(os.path.join(O, "queue.tsv"), "w") as f:
    f.write("prio\tlabel\tkind\test_s\tranks\tconfig\targs\n")
    for o in out:
        f.write("\t".join(str(x) for x in o) + "\n")
print(f"{len(out)} entries, {sum(o[3] for o in out) / 3600:.2f} h estimated")
