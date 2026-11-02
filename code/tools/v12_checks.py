"""v12 (2 Nov 2026) census post hoc checks (TESTABLE_PLAN.md part B, 10 checks, 0 runs) on the delivered v11 outputs.

  python tools/v12_checks.py W      (W = runs/2026-11-02-v12-census; run under the lock)

Inputs (read only): v11 MOST_REALISTIC_P10 per-site summary (scenarios_alliance/MOST_REALISTIC_P10/
nuraghe_manhours_summary.csv: mean over 100 seeds of man-hours, build days, builders, the face-0 route length haul_m),
its 100 part files (per seed: builders, start/finish day, own man-hours), v11 summary/v11_runs.csv (P10, P20, P100 island
years), the hybrid haul tables (cache/sites_haul.csv: recorded / fallback stone, on_outcrop), the hybrid outcrop raster
(cache/outcrop_code.tif) and the 1:250,000 soil map (land-capability classes, Aru et al. 1991).
Route length = the site's least-cost (mu 0.3) route to its nearest allowed outcrop, as hauled by MR_P10 when it keeps
quarry face 0 (the model may choose a farther face in a seed; face 0 is the reference here).
Outputs: outputs/checks/checks_v12.csv (one row per check: model value, reference value, source, verdict) and detail
tables outputs/checks/*.csv.
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
MR = f"{V11}/outputs/scenarios_alliance/MOST_REALISTIC_P10"
PARTS = f"{V11}/outputs/cache/runs/alliance_MOST_REALISTIC_P10/8a8739cdc5be"
CD = os.path.join(O, "checks")
os.makedirs(CD, exist_ok=True)
SD = 90.0
s = pd.read_csv(f"{MR}/nuraghe_manhours_summary.csv")
h = pd.read_csv(os.path.join(O, "cache", "sites_haul.csv"))
s = s.merge(h[["UID", "quarry_stone", "on_outcrop", "Q_SRC"]], on="UID", how="left")
v11 = pd.read_csv(f"{V11}/outputs/summary/v11_runs.csv").set_index("label")
res = []


def add(check, ids, metric, model, ref, source, verdict, note=""):
    res.append({"check": check, "census_ids": ids, "metric": metric, "model": model, "reference": ref,
                "source": source, "verdict": verdict, "note": note})


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    w = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - w, c + w


# 1 V_gallin (G01): Marghine sites with haul > 2 km vs Gallin's 7 of 113 (REPORTED-ONLY via Webster 1991: 848)
MARGHINE = ["Birori", "Bolotana", "Borore", "Bortigali", "Dualchi", "Lei", "Macomer", "Noragugume", "Silanus"]
m = s[s.COMUNE.isin(MARGHINE)]
k = int((m.haul_m > 2000).sum())
lo, hi = wilson(7, 113)
sh = k / len(m)
add("V_gallin", "G01", "share of Marghine sites with route > 2 km", f"{100 * sh:.1f}% ({k} of {len(m)})",
    "6.2% (7 of 113); 95% interval 3.0-12.2%", "Gallin 1989 via Webster 1991: 848 (REPORTED-ONLY)",
    "consistent" if lo <= sh <= hi else ("model more local" if sh < lo else "model less local"),
    f"Marghine = the 9 comuni {', '.join(MARGHINE)} (our delimitation; Gallin's area is not mapped)")
m[["UID", "NAME", "COMUNE", "TWR_N", "haul_m", "quarry_stone", "on_outcrop"]].to_csv(f"{CD}/v_gallin_sites.csv", index=False)

# 2 V_provenance (G06): three excavated sites
_sn = s[(s.COMUNE == "Barumini") & (s.NAME == "Nuraghe Su Nuraxi")].iloc[0]
_mf = s[(s.COMUNE == "Barumini") & (s.NAME == "Nuraghe Marfudi")].iloc[0]
D_MARF = float(np.hypot(_sn.x - _mf.x, _sn.y - _mf.y))           # the source lies on the slope between the two
SITES = {"Su Nuraxi (Barumini)": ("Barumini", "Nuraxi", "basalt recovered from the slope towards nuraghe Marfudi "
                                   f"(Marfudi lies {D_MARF:,.0f} m away, Nurnet coordinates)", "Lilliu & Zucca 2005: 40-41",
                                   (0, D_MARF)),
         "S'Urachi (San Vero Milis)": ("San Vero Milis", "Urachi", "basalt from about 3 km", "Stiglitz et al. 2012: 921-922",
                                        (2250, 3750)),
         "Duos Nuraghes (Borore)": ("Borore", "Duos", "the basalt knoll the towers stand on", "Webster 1991: 848",
                                    (0, 200))}
pv = []
for lab, (com, key, pub, src, rng) in SITES.items():
    x = s[(s.COMUNE == com) & s.NAME.str.contains(key, case=False, na=False)].sort_values("TWR_N", ascending=False)
    if x.empty:
        add("V_provenance", "G06", f"{lab}: route length and stone", "site not in the Nurnet list", pub, src, "not checkable")
        continue
    r = x.iloc[0]
    ok = rng[0] <= r.haul_m <= rng[1]
    pv.append({"site": lab, "UID": r.UID, "NAME": r.NAME, "TWR_N": int(r.TWR_N), "haul_m": r.haul_m,
               "quarry_stone": r.quarry_stone, "on_outcrop": bool(r.on_outcrop), "Q_SRC": r.Q_SRC, "published": pub})
    add("V_provenance", "G06", f"{lab}: route length and stone",
        f"{r.haul_m:,.0f} m, {r.quarry_stone}{', on its outcrop' if r.on_outcrop else ''}", pub, src,
        "consistent" if ok else "inconsistent", f"{r.UID}, TWR_N {int(r.TWR_N)}; accepted range {rng[0]:,.0f}-{rng[1]:,.0f} m "
        "(S'Urachi: about 3 km +/- 25%, our tolerance)")
pd.DataFrame(pv).to_csv(f"{CD}/v_provenance.csv", index=False)

# 3 V_sarcidano (G03): Nurri and Orroli
x = s[s.COMUNE.isin(["Nurri", "Orroli"])].sort_values("haul_m", ascending=False)
loc = x.haul_m <= 1000
add("V_sarcidano", "G03", "Nurri and Orroli: share with route <= 1 km; longest routes",
    f"{100 * loc.mean():.1f}% ({int(loc.sum())} of {len(x)}); longest {x.haul_m.iloc[0]:,.0f} m ({x.NAME.iloc[0]}), "
    f"{int((x.haul_m > 2000).sum())} sites > 2 km",
    "most fortresses on local rock; site importance could override (one non-local tower in the sample)",
    "Orgiana 2012 (page not recoverable)",
    "consistent" if loc.mean() > 0.5 and (x.haul_m > 2000).sum() <= 0.1 * len(x) else "inconsistent",
    "the non-local tower is not named in the Catalogue text, so the site-level match cannot be made")
x[["UID", "NAME", "COMUNE", "TWR_N", "haul_m", "quarry_stone", "on_outcrop"]].to_csv(f"{CD}/v_sarcidano.csv", index=False)

# 4 V_sangavino (T11)
x = s[s.COMUNE.str.contains("San Gavino", na=False)]
add("V_sangavino", "T11", "San Gavino Monreale: route lengths",
    f"{len(x)} sites; median {x.haul_m.median():,.0f} m, max {x.haul_m.max():,.0f} m; {int((x.haul_m >= 5000).sum())} at >= 5 km",
    "up to 10 km from the stone source", "blog, unattributed quotation (REPORTED-ONLY)",
    "consistent" if x.haul_m.max() >= 5000 else "inconsistent (model sources nearer)",
    "the model takes the nearest allowed outcrop; a claim of 10 km is a choice the model would not make")
x[["UID", "NAME", "TWR_N", "haul_m", "quarry_stone", "on_outcrop"]].to_csv(f"{CD}/v_sangavino.csv", index=False)

# 5 V_density_stone (Q05): density vs stoniness proxy (outcrop share) in 5 km cells, controlling for land capability
import geopandas as gpd  # noqa: E402
import rasterio  # noqa: E402
with rasterio.open(os.path.join(O, "cache", "outcrop_code.tif")) as r:
    a = r.read(1)
    T = r.transform
    crs = r.crs
cs = 5000
nr, nc = a.shape
k = int(cs / T.a)
cs = k * T.a                                     # 166 cells x 30 m = 4,980 m: raster blocks and polygons coincide
H2, W2 = nr // k, nc // k
blk = (a[:H2 * k, :W2 * k] > 0).reshape(H2, k, W2, k).mean(axis=(1, 3))
del a
soil = gpd.read_file(os.path.join(os.environ.get("NURAGHE_DATA", "data"), "soils", "soils250k.geojson")).to_crs(crs)
soil["lcc"] = soil.CLASSI.astype(str).str.extract(r"(I{1,3}V?|IV|VI{0,3}|V)")[0].map(
    {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8})
from shapely.geometry import box  # noqa: E402
cells = []
for i in range(H2):
    for j in range(W2):
        x0 = T.c + j * cs
        y1 = T.f - i * cs
        cells.append((i, j, box(x0, y1 - cs, x0 + cs, y1)))
g = gpd.GeoDataFrame({"i": [c[0] for c in cells], "j": [c[1] for c in cells]}, geometry=[c[2] for c in cells], crs=crs)
ov = gpd.overlay(g, soil[["lcc", "geometry"]].dropna(), how="intersection")
ov["a"] = ov.area
lcc = ov.groupby(["i", "j"]).apply(lambda d: np.average(d.lcc, weights=d.a), include_groups=False).rename("lcc")
land = ov.groupby(["i", "j"]).a.sum().rename("land_m2")
ci = ((T.f - s.y) // cs).astype(int)
cj = ((s.x - T.c) // cs).astype(int)
cnt = pd.DataFrame({"i": ci, "j": cj, "cx": (s.TWR_N >= 2).astype(int)}).groupby(["i", "j"]).agg(n=("cx", "size"),
                                                                                                n_complex=("cx", "sum"))
D = pd.concat([lcc, land], axis=1).join(cnt).fillna({"n": 0, "n_complex": 0}).reset_index()
D["stony"] = [blk[i, j] if i < H2 and j < W2 else np.nan for i, j in zip(D.i, D.j)]
D = D[(D.land_m2 > 0.5 * cs * cs) & D.stony.notna()]
D["dens"] = D.n / (D.land_m2 / 1e6)
D["dens_cx"] = D.n_complex / (D.land_m2 / 1e6)


def partial_spearman(y, x, z):
    ry, rx, rz = (stats.rankdata(v) for v in (y, x, z))
    ey = ry - np.polyval(np.polyfit(rz, ry, 1), rz)
    ex = rx - np.polyval(np.polyfit(rz, rx, 1), rz)
    return stats.pearsonr(ey, ex)


r0 = stats.spearmanr(D.dens, D.stony)
r1 = partial_spearman(D.dens.to_numpy(), D.stony.to_numpy(), D.lcc.to_numpy())
r2 = partial_spearman(D.dens_cx.to_numpy(), D.stony.to_numpy(), D.lcc.to_numpy())
D.to_csv(f"{CD}/v_density_stone_cells.csv", index=False)
add("V_density_stone", "Q05", "Spearman rho, nuraghe density vs outcrop share (about 5 km cells: 166 x 30 m)",
    f"rho {r0.statistic:.2f} (p {r0.pvalue:.1g}); partial (land capability held) {r1.statistic:.2f} (p {r1.pvalue:.1g}); "
    f"complex nuraghi partial {r2.statistic:.2f} (p {r2.pvalue:.1g}); {len(D)} cells",
    "density rises with stoniness (hypothesis)", "Araque Gonzalez 2021: 194-195 (OPINION)",
    "supported" if r1.statistic > 0 and r1.pvalue < 0.05 else "not supported",
    "stoniness proxy = share of the cell on mapped allowed-stone outcrop (hybrid raster), not surface stoniness; "
    "soil = area-weighted dominant land-capability class (Aru et al. 1991)")

# per-seed part files: builders, days, own man-hours, start/finish (checks 6-8, 10)
rows = []
for f in sorted(glob.glob(os.path.join(PARTS, "seed_*.sites.csv.gz"))):
    p = pd.read_csv(f, usecols=["seed", "gid", "TWR_N", "mh_own", "mh_total", "builders", "days", "start_day",
                                "finish_day"])
    rows.append(p)
P = pd.concat(rows)
del rows
P["years40"] = P.days / 40.0
uid = s.UID.to_numpy()      # summary rows are in site (gid) order
assert len(uid) == P.gid.max() + 1

# 6 V_duration (R01, R02)
t1 = P[P.TWR_N == 1].years40
tc = P[P.TWR_N >= 2].years40
add("V_duration", "R01", "single towers: build span in 40-day years (all sites, 100 seeds)",
    f"median {t1.median():.1f}, mean {t1.mean():.1f} (10-90%: {t1.quantile(.1):.1f}-{t1.quantile(.9):.1f})",
    "about 3 years (Borore labour pool, 40 days a year)", "Webster 1991: 853",
    "consistent" if 1.5 <= t1.median() <= 6 else ("model slower" if t1.median() > 6 else "model faster"),
    "model work party = 0.5 x residents (3-20 for single towers); Webster's pool is the Borore group")
add("V_duration", "R01", "complexes (TWR_N >= 2): build span in 40-day years",
    f"median {tc.median():.1f}, mean {tc.mean():.1f} (10-90%: {tc.quantile(.1):.1f}-{tc.quantile(.9):.1f})",
    "4-5 years for the Porcarzos additions (80 men x 40 days)", "Webster 1991: 853",
    "consistent" if 2 <= tc.median() <= 10 else ("model slower" if tc.median() > 10 else "model faster"))
add("V_duration", "R02", "single towers / complexes in 40-day years vs 12 and 25-30 years",
    f"{t1.median():.1f} / {tc.median():.1f}", "12 years (single), 25-30 years (complexes)",
    "attributed to Webster by Atzeni & Frau 2023: 326 (REPORTED-ONLY; not found in Webster 1991)",
    "model faster" if t1.median() < 12 else "consistent")
pd.DataFrame({"group": ["single", "complex"], "median_years40": [t1.median(), tc.median()],
              "mean_years40": [t1.mean(), tc.mean()]}).to_csv(f"{CD}/v_duration.csv", index=False)

# 7 V_labour_share (R03): days per adult male per year over the island span
span_days = P.groupby("seed").finish_day.max() + 1
span_y = span_days / SD                                              # island years (90-day seasons = calendar years)
P = P.join(span_y.rename("span_y"), on="seed")
P["adult_m"] = P.builders / 2.0                                      # residents = 2 x builders; adult men = residents / 4
P["days_pm_y"] = (P.mh_own / 8.0) / P.adult_m / P.span_y
P["days_pm_build"] = (P.mh_own / 8.0) / P.adult_m / np.maximum(P.days / SD, 1.0 / SD)
sh_life = (P.mh_own.sum() / 8.0) / (P.adult_m * P.span_y).sum() / 365.0
lab = P.days_pm_y.median()
add("V_labour_share", "R03", "own labour per adult man, days a year over the island span (median site)",
    f"{lab:.1f} days a year; island-wide {100 * sh_life:.2f}% of adult male time",
    "about 9.5 days a year, 2.5% of adult male time", "Webster 1991: 853",
    "consistent" if 0.5 * 9.5 <= lab <= 2 * 9.5 else ("model lower" if lab < 4.75 else "model higher"),
    "adult men = builders / 2 (builders = 0.5 x residents of both sexes; men = half the adults); 365 days a year; "
    f"during its own build a community's party works the full 90-day season ({100 * 90 / 365:.1f}% of the year)")

# 8 V_concurrency (R04)
act = P.groupby("seed").apply(lambda d: d.days.sum() / (d.finish_day.max() + 1), include_groups=False)
wf = P.groupby("seed").apply(lambda d: (d.days * d.builders).sum() / (d.finish_day.max() + 1), include_groups=False)
add("V_concurrency", "R04", "time-average sites under construction and their work parties (P10)",
    f"{act.mean():,.0f} sites, {wf.mean():,.0f} builders (100 seeds; {act.min():,.0f}-{act.max():,.0f} sites)",
    "about 208 sites and 4,160 people", "Atzeni & Frau 2023: 326-327 (calculation, non-specialist)",
    "consistent" if 0.5 * 208 <= act.mean() <= 2 * 208 else ("model more concurrent" if act.mean() > 416 else
                                                              "model less concurrent"),
    "their figure assumes 8,000 nuraghi over 600 years; a P10 cohort starts ~717 sites at once")

# 9 V_span (R05)
p10, p20, p100 = (v11.loc[k_, "years_mean"] for k_ in ("MOST_REALISTIC_P10", "MOST_REALISTIC_P20", "MOST_REALISTIC_P100"))
add("V_span", "R05", "island years: P10 / P20 / all at once (P100)", f"{p10:.1f} / {p20:.1f} / {p100:.1f}",
    "700 years (c. 1600-900 BC); ~500 years", "Ugas via Moravetti et al. 2009: 361 (REPORTED-ONLY); Ialongo 2018 (NUR 116)",
    "model shorter" if p10 < 500 else "consistent",
    "the model measures labour-limited time; a longer historical span means building was not labour-limited "
    "(demand, population growth: see S22_demog)")

# 10 V_unfinished (R07): slow sites and lintel feasibility
g_ = P.groupby("gid").agg(years40=("years40", "mean"), builders=("builders", "mean"))
g_["UID"] = uid[g_.index]
g_ = g_.merge(s[["UID", "NAME", "COMUNE", "TWR_N", "x", "y", "haul_m"]], on="UID")
crew3 = int(np.ceil(3000 / (30 / 0.38)))
g_["slow"] = g_.years40 > 25
g_["lintel_alone_infeasible"] = g_.builders < crew3
g_["pct_rank_years"] = g_.years40.rank(pct=True)
g_.to_csv(f"{CD}/v_unfinished_sites.csv", index=False)
known = {"NID0091000": "Mura Era I (Sindia)", "NID1470000": "Portazo (Sedilo)"}
kn = g_[g_.UID.isin(known)]
txt = "; ".join(f"{known[r.UID]}: {r.years40:.1f} y, percentile {100 * r.pct_rank_years:.0f}, party {r.builders:.0f}"
                for r in kn.itertuples())
add("V_unfinished", "R07", "sites slower than 25 (40-day) years; lintel (3 t) beyond the own party; the two named sites",
    f"{int(g_.slow.sum())} slow sites; {int(g_.lintel_alone_infeasible.sum())} parties below {crew3} haulers; {txt}",
    "unfinished nuraghi (only the first ring course and the lintel laid): Mura Era I, Portazo",
    "Atzeni, A. 2019: 92 (field observation + interpretation)",
    "consistent" if (kn.pct_rank_years >= 0.5).all() and len(kn) == 2 else "not supported",
    f"lintel crew = ceil(3,000 kg / 78.9 kg) = {crew3} on dry ground (pull 30 kgf / mu 0.38)")
pd.DataFrame(res).to_csv(f"{CD}/checks_v12.csv", index=False)
print(pd.DataFrame(res)[["check", "model", "verdict"]].to_string())
