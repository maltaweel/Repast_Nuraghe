"""v11 (2 Nov 2026) summary of the reruns and the consolidated ranked table of every scenario.

  python tools/v11_summary.py W            (W = runs/2026-11-02-v11; reads W/outputs/queue.tsv, W/outputs/logs/q_*.ok,
                                            the v10 ranked inventory and the v11 outputs; writes W/outputs/summary/ and
                                            W/outputs/summary_all/)
Per seed, with the same arithmetic as tools/master_table.py / the 1 Nov (b) inventory (compute_per_seed.py):
  island MH = sum of mh_total over the 7,167 sites; island years = P10/P20/P100 simulated (alliance/pre `_Pxx`
  names): (max finish_day + 1) / 90 from the part files; all at once (coop, baseline, lit, TOST) and alliance/pre
  without suffix (all-at-once rule on the sites' own spans): max site days / 90. mean / min / max over seeds.
Outputs
  summary/per_seed_v11.csv     one row per (run, seed)
  summary/v11_runs.csv         one row per queue entry: status (v11 rerun / dropped / failed / not run), v11 and v10
                               values, changes, source files
  summary_all/all_scenarios_v11.csv  the 1 Nov (b) ranked inventory (442 rows) + MR_P10_v11_pull125, with
                               value_source = "v11 rerun" | "v10 (not rerun)" | "obsolete (...)" | "superseded (...)",
                               v11 values where rerun, % vs the v11 MR_P10, re-ranked with the 1 Nov (b) rules.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

W = sys.argv[1]
O = os.path.join(W, "outputs")
P = os.environ.get("NURAGHE_PROJECT", ".")
RANKED = f"{P}/runs/2026-11-01-wider-lit/outputs/summary_all/all_scenarios_ranked.csv"
sys.path.insert(0, os.path.join(W, "code"))
import phasing  # noqa: E402

SD = 90.0
rel = lambda p: os.path.relpath(p, P)


def runs_file(label, kind, args):
    a = args.split()
    if label == "MR_P10_v11_pull125":
        return f"{O}/pull125/scenarios_alliance/MOST_REALISTIC_P10/nuraghe_manhours_runs.csv.gz"
    if kind == "tost":
        return os.path.join(a[a.index("--out") + 1], "nuraghe_manhours_runs.csv.gz")
    if kind == "baseline":
        return f"{O}/scenarios/baseline/nuraghe_manhours_runs.csv.gz"
    sub = {"alliance": "scenarios_alliance", "pre": "scenarios_pre", "coop": "scenarios", "lit": "scenarios_lit"}[kind]
    return f"{O}/{sub}/{label}/nuraghe_manhours_runs.csv.gz"


def parts_dir(label, kind, args):
    if label == "MR_P10_v11_pull125":
        base, name = f"{O}/pull125/parts", "MOST_REALISTIC_P10"
    else:
        base, name = f"{O}/cache/runs", label
    ds = [d for d in glob.glob(f"{base}/*_{name}/*") if os.path.basename(os.path.dirname(d)).endswith("_" + name)
          and os.path.basename(os.path.dirname(d)) in (f"alliance_{name}", f"pre_{name}") and glob.glob(f"{d}/*.done")]
    if len(ds) != 1:
        raise RuntimeError(f"{label}: expected one signature folder with part files, found {ds}")
    return ds[0]


def per_seed(label, kind, args):
    f = runs_file(label, kind, args)
    name = "MOST_REALISTIC_P10" if label == "MR_P10_v11_pull125" else label
    frac = phasing.split_name(name)[1] if kind in ("alliance", "pre") else None
    df = pd.read_csv(f, usecols=lambda c: c in ("seed", "days", "mh_total"))
    pdir = parts_dir(label, kind, args) if frac else None
    rows = []
    for s, g in df.groupby("seed", sort=True):
        r = {"label": label, "seed": int(s), "island_MH": g.mh_total.sum()}
        if frac:
            p = pd.read_csv(os.path.join(pdir, f"seed_{int(s):04d}.sites.csv.gz"), usecols=["finish_day"])
            r["years"] = (p.finish_day.to_numpy() + 1.0).max() / SD
            r["schedule"] = f"P{int(round(frac * 100))} simulated"
        else:
            r["years"] = g.days.max() / SD
            r["schedule"] = "all at once" if kind not in ("alliance", "pre") else "all-at-once rule on own spans"
        rows.append(r)
    return pd.DataFrame(rows), f, pdir


q = pd.read_csv(os.path.join(O, "queue.tsv"), sep="\t", dtype=str, keep_default_na=False)
dropped = set()
dp = os.path.join(O, "logs", "dropped.tsv")
if os.path.exists(dp):
    dropped = set(pd.read_csv(dp, sep="\t").label)
rk = pd.read_csv(RANKED)
rk_by = rk.set_index("scenario")
ps, runs = [], []
NOTES = open(os.path.join(W, "code", "V11_NOTES.md"), encoding="utf-8").read()
for _, e in q.iterrows():
    ok = os.path.exists(os.path.join(O, "logs", f"q_{e.label}.ok"))
    mem = os.path.join(O, "logs", f"q_{e.label}.mem")
    wall = ""
    if os.path.exists(mem):
        t = open(mem).read().strip().splitlines()
        wall = next((x.split("wall ")[1].split(" s")[0] for x in t[-1:] if "wall " in x), "")
    r = {"prio": int(e.prio), "label": e.label, "kind": e.kind, "wall_s": wall}
    if ok:
        d, f, pdir = per_seed(e.label, e.kind, e.args)
        ps.append(d)
        r.update(status="v11 rerun", n_seeds=len(d), schedule=d.schedule.iloc[0],
                 years_mean=d.years.mean(), years_min=d.years.min(), years_max=d.years.max(),
                 mh_M_mean=d.island_MH.mean() / 1e6, mh_M_min=d.island_MH.min() / 1e6,
                 mh_M_max=d.island_MH.max() / 1e6, runs_file=rel(f), parts_dir=rel(pdir) if pdir else "")
    else:
        r["status"] = "dropped (time)" if e.label in dropped else \
            ("failed" if f"FAILED q_{e.label} " in NOTES else "not run (queue unfinished)")
    v10 = "MOST_REALISTIC_P10" if e.label == "MR_P10_v11_pull125" else e.label
    if v10 in rk_by.index and e.label != "MR_P10_v11_pull125":
        x = rk_by.loc[v10]
        r.update(v10_years_mean=x.years_mean, v10_mh_M_mean=x.mh_M_mean, v10_n_seeds=x.n_seeds,
                 v10_source=f"{x.source_file} row {x.source_row}")
    runs.append(r)
runs = pd.DataFrame(runs)
for c, k in (("years", "years"), ("mh_M", "mh")):
    if f"{c}_mean" in runs and "v10_" + c + "_mean" in runs:
        runs[f"pct_{k}_v11_vs_v10"] = 100.0 * (runs[f"{c}_mean"] / runs[f"v10_{c}_mean"] - 1.0)
os.makedirs(os.path.join(O, "summary"), exist_ok=True)
os.makedirs(os.path.join(O, "summary_all"), exist_ok=True)
if ps:
    pd.concat(ps, ignore_index=True).to_csv(os.path.join(O, "summary", "per_seed_v11.csv"), index=False,
                                            float_format="%.6g")
runs.to_csv(os.path.join(O, "summary", "v11_runs.csv"), index=False, float_format="%.6g")

# ------------------------------------------------------------------ consolidated ranked table
a = rk.copy()
a["v10_years_mean"], a["v10_mh_M_mean"], a["v10_n_seeds"] = a.years_mean, a.mh_M_mean, a.n_seeds
a["value_source"] = "v10 (not rerun)"
a.loc[a.superseded == 1, "value_source"] = "superseded (pre-fix code; kept for the record)"
obs = a.scenario.str.contains(r"\[season \d+ d\]", regex=True)
a.loc[obs, "value_source"] = "obsolete (pre-fix code; season-length scenario dropped by the authors on 30 Oct)"
a["v11_source_file"] = ""
R = runs.set_index("label")
for i, x in a.iterrows():
    if x.superseded == 1 or x.scenario not in R.index or R.loc[x.scenario, "status"] != "v11 rerun":
        continue
    y = R.loc[x.scenario]
    for c in ("years_mean", "years_min", "years_max", "mh_M_mean", "mh_M_min", "mh_M_max", "n_seeds"):
        a.at[i, c] = y[c]
    a.at[i, "value_source"] = "v11 rerun"
    a.at[i, "v11_source_file"] = y.runs_file
if "MR_P10_v11_pull125" in R.index and R.loc["MR_P10_v11_pull125", "status"] == "v11 rerun":
    y = R.loc["MR_P10_v11_pull125"]
    b = a[a.scenario == "MOST_REALISTIC_P10"].iloc[0].copy()
    b["scenario"] = "MR_P10_v11_pull125"
    b["family"] = "v11 sensitivity (pulling force)"
    for c in ("years_mean", "years_min", "years_max", "mh_M_mean", "mh_M_min", "mh_M_max", "n_seeds"):
        b[c] = y[c]
    b["v10_years_mean"] = b["v10_mh_M_mean"] = b["v10_n_seeds"] = np.nan
    b["rating"], b["rating_source"] = 3, "NEW (v11) judgement"
    b["rating_reason"] = ("MOST_REALISTIC_P10 with every person pulling 125 N, the sustained effort (Boswinkel 2021: "
                          "52), instead of the 300 N peak; crews are re-formed for every haul, so bursts are possible "
                          "and 125 N is a lower bound on pulling force: a bound, not the headline")
    b["basis"] = "Boswinkel 2021: 52 (Hertzberg 1972: 574, 104 W at 0.83 m/s), 111 (300 N peak); Harris 2016"
    b["rating_overall"] = min(3, int(b.schedule_rating)) if pd.notna(b.schedule_rating) else 3
    b["value_source"] = "v11 rerun"
    b["v11_source_file"] = y.runs_file
    b["source_file"], b["source_row"] = "runs/2026-11-02-v11/outputs/summary/v11_runs.csv", "MR_P10_v11_pull125"
    b["note"] = "v11 sensitivity (d): 300 N -> 125 N per person on land hauls; sea boat factor unchanged"
    a = pd.concat([a, b.to_frame().T], ignore_index=True)
k = a.scenario == "MOST_REALISTIC_C2_day5_P10"                  # v11: reason updated after reading Webster 1991: 852
a.loc[k, "rating_reason"] = ("Alternative reading of Webster's day length (v11 sensitivity, = MR_P10_v11_day5all): reads "
                             "his Abrams-based dressing and walling man-days as 5-h days too, against Abrams's 8-h day "
                             "(Boswinkel 2021: 109, 125, 146); Webster's quarry and haul man-days are Erasmus's 5-h "
                             "days, but MOST_REALISTIC uses neither")
a.loc[k, "rating_source"] = "REALISM_RATINGS_WL_1101.md (rating); reason updated in v11 (judgement)"
a.loc[k, "basis"] = "Webster 1991: 852 (Erasmus 1965: 283, 286-7; Abrams 1984: 165, 175-6); Boswinkel 2021: 109, 145-146"
ref = a[a.scenario == "MOST_REALISTIC_P10"].iloc[0]
a["pct_years_vs_MR_P10"] = 100.0 * (a.years_mean.astype(float) / float(ref.years_mean) - 1.0)
a["pct_mh_vs_MR_P10"] = 100.0 * (a.mh_M_mean.astype(float) / float(ref.mh_M_mean) - 1.0)
a["pct_years_v11_vs_v10"] = np.where(a.value_source == "v11 rerun",
                                     100.0 * (a.years_mean.astype(float) / a.v10_years_mean.astype(float) - 1.0), np.nan)
a["pct_mh_v11_vs_v10"] = np.where(a.value_source == "v11 rerun",
                                  100.0 * (a.mh_M_mean.astype(float) / a.v10_mh_M_mean.astype(float) - 1.0), np.nan)
a["_cur"] = a.value_source.isin(["v11 rerun", "v10 (not rerun)"]).astype(int)
a["_absmh"] = a.pct_mh_vs_MR_P10.abs()
a = a.sort_values(["_cur", "rating_overall", "rating", "_absmh", "scenario"],
                  ascending=[False, False, False, True, True]).drop(columns=["_cur", "_absmh"])
a["rank"] = np.arange(1, len(a) + 1)
a.to_csv(os.path.join(O, "summary_all", "all_scenarios_v11.csv"), index=False, float_format="%.6g")
st = runs.status.value_counts().to_dict()
print("queue:", st, "| table rows:", len(a), a.value_source.value_counts().to_dict())
