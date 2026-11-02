"""Summary of the 1 Nov 2026 scenario-gap runs (S10-S14) against MOST_REALISTIC_P10, from the per-seed part files.

  python tools/gaps_summary.py CFG --parts PARTS_ROOT [--ref-parts REF_ROOT] --names N1,N2,... --out DIR

Per scenario and seed (same definitions as tools/master_table.py, so MOST_REALISTIC_P10 reproduces its row):
  island_mh        sum of mh_total (construction labour; S14 repair labour is separate)
  years_max / p95  island day at which the last / 95% of the nuraghi are finished (finish_day + 1) / 90
  share_transport  sum mh_transport / sum mh_total
  peak_workforce   largest cohort's work parties (phased runs: the builders of every site with a unit in the cohort;
                   S10 smaller-party variant: builders_add for an additions unit)
  workforce        sum of the work parties (keep parties in the S10 variant)
  S12: sites whose drawn party exceeds the food cap (party in MOST_REALISTIC_P10, same seed = same draw)
  S13: tonnes of extra stone; S14: repairs in the build period (simulated) and, post hoc, in the occupation span:
       expected repairs = p_collapse x repair_frac x (man-hours of the site's towers) x remaining years, where a
       site's occupation runs occupation_years from its own finish and the build period already covers
       (island end - site finish); routine upkeep at an annual share of the build labour (analogue) is a
       separate line (--upkeep-share, default 0.012 = WOCAT 2007: 250, dry-stone terraces).
Outputs: gaps_by_seed.csv, gaps_summary.csv (mean, min, max, p5, p95 over seeds; % change vs the reference).
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import alliance  # noqa: E402

SD = 90.0
REF = "MOST_REALISTIC_P10"


def part_dir(root, name):
    ds = [d for d in glob.glob(os.path.join(root, f"alliance_{name}", "*")) if glob.glob(os.path.join(d, "*.done"))]
    if not ds:
        return None
    return max(ds, key=lambda d: (len(glob.glob(os.path.join(d, "*.done"))), os.path.getmtime(d)))


def seed_row(df, sc, ref_b, upkeep):
    fin = df.finish_day.to_numpy() + 1.0
    r = {"island_mh": df.mh_total.sum(), "years_max": fin.max() / SD, "years_p95": np.percentile(fin, 95) / SD,
         "share_transport": df.mh_transport.sum() / df.mh_total.sum(), "workforce": df.builders.sum(),
         "tonnes": df.tonnes.sum(), "nuraghe_years_mean": df.days.mean() / SD,
         "nuraghe_years_median": np.median(df.days) / SD}
    pk = []
    for k in sorted(set(df.phase) | set(df.get("phase_add", pd.Series([], dtype=int)))):
        if k < 0:
            continue
        b = df.builders[df.phase == k].sum()
        if "phase_add" in df:
            ba = df.builders_add if "builders_add" in df else df.builders
            b += ba[df.phase_add == k].sum()
        pk.append(b)
    r["peak_workforce"] = max(pk)
    if "tonnes_extra" in df:
        r["tonnes_extra"] = df.tonnes_extra.sum()
    if "staged" in df:
        r["n_staged"] = int(df.staged.sum())
    if "food_cap" in df and ref_b is not None:
        r["food_binding_sites"] = int((ref_b > df.food_cap.to_numpy()).sum())
        r["food_cap_median"] = float(np.median(df.food_cap))
        r["workforce_ref"] = int(ref_b.sum())
    M = sc.get("maintenance")
    if M:
        r["mh_repair_build"] = df.mh_repair.sum()
        r["n_collapse_build"] = int(df.n_collapse.sum())
        rem = np.maximum(0.0, float(M["occupation_years"]) - (fin.max() - fin) / SD)
        r["mh_repair_occupation"] = float((float(M["p_collapse"]) * float(M["repair_frac"]) * df.tower_mh * rem).sum())
        r["mh_repair_total"] = r["mh_repair_build"] + r["mh_repair_occupation"]
        r["mh_upkeep_analogue"] = upkeep * df.tower_mh.sum() * float(M["occupation_years"])
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cfg")
    ap.add_argument("--parts", required=True, help="cache/runs root of the new runs")
    ap.add_argument("--ref-parts", help="cache/runs root holding the reference MOST_REALISTIC_P10 (default --parts)")
    ap.add_argument("--names", required=True)
    ap.add_argument("--seeds", default="1-100")
    ap.add_argument("--upkeep-share", type=float, default=0.012)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.cfg))
    s0, s1 = (int(x) for x in a.seeds.split("-"))
    seeds = range(s0, s1 + 1)
    names = [REF] + [n for n in a.names.split(",") if n != REF]
    rows = []
    ref_b = {}
    for name in names:
        root = (a.ref_parts or a.parts) if name == REF else a.parts
        d = part_dir(root, name)
        if d is None:
            print(f"{name}: no parts, skipped"); continue
        sc = alliance.scenario(cfg, name)
        for s in seeds:
            f = os.path.join(d, f"seed_{s:04d}.sites.csv.gz")
            if not os.path.exists(f):
                raise SystemExit(f"{name}: seed {s} missing in {d}")
            df = pd.read_csv(f)
            if name == REF:
                ref_b[s] = df.builders.to_numpy()
            r = seed_row(df, sc, ref_b.get(s), a.upkeep_share)
            r.update({"scenario": name, "seed": s, "seasons": int(open(f.replace(".sites.csv.gz", ".done")).read())})
            rows.append(r)
        print(f"{name}: {len(seeds)} seeds from {d}", flush=True)
    by = pd.DataFrame(rows)
    os.makedirs(a.out, exist_ok=True)
    by.to_csv(os.path.join(a.out, "gaps_by_seed.csv"), index=False, float_format="%.6g")
    num = [c for c in by.columns if c not in ("scenario", "seed")]
    out = []
    ref = by[by.scenario == REF].set_index("seed")
    for name, g in by.groupby("scenario", sort=False):
        r = {"scenario": name, "seeds": len(g)}
        for c in num:
            v = g[c].dropna()
            if not len(v):
                continue
            r[c + "_mean"], r[c + "_min"], r[c + "_max"] = v.mean(), v.min(), v.max()
            r[c + "_p5"], r[c + "_p95"] = np.percentile(v, 5), np.percentile(v, 95)
        if len(ref):
            for c in ("island_mh", "years_max", "years_p95", "share_transport", "peak_workforce"):
                r[c + "_pct_vs_ref"] = 100.0 * (g[c].mean() / ref[c].mean() - 1.0)
            gi = g.set_index("seed")
            d = 100.0 * (gi.years_max / ref.years_max.reindex(gi.index) - 1.0)        # paired, same seed
            r["years_max_pct_paired_min"], r["years_max_pct_paired_max"] = d.min(), d.max()
            d = 100.0 * (gi.island_mh / ref.island_mh.reindex(gi.index) - 1.0)
            r["island_mh_pct_paired_min"], r["island_mh_pct_paired_max"] = d.min(), d.max()
        out.append(r)
    pd.DataFrame(out).to_csv(os.path.join(a.out, "gaps_summary.csv"), index=False, float_format="%.6g")
    print(pd.DataFrame(out)[["scenario", "seeds", "island_mh_mean", "years_max_mean", "share_transport_mean",
                             "peak_workforce_mean"]].to_string(index=False))


if __name__ == "__main__":
    main()
