"""v11 (2 Nov 2026) rerun queue, in the authors' priority order (1 Nov 21:05):
  0 identity (v11 code, switches off) MR_P10 -> handled by the chain itself
  1 v11 MR_P10 (new headline), MR_P10_v11_pull125 (sensitivity d), MR_P10_v11_day5all (= C2_day5, the alternative
    reading of Webster's day length, item 1)
  2 every scenario rated 5 in all_scenarios_ranked.csv (current, i.e. not superseded / obsolete)
  3 every scenario rated 4 (same), in the ranked file's order
  4 the remaining 1 Nov S10-S14 and C1-C3 / M1-M4 variants, highest rating first
Writes outputs/queue.tsv: prio, label, kind, est_s, ranks, config, args (model.py arguments after the config).
Estimated wall times (s, 100 seeds) from the 29 Oct - 1 Nov chain logs (runs/2026-10-29-bugfix/output_new/logs,
runs/2026-11-01-wider-lit/code/WIDER_LIT_1101.md); pull125 from the 300-site subset (about 2x the island days).
  python tools/v11_queue.py RANKED_CSV OUT_DIR"""
import csv
import os
import sys

ranked_p, O = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(ranked_p)))
CFG = os.path.join(O, "config_v11.yaml")
TOST_VARS = {"block_sigma_min", "block_sigma_max", "household_size_min", "household_size_max", "hours_per_day_min",
             "hours_per_day_max", "block_median_kg_min", "block_median_kg_max"}
LIT = {"webster", "S1a_scree", "S1b_joints_low", "S1b_joints_high", "S2a_unworked", "S2b_fine", "S3a_rails_tallow",
       "S3b_rails_grease", "S3c_dry_ground", "S3d_rough", "S3e_oxen", "S4a_lever", "S4b_ramp", "S4c_stair", "S5a_onsite",
       "S5b_any_buildstone", "S5c_complex_far", "S6_density", "S7_classes", "S8_learning", "LOW", "HIGH", "REALISTIC",
       "REALISTIC_oxen"}
COOP = {"none", "low", "mixed", "mostly", "full", "patchwork", "S9_sea_2kn", "S9_sea_4kn", "S9_sea_5kn", "S9_sea_6kn"}


def est_alliance(n):
    if n.startswith("MOST_REALISTIC"):
        if n.endswith("_P100"):
            return 1550
        if n.endswith("_P20"):
            return 750
        if "_M4_any" in n:
            return 560
        if "_M2_" in n or "_M4_" in n:
            return 400
        return 360
    return 320 if n.endswith("_P20") else 250 if n.endswith("_P10") else 160


def spec(label, family):
    """(kind, est_s, ranks, config, args) for one ranked-file row."""
    if "TOST" in family:
        sc, var = label.split("_TOST_")
        assert var in TOST_VARS, label
        return ("tost", 160, 8, os.path.join(O, "tost_configs", f"{var}.yaml"),
                f"--scenario {sc} --out {O}/tost/{sc}/{var} --parts-dir {O}/tost/{sc}/{var}/parts")
    if label == "baseline":
        return ("baseline", 140, 8, CFG, "")
    if label in LIT:
        return ("lit", 165, 8, CFG, f"--lit {label}")
    if label in COOP:
        return ("coop", 150, 8, CFG, f"--scenario {label}")
    if label.startswith("P_"):
        e = 190 if label.endswith("_P20") else 150 if label.endswith("_P10") else 200
        return ("pre", e, 6, CFG, f"--pre {label}")
    return ("alliance", est_alliance(label), 6, CFG, f"--alliance {label}")


cur = [r for r in rows if r["superseded"] == "0"]
out = [(1, "MOST_REALISTIC_P10", "alliance", 360, 6, CFG, "--alliance MOST_REALISTIC_P10"),
       (1, "MR_P10_v11_pull125", "alliance", 700, 6, os.path.join(O, "config_v11_pull125.yaml"),
        f"--alliance MOST_REALISTIC_P10 --parts-dir {O}/pull125/parts"),
       (1, "MOST_REALISTIC_C2_day5_P10", "alliance", 360, 6, CFG, "--alliance MOST_REALISTIC_C2_day5_P10")]
seen = {o[1] for o in out}
for prio, rating in ((2, "5"), (3, "4")):
    for r in cur:
        if r["rating"] == rating and r["scenario"] not in seen:
            out.append((prio, r["scenario"]) + spec(r["scenario"], r["family"]))
            seen.add(r["scenario"])
today = [r for r in cur if r["family"].startswith(("S10-S14", "Wider literature")) and r["scenario"] not in seen]
today.sort(key=lambda r: (-int(r["rating"]), int(r["rank"])))
for r in today:
    out.append((4, r["scenario"]) + spec(r["scenario"], r["family"]))
with open(os.path.join(O, "queue.tsv"), "w") as f:
    f.write("prio\tlabel\tkind\test_s\tranks\tconfig\targs\n")
    for o in out:
        f.write("\t".join(str(x) for x in o) + "\n")
tot = sum(o[3] for o in out)
print(f"{len(out)} runs, estimated {tot / 3600:.2f} h")
for p in (1, 2, 3, 4):
    s = [o for o in out if o[0] == p]
    print(f"  prio {p}: {len(s)} runs, {sum(o[3] for o in s) / 60:.0f} min")
