"""Master comparison table (specified by the authors): every scenario a row.

  python tools/master_table.py --roots RUN/output RUN/output_new --caches RUN/cache RUN/output_new/cache \
         --ratings RUN/REALISM_RATINGS.md --out RUN/output_new/master

Scans each root for baseline (nuraghe_manhours_runs.csv.gz), scenarios/, scenarios_lit/, scenarios_alliance/,
scenarios_pre/ (sensitivity folders skipped). A name found in a later root replaces the earlier one.
Columns (means over seeds):
  island_MH, per_nuraghe_MH (mean site labour), workforce W (sum of builders = all work parties), peak_pop (largest
  number building at once: phased = largest cohort's builders; all at once = W; alliance native schedule = not computed)
  years_max / years_p95: island years of the row's own schedule. Finish-time rule for every row: the island day at
  which the last (max) / 95% (p95) of the nuraghi are finished, / 90. All-at-once rows: max / p95 of site days.
  P100 / P10 / P20 years (max, p95): independent scenarios (baseline, lit, coop without inter-site help, S9 coop):
  P10/P20 post hoc (phasing.cohorts, the same cohorts as the simulated runs). Coupled scenarios (high, alliance, pre):
  P10/P20 from the simulated twin rows NAME_P10 / NAME_P20 when present (source column says which); P100 = the
  all-at-once rule on the sites' own spans (alliance native schedule is a separate column, native_seasons).
  nuraghe_years_mean / _median: a site's own build span (days) / 90.
  realism: from REALISM_RATINGS.md (Code | Rating | Reason): by scenario code; pre-network rows by group (G20_system,
  G133_tribe, G3/G5/G50); sea rows by suffix (_sea = 5 kn -> S9_sea_4/5/6kn; _sea2kn -> S9_sea_2kn); phasing by
  suffix (P10, P20; all-at-once rows -> P100). realism_min = the lowest of the numeric parts (a range counts its low end).
Outputs: master_table.csv (sorted by years_max), master_table.md, master_table.pdf.
"""
import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import phasing  # noqa: E402

SD = 90.0
FAMS = [("coop", "scenarios"), ("lit", "scenarios_lit"), ("alliance", "scenarios_alliance"), ("pre", "scenarios_pre")]
COUPLED_COOP = re.compile(r"^high")
USE = ["seed", "TWR_N", "days", "builders", "mh_total"]


def discover(roots):
    found = {}
    for root in roots:
        f = os.path.join(root, "nuraghe_manhours_runs.csv.gz")
        if os.path.exists(f):
            found["baseline"] = ("baseline", f, root)
        for fam, sub in FAMS:
            for f in sorted(glob.glob(os.path.join(root, sub, "*", "nuraghe_manhours_runs.csv.gz"))):
                found[os.path.basename(os.path.dirname(f))] = (fam, f, root)
    return found


def independent(fam, name):
    if fam in ("baseline", "lit"):
        return True
    return fam == "coop" and not COUPLED_COOP.match(name) and phasing.split_name(name)[1] is None


def parts_dir(caches, name):
    for c in caches[::-1]:
        ds = [d for d in glob.glob(os.path.join(c, "runs", f"alliance_{name}", "*")) if glob.glob(os.path.join(d, "*.done"))]
        if ds:
            return max(ds, key=lambda d: (len(glob.glob(os.path.join(d, "*.done"))), os.path.getmtime(d)))
    return None


def finish_years(fin):
    return fin.max() / SD, np.percentile(fin, 95) / SD


