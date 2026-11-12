"""v12 (2 Nov 2026) census summary: every finished queue entry against the v11 MOST_REALISTIC_P10 (the reference; the
identity test shows the v12 code reproduces its part files exactly).

  python tools/paired_summary.py W        (W = runs/2026-11-02-v12-census; run under the lock: it reads ~40 x 100 part files)

Per seed, as the earlier v11 summary tool (git history): island MH = sum of mh_total over the 7,167 sites; island years = (max finish_day + 1)
/ 90 (P10 simulated; S22 unphased: the same day count from season 1). Paired by seed (same seed in both runs):
pct_years_s = 100 (years_s / years_ref_s - 1), pct_mh_s likewise; mean and a 95% t interval over the 100 seeds.
Verdict (stated in the report): "moves results" when, for island years or island MH, the paired 95% interval excludes 0
AND the change of the means is at least 1% in size; otherwise "no material effect" (the 1% floor keeps tiny but
seed-consistent shifts, e.g. +0.3% MH, out of the "moves" class). Also: per-nuraghe years (mean of site days / 90),
transport share, mechanism counters.
Outputs: outputs/summary/v12_per_seed.csv, outputs/summary/v12_census_summary.csv, outputs/summary/v12_nurtime.csv
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

W = sys.argv[1]
O = os.path.join(W, "outputs")
V11 = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "runs/2026-11-02-v11")
REF_DIR = f"{V11}/outputs/cache/runs/alliance_MOST_REALISTIC_P10/8a8739cdc5be"
SD = 90.0
EXTRA = ["lintel_wait_seasons", "lintel_fallback", "lintel_helpers", "lintel_own", "mh_lintel", "mh_found",
         "mh_fillcarry", "mh_levy_received", "clear_tonnes", "brick_m3", "tonnes_extra", "cart_site", "mason_wait_days",
         "mason_travel_h", "n_vault"]


def one_dir(base):
    d = sorted(glob.glob(os.path.join(base, "*/")))
    assert len(d) == 1, (base, d)
    return d[0]


def per_seed(d, label):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "seed_*.sites.csv.gz"))):
        s = pd.read_csv(f)
        r = {"label": label, "seed": int(os.path.basename(f)[5:9]), "island_MH": s.mh_total.sum(),
             "years": (s.finish_day.max() + 1) / SD, "site_years_mean": (s.days / SD).mean(),
             "transport_share": s.mh_transport.sum() / s.mh_total.sum(), "tonnes": s.tonnes.sum()}
        for c in EXTRA:
            if c in s:
                r[c] = float(s[c].sum())
        if "lintel_wait_seasons" in s:
            r["lintel_sites_waiting"] = int((s.lintel_wait_seasons > 0).sum())
        rows.append(r)
    return pd.DataFrame(rows)


q = pd.read_csv(os.path.join(O, "queue.tsv"), sep="\t")
ref = per_seed(REF_DIR, "MOST_REALISTIC_P10")
chk = pd.read_csv(f"{V11}/outputs/summary/per_seed_v11.csv")
chk = chk[chk.label == "MOST_REALISTIC_P10"].set_index("seed")
assert np.allclose(ref.set_index("seed").island_MH, chk.island_MH, rtol=1e-5) and \
    np.allclose(ref.set_index("seed").years, chk.years, rtol=1e-5), "reference differs from per_seed_v11.csv"
allp = [ref]
out = []
rs = ref.set_index("seed")


def summarise(label, ps, prio, note=""):
    p = ps.set_index("seed")
    common = p.index.intersection(rs.index)
    r = {"prio": prio, "label": label, "n_seeds": len(p), "note": note}
    for k, col, sc in (("years", "years", 1.0), ("mh_M", "island_MH", 1e-6), ("site_years", "site_years_mean", 1.0)):
        r[f"{k}_mean"], r[f"{k}_min"], r[f"{k}_max"] = p[col].mean() * sc, p[col].min() * sc, p[col].max() * sc
        r[f"{k}_ref_mean"] = rs[col].mean() * sc
        r[f"pct_{k}"] = 100.0 * (p[col].mean() / rs[col].mean() - 1.0)
        d = 100.0 * (p.loc[common, col] / rs.loc[common, col] - 1.0)
        n = len(d)
        h = stats.t.ppf(0.975, n - 1) * d.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
        r[f"pct_{k}_paired_mean"], r[f"pct_{k}_ci_lo"], r[f"pct_{k}_ci_hi"] = d.mean(), d.mean() - h, d.mean() + h
        r[f"pct_{k}_paired_min"], r[f"pct_{k}_paired_max"] = d.min(), d.max()
    r["transport_share"] = p.transport_share.mean()
    for c in EXTRA + ["lintel_sites_waiting"]:
        if c in p:
            r[c + "_mean"] = p[c].mean()
    mv = []
    for k, nm in (("years", "years"), ("mh_M", "man-hours")):
        lo, hi = r[f"pct_{k}_ci_lo"], r[f"pct_{k}_ci_hi"]
        if (lo > 0 or hi < 0) and abs(r[f"pct_{k}"]) >= 1.0:
            mv.append(nm)
    r["verdict"] = "moves results" if mv else "no material effect"
    r["moved"] = " and ".join(mv)
    return r


for x in q.itertuples():
    ok = os.path.exists(os.path.join(O, "logs", f"q_{x.label}.ok"))
    if x.kind != "alliance":
        continue
    if not ok:
        out.append({"prio": x.prio, "label": x.label, "n_seeds": 0, "verdict": "not run", "note": "no .ok marker"})
        continue
    run = x.args.split("--alliance ")[1].split()[0]
    if x.label == "MR_P10_v12_drag10":
        d = one_dir(os.path.join(O, "drag10", "parts", "alliance_MOST_REALISTIC_P10"))
    else:
        d = one_dir(os.path.join(O, "cache", "runs", f"alliance_{run}"))
    ps = per_seed(d, x.label)
    allp.append(ps)
    out.append(summarise(x.label, ps, x.prio, os.path.relpath(d, W)))
os.makedirs(os.path.join(O, "summary"), exist_ok=True)
pd.concat(allp).to_csv(os.path.join(O, "summary", "v12_per_seed.csv"), index=False, float_format="%.6g")
pd.DataFrame(out).to_csv(os.path.join(O, "summary", "v12_census_summary.csv"), index=False, float_format="%.6g")
# X_nurtime: single-site predictions
if os.path.exists(os.path.join(O, "logs", "q_X_nurtime.ok")):
    rows = []
    for d in sorted(glob.glob(os.path.join(O, "nurtime", "parts", "alliance_*", "*/"))):
        nm = d.split("/")[-3][len("alliance_MOST_REALISTIC_X_nurtime_"):]
        lift, crew = nm.rsplit("_c", 1)
        for f in sorted(glob.glob(os.path.join(d, "seed_*.sites.csv.gz"))):
            s = pd.read_csv(f).iloc[0]
            rows.append({"lift": lift, "crew": int(crew), "seed": int(os.path.basename(f)[5:9]),
                         **{c: s[c] for c in ("mh_total", "mh_quarry", "mh_dress", "mh_transport", "mh_build", "mh_lift",
                                              "mh_setup", "days", "tonnes", "builders")}})
    t = pd.DataFrame(rows)
    t["years_90d"] = t.days / 90.0
    t["years_40d"] = t.days / 40.0
    g = t.groupby(["lift", "crew"]).agg(n=("seed", "size"), mh_mean=("mh_total", "mean"), mh_min=("mh_total", "min"),
                                        mh_max=("mh_total", "max"), years40_mean=("years_40d", "mean"),
                                        years40_min=("years_40d", "min"), years40_max=("years_40d", "max"),
                                        years90_mean=("years_90d", "mean"), quarry=("mh_quarry", "mean"),
                                        dress=("mh_dress", "mean"), transport=("mh_transport", "mean"),
                                        build=("mh_build", "mean"), lift_mh=("mh_lift", "mean"),
                                        tonnes=("tonnes", "mean")).reset_index()
    g.to_csv(os.path.join(O, "summary", "v12_nurtime.csv"), index=False, float_format="%.6g")
print(pd.DataFrame(out)[["label", "n_seeds", "verdict"]].to_string())
