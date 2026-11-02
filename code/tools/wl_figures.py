"""Figures for the wider-literature chapter (C1-C3, M1-M4), from tools/wl_summary.py outputs.

  python tools/wl_figures.py SUMMARY_DIR CALIB_CSV OUT_DIR

f_wl_compare.png  every variant vs MOST_REALISTIC_P10: island years to the last nuraghe (dot = mean over 100 seeds, bar =
                  min-max over seeds) and island man-hours (% change of the means; bar = min-max of the same-seed change).
                  Colour = family, every row labelled.
f_wl_stages.png   man-hours by stage (quarry, dressing, transport, walling, lift, other) per variant, million.
f_wl_calib.png    calibration: our rates vs Harris / Erasmus / Boswinkel per stage, common units (calibration CSV).
Palette: the reference categorical order (dataviz validate_palette.js, 8 slots, light mode: all checks pass; contrast WARN
for aqua / yellow / magenta -> every mark is directly labelled and every number is in the report tables).
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
    "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.edgecolor": "#8a8986", "axes.linewidth": 0.6, "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.labelcolor": "#2b2b2a", "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": "#e4e3df", "grid.linewidth": 0.5, "savefig.dpi": 220, "figure.dpi": 100,
})
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
NEUTRAL = "#8a8986"
INK = "#2b2b2a"
REF = "MOST_REALISTIC_P10"
FAM = {"C1": 0, "C2": 1, "C3": 2, "M1": 3, "M2": 4, "M3": 5, "M4": 6}
FAMNAME = {"C1": "C1 Harris sledge", "C2": "C2 Erasmus rates", "C3": "C3 Mycenaean costings", "M1": "M1 emulation",
           "M2": "M2 master masons", "M3": "M3 wetted sand", "M4": "M4 walked blocks"}


def short(n):
    return n.replace("MOST_REALISTIC_", "").replace("_P10", "")


def main(sd, calib, od):
    s = pd.read_csv(os.path.join(sd, "wl_summary.csv"))
    os.makedirs(od, exist_ok=True)
    ref = s[s.scenario == REF].iloc[0]
    v = s[s.scenario != REF].copy()
    v["fam"] = v.scenario.map(lambda n: short(n)[:2])
    n = len(v)
    y = np.arange(n)[::-1]
    # ---------------------------------------------------------------- compare
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 0.25 * n + 1.4), sharey=True, gridspec_kw={"wspace": 0.08})
    for ax in (a1, a2):
        ax.grid(True, axis="x")
    a1.axvline(ref.years_max_mean, color=NEUTRAL, lw=1.0, ls="--", zorder=1)
    a1.text(ref.years_max_mean, n - 0.3, f" MR_P10 {ref.years_max_mean:,.1f} yr", color=INK, fontsize=7, va="bottom")
    a2.axvline(0, color=NEUTRAL, lw=1.0, ls="--", zorder=1)
    for yy, r in zip(y, v.itertuples()):
        c = CAT[FAM[r.fam]]
        a1.plot([r.years_max_min, r.years_max_max], [yy, yy], color=c, lw=2, solid_capstyle="round", zorder=2)
        a1.scatter(r.years_max_mean, yy, s=36, color=c, edgecolors="white", lw=1.0, zorder=3)
        a2.plot([r.island_mh_pct_paired_min, r.island_mh_pct_paired_max], [yy, yy], color=c, lw=2,
                solid_capstyle="round", zorder=2)
        a2.scatter(r.island_mh_pct_vs_ref, yy, s=36, color=c, edgecolors="white", lw=1.0, zorder=3)
    a1.set_yticks(y); a1.set_yticklabels([short(n_) for n_ in v.scenario], fontsize=7.5)
    a1.set_ylim(-0.7, n - 0.1)
    a1.set_xlabel("island years to the last nuraghe")
    a2.set_xlabel("island man-hours, % change vs MR_P10")
    for f_, k in FAM.items():
        a1.scatter([], [], s=36, color=CAT[k], label=FAMNAME[f_])
    a1.legend(*a1.get_legend_handles_labels(), frameon=False, ncol=4, fontsize=7.0, loc="lower left",
              bbox_to_anchor=(0.0, 1.01), borderaxespad=0.2)
    fig.savefig(os.path.join(od, "f_wl_compare.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    # ---------------------------------------------------------------- stages
    st = [("mh_quarry_mean", "quarry (+ face set-up)"), ("mh_dress_mean", "dressing"), ("mh_transport_mean", "transport"),
          ("mh_build_mean", "walling"), ("mh_lift_mean", "lift"), ("other", "walking to help, tracks")]
    w = s.copy()
    w["mh_quarry_mean"] = w.mh_quarry_mean + w.mh_setup_mean
    w["other"] = w.island_mh_mean - sum(w[c] for c, _ in st[:-1])
    w = pd.concat([w[w.scenario == REF], w[w.scenario != REF]])
    yy = np.arange(len(w))[::-1]
    fig, ax = plt.subplots(figsize=(7.4, 0.25 * len(w) + 1.4))
    left = np.zeros(len(w))
    stc = [CAT[0], CAT[1], CAT[2], CAT[3], CAT[4], NEUTRAL]
    for (c, lab), col in zip(st, stc):
        val = w[c].to_numpy() / 1e6
        ax.barh(yy, val, left=left, height=0.72, color=col, edgecolor="white", lw=1.0, label=lab)
        left += val
    for y0, t in zip(yy, left):
        ax.text(t + 2, y0, f"{t:,.0f}", va="center", fontsize=6.8, color=INK)
    ax.set_yticks(yy); ax.set_yticklabels(["MR_P10" if n_ == REF else short(n_) for n_ in w.scenario], fontsize=7.5)
    ax.set_ylim(-0.7, len(w) - 0.3)
    ax.axvline(w.island_mh_mean.iloc[0] / 1e6, color=NEUTRAL, lw=0.8, ls="--")
    ax.set_xlabel("island man-hours by stage, million (mean over 100 seeds)")
    ax.grid(True, axis="x")
    ax.legend(frameon=False, ncol=3, fontsize=7.0, loc="lower left", bbox_to_anchor=(0.0, 1.01))
    fig.savefig(os.path.join(od, "f_wl_stages.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    # ---------------------------------------------------------------- calibration
    c = pd.read_csv(calib)
    c = c[c["plot"] == 1]
    groups = list(dict.fromkeys(c.group))
    fig, axs = plt.subplots(len(groups), 1, figsize=(7.4, 1.0 + 0.24 * len(c) + 0.25 * len(groups)),
                            gridspec_kw={"height_ratios": [max(1, (c.group == g).sum()) for g in groups]})
    src_col = {"this model": CAT[0], "Harris 2016": CAT[1], "Erasmus 1965": CAT[2], "Boswinkel 2021": CAT[6],
               "Webster 1991": CAT[3]}
    for ax, g in zip(np.atleast_1d(axs), groups):
        d = c[c.group == g].iloc[::-1]
        yy = np.arange(len(d))
        for y0, r in zip(yy, d.itertuples()):
            col = src_col.get(r.source, NEUTRAL)
            if np.isfinite(r.lo) and np.isfinite(r.hi) and r.hi > r.lo:
                ax.plot([r.lo, r.hi], [y0, y0], color=col, lw=2.2, solid_capstyle="round")
            ax.scatter([r.value], [y0], s=34, color=col, edgecolors="white", lw=1.0, zorder=3)
            ax.text(max(r.value, r.hi if np.isfinite(r.hi) else r.value) * 1.08, y0, f"{r.value:,.3g}",
                    va="center", fontsize=6.6, color=INK)
        ax.set_yticks(yy); ax.set_yticklabels(d.label, fontsize=7)
        ax.set_xscale("log")
        ax.set_title(g, loc="left", fontsize=8.2)
        ax.grid(True, axis="x")
        ax.set_ylim(-0.6, len(d) - 0.4)
        ax.xaxis.set_major_locator(matplotlib.ticker.LogLocator(subs=(1.0, 2.0, 5.0)))
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.3g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        lo_, hi_ = ax.get_xlim()
        ax.set_xlim(lo_ / 1.15, hi_ * 1.6)
    for k, col in src_col.items():
        np.atleast_1d(axs)[0].scatter([], [], s=34, color=col, label=k)
    np.atleast_1d(axs)[0].legend(frameon=False, ncol=5, fontsize=7, loc="lower left", bbox_to_anchor=(0, 1.25))
    fig.tight_layout()
    fig.savefig(os.path.join(od, "f_wl_calib.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote f_wl_compare.png, f_wl_stages.png, f_wl_calib.png in", od)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
