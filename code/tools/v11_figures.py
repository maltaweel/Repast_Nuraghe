"""v11 figure: change of every rerun scenario, v11 vs v10 (island man-hours and island years, % of the v10 mean).
  python tools/v11_figures.py V11_RUNS_CSV OUT_DIR   -> f_v11_change.png
One series per panel (a single neutral-blue mark; identity is the row label), zero line, recessive grid."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 8, "axes.edgecolor": "#8a8986",
                     "axes.linewidth": 0.6, "xtick.color": "#52514e", "ytick.color": "#52514e", "axes.labelcolor": "#2b2b2a",
                     "axes.spines.top": False, "axes.spines.right": False, "grid.color": "#e4e3df", "grid.linewidth": 0.5,
                     "savefig.dpi": 200})
r = pd.read_csv(sys.argv[1])
r = r[(r.status == "v11 rerun") & r.pct_mh_v11_vs_v10.notna()].sort_values(["pct_mh_v11_vs_v10", "label"])
n = len(r)
y = np.arange(n)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 0.12 * n + 1.2), sharey=True, gridspec_kw={"wspace": 0.06})
a1.barh(y, r.pct_mh_v11_vs_v10, height=0.7, color="#2a78d6")
a2.barh(y, r.pct_years_v11_vs_v10, height=0.7, color="#2a78d6")
a1.set_yticks(y)
a1.set_yticklabels([s.replace("MOST_REALISTIC_", "MR_") for s in r.label], fontsize=4.6)
a1.set_ylim(-0.7, n - 0.3)
for ax in (a1, a2):
    ax.axvline(0, color="#8a8986", lw=0.8)
    ax.grid(True, axis="x")
a1.set_xlabel("island man-hours, % change v11 vs v10")
a2.set_xlabel("island years, % change v11 vs v10\n(P10/P20 twins: v10 had 10 seeds, v11 100)")
os.makedirs(sys.argv[2], exist_ok=True)
fig.savefig(os.path.join(sys.argv[2], "f_v11_change.png"), bbox_inches="tight", facecolor="white")
print("wrote f_v11_change.png", n, "rows")
