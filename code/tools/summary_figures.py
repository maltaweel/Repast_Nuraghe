"""Figures of the executive summary (1 Nov (b) edition; v11: reads all_scenarios_v11.csv, pull125 in the MR group), from outputs/summary_all/all_scenarios_ranked.csv.

  python tools/summary_figures.py RANKED_CSV OUT_DIR

f_all_rating.png  every current scenario (superseded runs excluded) ranked by realism: y = overall rating (min of rule
                  and schedule rating; jittered), x = island man-hours (left) and island years (right, log; filled =
                  10% phasing simulated, open = all at once / own schedule). Colour = family.
f_all_p10.png     the scenarios on the MR_P10 schedule (10% phasing simulated, 90-day seasons): island years vs island
                  man-hours, log-log; marker size = overall rating; MR_P10 labelled.
f_all_delta.png   the 51 scenarios built on MOST_REALISTIC (MR variants, S10-S14, C1-M4): % change of island years and
                  man-hours vs MR_P10, ranked by realism (years clipped at +100%, true value printed).
Palette: the reference categorical order (dataviz validate_palette.js, 8 slots, light: all checks pass; contrast WARN ->
every family is in the legend and every number is in the tables); the ninth group (wider literature) is ink, drawn with
a distinct marker.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 9, "axes.titlesize": 9.5,
    "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 7.5,
    "axes.edgecolor": "#8a8986", "axes.linewidth": 0.6, "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.labelcolor": "#2b2b2a", "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": "#e4e3df", "grid.linewidth": 0.5, "savefig.dpi": 220, "figure.dpi": 100,
})
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, NEUTRAL = "#2b2b2a", "#8a8986"
GROUPS = [("Literature (chaîne opératoire)", ("Literature",)),
          ("Cooperation, baseline, TOST", ("Cooperation", "Baseline", "TOST")),
          ("Alliance (+ sensitivity)", ("Alliance",)),
          ("Pre-existing networks", ("Pre-existing",)),
          ("Sea access S9", ("Sea access",)),
          ("Phasing P10/P20 twins", ("Phasing",)),
          ("MOST_REALISTIC (+ v11 pull125)", ("MOST_REALISTIC", "Season", "v11 sensitivity")),
          ("S10–S14 (1 Nov)", ("S10-S14",)),
          ("C1–M4 wider literature", ("Wider literature",))]


def group(f):
    for k, (name, keys) in enumerate(GROUPS):
        if any(f.startswith(x) for x in keys):
            return k
    raise KeyError(f)


def style(k):
    return (CAT[k], "o") if k < 8 else (INK, "D")


def main(p, od):
    a = pd.read_csv(p)
    a = a[a.superseded.astype(int) == 0].copy()
    a["g"] = a.family.map(group)
    os.makedirs(od, exist_ok=True)
    rng = np.random.default_rng(7)
    a["yj"] = a.rating_overall + rng.uniform(-0.28, 0.28, len(a))
    p10 = a.schedule.fillna("").str.match(r"P10(?!0)")
    # ---------------------------------------------------------------- ranking by rating
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 4.4), sharey=True, gridspec_kw={"wspace": 0.06})
    for k in range(len(GROUPS)):
        d = a[a.g == k]
        c, m = style(k)
        ax1.scatter(d.mh_M_mean, d.yj, s=16, color=c, marker=m, edgecolors="white", lw=0.4, alpha=0.9,
                    label=GROUPS[k][0])
        dd = d[d.years_mean.notna()]
        f = p10.reindex(dd.index)
        ax2.scatter(dd.years_mean[f], dd.yj[f], s=16, color=c, marker=m, edgecolors="white", lw=0.4, alpha=0.9)
        ax2.scatter(dd.years_mean[~f], dd.yj[~f], s=16, facecolors="none", edgecolors=c, marker=m, lw=0.8, alpha=0.9)
    mr = a[a.scenario == "MOST_REALISTIC_P10"].iloc[0]
    for ax, x in ((ax1, mr.mh_M_mean), (ax2, mr.years_mean)):
        ax.axvline(x, color=NEUTRAL, lw=0.8, ls="--")
        ax.grid(True, axis="x")
    ax1.text(mr.mh_M_mean, 5.45, " MR_P10", fontsize=7, color=INK)
    ax1.set_xscale("log"); ax2.set_xscale("log")
    for ax in (ax1, ax2):
        ax.xaxis.set_major_locator(matplotlib.ticker.LogLocator(subs=(1.0, 3.0)))
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax1.set_yticks([1, 2, 3, 4, 5]); ax1.set_ylim(0.5, 5.6)
    ax1.set_ylabel("realism rating (overall; judgement)")
    ax1.set_xlabel("island man-hours, million (log)")
    ax2.set_xlabel("island years (log; open = all at once / own schedule)")
    ax1.legend(frameon=False, ncol=3, fontsize=6.8, loc="lower left", bbox_to_anchor=(0.0, 1.01), markerscale=1.4)
    fig.savefig(os.path.join(od, "f_all_rating.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    # ---------------------------------------------------------------- P10 schedule scatter
    b = a[p10 & a.years_mean.notna()]
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    for k in sorted(b.g.unique()):
        d = b[b.g == k]
        c, m = style(k)
        ax.scatter(d.years_mean, d.mh_M_mean, s=8 + 9 * d.rating_overall ** 1.6, color=c, marker=m,
                   edgecolors="white", lw=0.6, alpha=0.85, label=GROUPS[k][0])
    ax.scatter([mr.years_mean], [mr.mh_M_mean], s=120, facecolors="none", edgecolors=INK, lw=1.2)
    ax.annotate("MR_P10", (mr.years_mean, mr.mh_M_mean), xytext=(8, 8), textcoords="offset points", fontsize=7.5)
    ax.set_xscale("log"); ax.set_yscale("log")
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xticks([30, 100, 300, 1000, 3000]); ax.set_yticks([250, 300, 400, 500])
    ax.set_xlabel("island years to the last nuraghe (log)")
    ax.set_ylabel("island man-hours, million (log)")
    ax.grid(True)
    h, l_ = ax.get_legend_handles_labels()
    for s_ in (1, 3, 5):
        h.append(ax.scatter([], [], s=8 + 9 * s_ ** 1.6, color=NEUTRAL)); l_.append(f"rating {s_}")
    ax.legend(h, l_, frameon=False, fontsize=6.8, ncol=4, loc="lower left", bbox_to_anchor=(0, 1.01))
    fig.savefig(os.path.join(od, "f_all_p10.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    # ---------------------------------------------------------------- deltas of the MR-based scenarios
    fams = ("MOST_REALISTIC", "S10-S14", "Wider literature", "v11 sensitivity")
    c_ = a[a.family.map(lambda f: any(f.startswith(x) for x in fams)) & p10 & (a.scenario != "MOST_REALISTIC_P10")]
    c_ = c_.sort_values(["rating_overall", "pct_mh_vs_MR_P10"], ascending=[False, True])
    n = len(c_)
    y = np.arange(n)[::-1]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 0.17 * n + 1.3), sharey=True, gridspec_kw={"wspace": 0.06})
    for yy, r in zip(y, c_.itertuples()):
        col, m = style(r.g)
        yv = min(r.pct_years_vs_MR_P10, 100.0)
        a1.barh(yy, yv, height=0.7, color=col)
        if r.pct_years_vs_MR_P10 > 100:
            a1.text(100, yy, f" {r.pct_years_vs_MR_P10:+,.0f}%", va="center", fontsize=5.8, color=INK)
        a2.barh(yy, r.pct_mh_vs_MR_P10, height=0.7, color=col)
    lab = [f"{r.scenario.replace('MOST_REALISTIC_', 'MR_' if r.g == 6 else '').replace('_P10', '')} [{r.rating_overall}]"
           for r in c_.itertuples()]
    a1.set_yticks(y); a1.set_yticklabels(lab, fontsize=5.8)
    a1.set_ylim(-0.7, n - 0.3)
    for ax in (a1, a2):
        ax.axvline(0, color=NEUTRAL, lw=0.8)
        ax.grid(True, axis="x")
    a1.set_xlim(-60, 140)
    a1.set_xlabel("island years, % change vs MR_P10 (clipped at +100%)")
    a2.set_xlabel("island man-hours, % change vs MR_P10")
    from matplotlib.patches import Patch
    a1.legend(handles=[Patch(color=style(k)[0], label=GROUPS[k][0]) for k in sorted(c_.g.unique())],
              frameon=False, ncol=3, fontsize=6.8, loc="lower left", bbox_to_anchor=(0, 1.005))
    fig.savefig(os.path.join(od, "f_all_delta.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote f_all_rating.png, f_all_p10.png, f_all_delta.png in", od)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
