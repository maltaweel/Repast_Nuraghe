"""Figures for the S10-S14 report section, from tools/gaps_summary.py outputs.

  python tools/gaps_figures.py SUMMARY_DIR OUT_DIR

f_gaps_compare.png  every variant vs MOST_REALISTIC_P10: island years to the last nuraghe (log scale; dot = mean over
                    seeds, bar = min-max over seeds) and island man-hours (% change vs MR_P10, mean; bar = min-max of
                    the paired same-seed change). Colour = scenario family, every row labelled.
f_gaps_params.png   parameter effects: S10 staged share, S11 volume factor, S12 surplus / ration, S13 extra stone,
                    S14 repair labour (build period simulated + occupation span post hoc).
Palette: the report's categorical order (validated: dataviz validate_palette.js, light mode, all checks pass; contrast
WARN -> every mark is directly labelled and the numbers are in the report tables).
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
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
NEUTRAL = "#8a8986"
INK = "#2b2b2a"
REF = "MOST_REALISTIC_P10"
FAM = {"S10": 0, "S11": 1, "S12": 2, "S13": 3, "S14": 4}
FAMNAME = {"S10": "S10 staged complexes", "S11": "S11 protonuraghi first", "S12": "S12 food-limited crews",
           "S13": "S13 antemurali + villages", "S14": "S14 maintenance"}


def short(n):
    return n.replace("MOST_REALISTIC_", "").replace("_P10", "")


def main(sd, od):
    s = pd.read_csv(os.path.join(sd, "gaps_summary.csv"))
    by = pd.read_csv(os.path.join(sd, "gaps_by_seed.csv"))
    os.makedirs(od, exist_ok=True)
    ref = s[s.scenario == REF].iloc[0]
    v = s[s.scenario != REF].copy()
    v["fam"] = v.scenario.map(lambda n: short(n)[:3])
    v = v.sort_values(["fam", "scenario"], key=lambda c: c if c.name == "fam" else c.map(lambda n: list(s.scenario).index(n)))
    # ---------------------------------------------------------------- figure 1
    n = len(v)
    y = np.arange(n)[::-1]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 0.26 * n + 1.3), sharey=True, gridspec_kw={"wspace": 0.08})
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
    a1.set_xscale("log")
    a1.set_xticks([250, 500, 1000, 2000, 5000])
    a1.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    a1.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    a1.set_yticks(y); a1.set_yticklabels([short(n_) for n_ in v.scenario], fontsize=7.5)
    a1.set_ylim(-0.7, n - 0.1)
    a1.set_xlabel("island years to the last nuraghe (log scale)")
    a2.set_xlabel("island man-hours, % change vs MR_P10")
    for f_, k in FAM.items():
        a1.scatter([], [], s=36, color=CAT[k], label=FAMNAME[f_])
    a1.legend(*a1.get_legend_handles_labels(), frameon=False, ncol=3, fontsize=7.2, loc="lower left",
              bbox_to_anchor=(0.0, 1.01), borderaxespad=0.2)
    fig.savefig(os.path.join(od, "f_gaps_compare.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    # ---------------------------------------------------------------- figure 2
    S = s.set_index("scenario")
    fig, axs = plt.subplots(2, 3, figsize=(7.4, 5.0))
    ax = axs[0, 0]                                        # S10 staged share -> years
    pts = [(0.0, "MOST_REALISTIC_S10_unitary_P10"), (0.5, "MOST_REALISTIC_S10_half_P10"),
           (0.7, "MOST_REALISTIC_S10_s70_P10"), (1.0, "MOST_REALISTIC_S10_all_P10")]
    pts = [(x, k) for x, k in pts if k in S.index]
    if pts:
        x_ = [p[0] for p in pts]; m = [S.loc[p[1], "years_max_mean"] for p in pts]
        ax.fill_between(x_, [S.loc[p[1], "years_max_p5"] for p in pts], [S.loc[p[1], "years_max_p95"] for p in pts],
                        color=CAT[0], alpha=0.15, lw=0)
        ax.plot(x_, m, color=CAT[0], lw=2, marker="o", ms=5, mec="white")
        if "MOST_REALISTIC_S10_all_crew50_P10" in S.index:
            ax.scatter([1.0], [S.loc["MOST_REALISTIC_S10_all_crew50_P10", "years_max_mean"]], s=36, facecolors="white",
                       edgecolors=CAT[0], lw=1.4, zorder=3)
            ax.annotate("additions by\nhalf parties", (1.0, S.loc["MOST_REALISTIC_S10_all_crew50_P10", "years_max_mean"]),
                        xytext=(0, 14), textcoords="offset points", ha="right", va="bottom", fontsize=6.5, color=INK)
    ax.set_xlabel("share of complexes built in stages"); ax.set_ylabel("island years")
    ax.set_title("S10 staged complexes", loc="left", fontsize=8.5)
    ax = axs[0, 1]                                        # S11 volume factor -> % change
    pts = [(1.0, "MOST_REALISTIC_S11_order_P10"), (0.835, "MOST_REALISTIC_S11_low_P10"),
           (2.084, "MOST_REALISTIC_S11_mid_P10"), (3.508, "MOST_REALISTIC_S11_high_P10")]
    pts = sorted([(x, k) for x, k in pts if k in S.index])
    if pts:
        x_ = [p[0] for p in pts]
        ax.plot(x_, [S.loc[p[1], "island_mh_pct_vs_ref"] for p in pts], color=CAT[1], lw=2, marker="o", ms=5,
                mec="white", label="man-hours")
        ax.plot(x_, [S.loc[p[1], "years_max_pct_vs_ref"] for p in pts], color=CAT[1], lw=1.2, ls="--", marker="s",
                ms=4, mec="white", label="island years")
        ax.legend(frameon=False, fontsize=6.8)
    ax.axhline(0, color=NEUTRAL, lw=0.8)
    ax.set_xlabel("protonuraghe stone / tower stone"); ax.set_ylabel("% change vs MR_P10")
    ax.set_title("S11 protonuraghi first", loc="left", fontsize=8.5)
    ax = axs[0, 2]                                        # S12 surplus/ration -> years (log)
    pts = [(0.1, "MOST_REALISTIC_S12_s10_P10"), (0.2, "MOST_REALISTIC_S12_central_P10"),
           (0.3, "MOST_REALISTIC_S12_s30_P10")]
    pts = [(x, k) for x, k in pts if k in S.index]
    if pts:
        x_ = [p[0] for p in pts]
        ax.fill_between(x_, [S.loc[p[1], "years_max_p5"] for p in pts], [S.loc[p[1], "years_max_p95"] for p in pts],
                        color=CAT[2], alpha=0.15, lw=0)
        ax.plot(x_, [S.loc[p[1], "years_max_mean"] for p in pts], color=CAT[2], lw=2, marker="o", ms=5, mec="white")
    for k, lab, x0 in (("MOST_REALISTIC_S12_low_P10", "joint low", 0.1 / 1.2), ("MOST_REALISTIC_S12_high_P10",
                                                                              "joint high", 0.3 / 0.9)):
        if k in S.index:
            ax.scatter([x0], [S.loc[k, "years_max_mean"]], s=36, facecolors="white", edgecolors=CAT[2], lw=1.4, zorder=3)
            ax.annotate(lab, (x0, S.loc[k, "years_max_mean"]), xytext=(4, 3), textcoords="offset points", fontsize=6.5)
    ax.axhline(ref.years_max_mean, color=NEUTRAL, lw=0.8, ls="--")
    ax.set_yscale("log")
    ax.set_yticks([300, 1000, 2000, 5000])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlabel("surplus share / ration (kg per worker-day)"); ax.set_ylabel("island years (log)")
    ax.set_title("S12 food-limited crews", loc="left", fontsize=8.5)
    ax = axs[1, 0]                                        # S13 extra stone -> MH %
    ks = [k for k in ("MOST_REALISTIC_S13_walls_P10", "MOST_REALISTIC_S13_walls_village_P10", "MOST_REALISTIC_S13_high_P10")
          if k in S.index]
    if ks:
        x_ = [S.loc[k, "tonnes_extra_mean"] / 1e6 for k in ks]
        ax.plot(x_, [S.loc[k, "island_mh_pct_vs_ref"] for k in ks], color=CAT[3], lw=2, marker="o", ms=5, mec="white",
                label="man-hours")
        ax.plot(x_, [S.loc[k, "years_max_pct_vs_ref"] for k in ks], color=CAT[3], lw=1.2, ls="--", marker="s", ms=4,
                mec="white", label="island years")
        for x0, k in zip(x_, ks):
            ax.annotate(short(k).replace("S13_", ""), (x0, S.loc[k, "island_mh_pct_vs_ref"]), xytext=(3, -9),
                        textcoords="offset points", fontsize=6.5)
        ax.legend(frameon=False, fontsize=6.8)
    ax.set_xlabel("extra stone (million t)"); ax.set_ylabel("% change vs MR_P10")
    ax.set_title("S13 antemurali + villages", loc="left", fontsize=8.5)
    ax = axs[1, 1]                                        # S14 repair labour
    ks = [k for k in ("MOST_REALISTIC_S14_low_P10", "MOST_REALISTIC_S14_central_P10", "MOST_REALISTIC_S14_high_P10")
          if k in S.index]
    if ks:
        x_ = np.arange(len(ks))
        b1 = np.array([S.loc[k, "mh_repair_build_mean"] for k in ks]) / 1e6
        b2 = np.array([S.loc[k, "mh_repair_occupation_mean"] for k in ks]) / 1e6
        ax.bar(x_, b1, width=0.6, color=CAT[4], label="build period (simulated)")
        ax.bar(x_, b2, width=0.6, bottom=b1, color=CAT[4], alpha=0.45, label="occupation span (post hoc)",
               edgecolor="white", lw=1.0)
        ax.axhline(ref.island_mh_mean / 1e6, color=NEUTRAL, lw=0.8, ls="--")
        ax.text(len(ks) - 0.5, ref.island_mh_mean / 1e6, "MR_P10 construction", fontsize=6.5, ha="right", va="bottom")
        ax.set_xticks(x_); ax.set_xticklabels([short(k).replace("S14_", "") for k in ks])
        ax.legend(frameon=False, fontsize=6.5, loc="upper left")
    ax.set_ylabel("repair man-hours (million)")
    ax.set_title("S14 maintenance", loc="left", fontsize=8.5)
    axs[1, 2].axis("off")
    for a in axs.flat:
        a.grid(True, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(od, "f_gaps_params.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", os.path.join(od, "f_gaps_compare.png"), os.path.join(od, "f_gaps_params.png"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