def scenario_row(name, fam, f, caches):
    cols = USE + (["phase", "start_day"] if fam == "coop" else []) + (["finish_season"] if fam in ("alliance", "pre") else [])
    hdr = pd.read_csv(f, nrows=0).columns
    df = pd.read_csv(f, usecols=[c for c in cols if c in hdr])
    frac = phasing.split_name(name)[1] if fam != "lit" else None
    per, ph = [], {}
    pdir = parts_dir(caches, name) if (fam in ("alliance", "pre") and frac) else None
    for s, g in df.groupby("seed", sort=True):
        days = g.days.to_numpy().astype(float); B = g.builders.to_numpy()
        r = {"island_MH": g.mh_total.sum(), "per_nuraghe_MH": g.mh_total.mean(), "workforce": B.sum(),
             "nuraghe_years_mean": days.mean() / SD, "nuraghe_years_median": np.median(days) / SD}
        if frac and "phase" in g:                                   # simulated model.py phasing
            fin = g.start_day.to_numpy() + days - 1
            r["years_max"], r["years_p95"] = finish_years(fin)
            r["peak_pop"] = g.groupby("phase").builders.sum().max()
        elif frac and pdir:                                         # simulated alliance phasing: island finish days
            p = pd.read_csv(os.path.join(pdir, f"seed_{s:04d}.sites.csv.gz"), usecols=["phase", "finish_day", "builders"])
            r["years_max"], r["years_p95"] = finish_years(p.finish_day.to_numpy() + 1.0)
            r["peak_pop"] = p.groupby("phase").builders.sum().max()
        else:                                                       # all-at-once rule on own spans
            r["years_max"], r["years_p95"] = finish_years(days)
            r["peak_pop"] = B.sum() if fam not in ("alliance", "pre") else np.nan
            if fam in ("alliance", "pre"):
                r["native_seasons"] = g.finish_season.max()
        if independent(fam, name):                                  # post hoc P10 / P20
            for lab, fr in (("P10", 0.1), ("P20", 0.2)):
                t0, fin = 0.0, np.zeros(days.size)
                for c in phasing.cohorts(days.size, fr, s):
                    fin[c] = t0 + days[c]; t0 += days[c].max()
                r[f"{lab}_years_max"], r[f"{lab}_years_p95"] = finish_years(fin)
                r[f"{lab}_peak_pop"] = max(B[c].sum() for c in phasing.cohorts(days.size, fr, s))
        per.append(r)
    out = pd.DataFrame(per).mean(numeric_only=True).to_dict()
    out.update({"scenario": name, "family": fam, "seeds": df.seed.nunique(),
                "phasing": {0.1: "P10", 0.2: "P20", 1.0: "P100"}.get(frac, "native" if fam in ("alliance", "pre") else "P100")})
    if independent(fam, name):
        out["P10_source"] = out["P20_source"] = "post hoc"
    return out


