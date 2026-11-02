"""v12 (2 Nov 2026) updated realism ranking: the v11 consolidated table (all_scenarios_v11.csv, 443 rows) plus the 40
census runs and the K5 drag sensitivity, re-ranked with the same rules as tools/v11_summary.py (current rows first, then
rating_overall, rating, |% island MH vs MR_P10|, name). Census ratings: TESTABLE_PLAN.md (realism, a judgement on the
REALISM_RATINGS.md scale); rating_overall = min(rating, 4) for the P10 runs (schedule rating of P10 = 4, as for the
MOST_REALISTIC family) and = rating for the unphased S22 runs (their calendar is the idea under test).
  python tools/v12_ranking.py W"""
import os
import sys

import numpy as np
import pandas as pd

W = sys.argv[1]
O = os.path.join(W, "outputs")
V11 = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "runs/2026-11-02-v11")
CEN = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "census")
a = pd.read_csv(f"{V11}/outputs/summary_all/all_scenarios_v11.csv")
cs = pd.read_csv(os.path.join(O, "summary", "v12_census_summary.csv"))
cc = pd.read_csv(f"{CEN}/census.csv").set_index("id")
IDS = {"S4_graded": ["D07", "F02"], "S20_lintels": ["D08"], "S15_found": ["F01"], "S17_fill": ["M03"],
       "S2c_vault": ["D02"], "S22_demog": ["W13"], "S4d_spiral": ["L03"], "S4e_laner": ["L02"], "S16_mud": ["M02"],
       "S13_rifascio": ["P06"], "S23_bichrome": ["G05"], "S21_levy_masters": ["W08"], "S21_levy": ["W07"],
       "M2_regional": ["W10"], "S12b_feast": ["E02"], "S19_mudbrick": ["M04"], "S18_clearance": ["Q05"],
       "S24_carts": ["T06"], "S25_size": ["G07"]}
RATE = {"S4_graded": 4, "S20_lintels": 4, "S15_found": 4, "S17_fill": 4, "S2c_vault": 4, "S22_demog": 4, "S4d_spiral": 3,
        "S4e_laner": 3, "S16_mud": 3, "S13_rifascio": 3, "S23_bichrome": 3, "S21_levy_masters": 2, "S21_levy": 3,
        "M2_regional": 3, "S12b_feast": 3, "S19_mudbrick": 2, "S18_clearance": 2, "S24_carts": 2, "S25_size": 2}


def idea(label):
    for k in IDS:                       # longest keys first where they nest (S21_levy_masters before S21_levy)
        if label.startswith(k) and not (k == "S21_levy" and label.startswith("S21_levy_masters")):
            return k
    return None


ref = a[a.scenario == "MOST_REALISTIC_P10"].iloc[0]
new = []
for x in cs.itertuples():
    if x.verdict == "not run":
        continue
    b = {c: np.nan for c in a.columns}
    for c in ("years_mean", "years_min", "years_max", "mh_M_mean", "mh_M_min", "mh_M_max", "n_seeds"):
        b[c] = getattr(x, c)
    if x.label == "MR_P10_v12_drag10":
        b.update(scenario="MR_P10_v12_drag10", family="v12 sensitivity (drag speed)", schedule="P10 simulated (alliance.py)",
                 rating=2, rating_source="project team 2 Nov (K5 check)",
                 rating_reason="upper bound (Harris 2016 peak): 1 m/s is the reported maximum, not a sustained mean",
                 basis="Harris 2016, AAM p. 4", rating_overall=2, schedule_rating=4)
    else:
        k = idea(x.label)
        ids = IDS[k]
        un = x.label.startswith("S22_demog")
        b.update(scenario=f"MOST_REALISTIC_{x.label}" + ("" if un else "_P10"), family="v12 census",
                 schedule="calendar N(t) (S22, unphased)" if un else "P10 simulated (alliance.py)",
                 rating=RATE[k], rating_source="TESTABLE_PLAN.md (2 Nov census) judgement",
                 rating_reason=str(cc.loc[ids[0], "realism_reason"]),
                 basis="; ".join(f"{i}: {cc.loc[i, 'page']}" for i in ids),
                 schedule_rating=np.nan if un else 4, rating_overall=RATE[k] if un else min(RATE[k], 4))
    b["value_source"] = "v12 census run"
    b["source_file"] = "runs/2026-11-02-v12-census/outputs/summary/v12_census_summary.csv"
    b["source_row"] = x.label
    b["season_days"] = 90
    new.append(b)
a = pd.concat([a, pd.DataFrame(new)], ignore_index=True)
a["pct_years_vs_MR_P10"] = 100.0 * (a.years_mean.astype(float) / float(ref.years_mean) - 1.0)
a["pct_mh_vs_MR_P10"] = 100.0 * (a.mh_M_mean.astype(float) / float(ref.mh_M_mean) - 1.0)
a["_cur"] = a.value_source.isin(["v11 rerun", "v10 (not rerun)", "v12 census run"]).astype(int)
a["_absmh"] = a.pct_mh_vs_MR_P10.abs()
a = a.sort_values(["_cur", "rating_overall", "rating", "_absmh", "scenario"],
                  ascending=[False, False, False, True, True]).drop(columns=["_cur", "_absmh"])
a["rank"] = np.arange(1, len(a) + 1)
os.makedirs(os.path.join(O, "summary_all"), exist_ok=True)
a.to_csv(os.path.join(O, "summary_all", "all_scenarios_v12.csv"), index=False, float_format="%.6g")
print(len(a), a.value_source.value_counts().to_dict())
