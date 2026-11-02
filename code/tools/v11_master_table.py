"""v11 item (e): the 30 Oct (b) master table had no base rating for 47 rows, so realism_min showed only the schedule
(or sea) rating (e.g. P_none_P10: 4). This fills realism_base from the 1 Nov (b) ratings of the ranked inventory
(all_scenarios_ranked.csv `rating`, with its source and reason; every fill is a JUDGEMENT), recomputes realism_min
(lowest numeric part; a range counts its low end) and writes:
  OUT/master_table_v11.csv  (the 30 Oct (b) table + realism_base_source, realism_base_reason, realism_min_v10)
  CODE/REALISM_RATINGS_V11.md (the 47 filled rows)
Numbers other than the ratings are unchanged (v10 values; the v11 reruns are in v11_runs.csv / all_scenarios_v11.csv).
  python tools/v11_master_table.py MASTER_30OCTB RANKED OUT_DIR CODE_DIR"""
import re
import sys

import pandas as pd

mt_p, rk_p, out_d, code_d = sys.argv[1:5]
mt = pd.read_csv(mt_p, dtype=str, keep_default_na=False)
rk = pd.read_csv(rk_p, dtype=str, keep_default_na=False).set_index("scenario")


def low(v):
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(v))
    return float(m.group(1)) if m else None


mt["realism_min_v10"] = mt.realism_min
mt["realism_base_source"] = ""
mt["realism_base_reason"] = ""
rows = []
for i, r in mt.iterrows():
    if r.realism_base == "":
        k = rk.loc[r.scenario]
        src = k.rating_source
        lab = "judgement (1 Nov b), filled in v11" if src.startswith("NEW") else f"{src}, filled in v11"
        mt.at[i, "realism_base"] = k.rating
        mt.at[i, "realism_base_source"] = lab
        mt.at[i, "realism_base_reason"] = k.rating_reason
        rows.append((r.scenario, k.rating, r.realism_min_v10 or "(none)", lab, k.rating_reason, k.basis))
    else:
        mt.at[i, "realism_base_source"] = "master table 30 Oct (b)"
    parts = [low(mt.at[i, c]) for c in ("realism_base", "realism_sea", "realism_phasing")]
    parts = [p for p in parts if p is not None]
    mt.at[i, "realism_min"] = f"{min(parts):.0f}" if parts else ""
mt.to_csv(f"{out_d}/master_table_v11.csv", index=False)
with open(f"{code_d}/REALISM_RATINGS_V11.md", "w") as f:
    f.write("# v11 (2 Nov 2026): base ratings filled in the 30 Oct (b) master table (item e)\n\n"
            "The 30 Oct (b) master table (report/master_table_2026-10-30b.csv) had an empty base rating for the "
            f"{len(rows)} rows below, so its realism_min showed only the schedule or sea rating. The ratings are the ones "
            "already given in the 1 Nov (b) ranked inventory; they are JUDGEMENTS (same 1-5 scale and rules as "
            "REALISM_RATINGS.md, 29 Oct), not model results. New realism_min = lowest numeric part (base, sea, phasing).\n\n"
            "| Scenario | Base rating | realism_min v10 -> v11 | Label | Reason (judgement) | Basis |\n|---|---|---|---|---|---|\n")
    for n, rt, old, lab, why, basis in rows:
        new = mt.loc[mt.scenario == n, "realism_min"].iloc[0]
        f.write(f"| {n} | {rt} | {old} -> {new} | {lab} | {why} | {basis} |\n")
print(f"filled {len(rows)} base ratings; changed realism_min rows: "
      f"{sum(low(a) != low(b) for a, b in zip(mt.realism_min, mt.realism_min_v10))}")