# ------------------------------------------------------------------ realism
def load_ratings(path):
    R = {}
    for line in open(path, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 2 and line.startswith("|") and not set(c[0]) <= set("-: ") and c[0] not in ("Code", "Group"):
            R[c[0]] = (c[1], c[2] if len(c) > 2 else "")
    return R


def low(v):
    m = re.match(r"\s*(\d+)", str(v))
    return int(m.group(1)) if m else np.nan


def realism(name, fam, phasing_lab, R):
    base, frac = phasing.split_name(name)
    m = re.match(r"^(.*)_sea(?:([0-9.]+)kn)?$", base)
    kn = None
    if m and fam in ("alliance", "pre"):
        base, kn = m.group(1), float(m.group(2)) if m.group(2) else 5.0
    elif fam == "coop" and base.startswith("S9_sea_"):
        kn = float(base.split("_")[-1].replace("kn", "")); base = None
    elif fam == "coop" and base.endswith("_sea"):
        base, kn = base[:-4], 5.0
    parts = {}
    if base is not None:
        if base.startswith("MOST_REALISTIC_alone"):          # A0 rules with the MOST_REALISTIC technique
            parts["base"] = R.get("A0_alone", ("", ""))[0]
        elif base.startswith("MOST_REALISTIC"):
            parts["base"] = R.get("MOST_REALISTIC", ("", ""))[0]
        elif base in R:
            parts["base"] = R[base][0]
        elif fam == "pre" or base.startswith("P_"):
            key = next((k for k in R if ("G20_system" in base and "G20_system" in k) or ("G133" in base and "G133" in k)), None)
            if key is None and re.search(r"_(G3|G5|G50|G9)", base):
                key = next((k for k in R if k.startswith("G3/G50")), None)
            if key is None and re.search(r"north|central|south|region", base):
                key = next((k for k in R if k.startswith("Regional")), None)
            if key:
                parts["base"] = R[key][0]
        elif base == "baseline":
            parts["base"] = R.get("webster", ("", ""))[0]
    if kn is not None:
        parts["sea"] = R.get("S9_sea_2kn" if kn == 2 else "S9_sea_4/5/6kn", ("", ""))[0]
    if phasing_lab in ("P10", "P20"):
        parts["phasing"] = R.get(phasing_lab, ("", ""))[0]
    elif phasing_lab == "P100":
        parts["phasing"] = R.get("All at once (P100)", ("", ""))[0]
    nums = [low(v) for v in parts.values() if not np.isnan(low(v))]
    return parts.get("base", ""), parts.get("sea", ""), parts.get("phasing", ""), (min(nums) if nums else np.nan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", required=True)
    ap.add_argument("--caches", nargs="+", required=True)
    ap.add_argument("--ratings", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    R = load_ratings(a.ratings)
    found = discover(a.roots)
    rows = {}
    for name, (fam, f, root) in found.items():
        print(f"  {fam:8s} {name}", flush=True)
        rows[name] = scenario_row(name, fam, f, a.caches)
    # coupled scenarios: P10 / P20 from the simulated twins
    for name, r in rows.items():
        fr = phasing.split_name(name)[1]
        if fr is not None and not (fr == 1.0 and phasing.split_name(name)[0] not in rows):
            continue
        if fr == 1.0:                                       # X_P100 with no X row: it carries X's P10 / P20 columns
            name = phasing.split_name(name)[0]
        for lab in ("P10", "P20"):
            tw = rows.get(f"{name}_{lab}")
            if tw is not None and f"{lab}_years_max" not in r:
                r[f"{lab}_years_max"], r[f"{lab}_years_p95"] = tw["years_max"], tw["years_p95"]
                r[f"{lab}_peak_pop"] = tw.get("peak_pop", np.nan); r[f"{lab}_source"] = f"simulated ({name}_{lab})"
        if r["phasing"] in ("P100", "native"):
            r["P100_years_max"], r["P100_years_p95"] = r["years_max"], r["years_p95"]
    for name, r in rows.items():
        r["realism_base"], r["realism_sea"], r["realism_phasing"], r["realism_min"] = realism(name, r["family"], r["phasing"], R)
    t = pd.DataFrame(rows.values())
    cols = ["scenario", "family", "phasing", "seeds", "island_MH", "per_nuraghe_MH", "workforce", "peak_pop",
            "years_max", "years_p95", "P100_years_max", "P100_years_p95", "P10_years_max", "P10_years_p95", "P10_source",
            "P20_years_max", "P20_years_p95", "P20_source", "native_seasons", "nuraghe_years_mean", "nuraghe_years_median",
            "realism_base", "realism_sea", "realism_phasing", "realism_min"]
    for c in cols:
        if c not in t:
            t[c] = np.nan
    t = t[cols].sort_values("years_max").reset_index(drop=True)
    t.to_csv(os.path.join(a.out, "master_table.csv"), index=False, float_format="%.4f")
    show = t.copy()
    for c in ["island_MH", "per_nuraghe_MH", "workforce", "peak_pop"]:
        show[c] = show[c].map(lambda v: "" if pd.isna(v) else f"{v:,.0f}")
    for c in [c for c in cols if "years" in c] + ["native_seasons"]:
        show[c] = show[c].map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    show = show.fillna("")
    with open(os.path.join(a.out, "master_table.md"), "w") as fh:
        fh.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for _, r in show.iterrows():
            fh.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
    try:                                                    # PDF: landscape pages of 40 rows, key columns
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        key = ["scenario", "phasing", "island_MH", "workforce", "peak_pop", "P100_years_max", "P100_years_p95",
               "P10_years_max", "P10_years_p95", "P20_years_max", "P20_years_p95", "nuraghe_years_mean",
               "nuraghe_years_median", "realism_min"]
        with PdfPages(os.path.join(a.out, "master_table.pdf")) as pdf:
            for k in range(0, len(show), 40):
                fig, ax = plt.subplots(figsize=(16.5, 11.7)); ax.axis("off")
                tb = ax.table(cellText=show[key].iloc[k:k + 40].values, colLabels=key, loc="upper center")
                tb.auto_set_font_size(False); tb.set_fontsize(6.5); tb.scale(1, 1.25)
                ax.set_title("Master comparison (sorted by island years of the row's own schedule; years = 90-day seasons)")
                pdf.savefig(fig); plt.close(fig)
    except Exception as e:                                  # the CSV / MD are the deliverable; never fail on the PDF
        print("PDF skipped:", e)
    print(f"{len(t)} scenarios -> {a.out}/master_table.csv")


if __name__ == "__main__":
    main()
