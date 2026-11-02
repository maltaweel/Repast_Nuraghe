"""Network formation figures (specified by the authors): growth over seasons and connected components,
from tools/formation.py (formation_curves.csv) and tools/components.py (components_by_seed.csv) in one folder.

  python tools/formation_plot.py DIR [--title-suffix TEXT]

Writes DIR/formation_<scenario>.png: helping pairs and ever-allied pairs (mean, 5-95% over seeds), help man-hours per
season, and the largest help network / number of networks at each components cut. The phasing (P10 / P20 / P100) is
part of the scenario name, so it is in every title. Under phasing the curves step up at each new cohort.
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

PH = {"_P10": "phased P10 (10% cohorts)", "_P20": "phased P20 (20% cohorts)", "_P100": "all at once (P100)"}


def phasing_label(n):
    for k, v in PH.items():
        if n.endswith(k):
            return v
    return "native start schedule (1/450 per season)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    a = ap.parse_args()
    cur = pd.read_csv(os.path.join(a.dir, "formation_curves.csv"))
    cp = os.path.join(a.dir, "components_by_seed.csv")
    comp = pd.read_csv(cp) if os.path.exists(cp) else None
    for n, c in cur.groupby("scenario", sort=False):
        fig, ax = plt.subplots(1, 3, figsize=(16, 4.5))
        ax[0].plot(c.season, c.helping_pairs_mean, label="helping pairs (cumulative)")
        ax[0].fill_between(c.season, c.helping_pairs_p05, c.helping_pairs_p95, alpha=0.25)
        ax[0].plot(c.season, c.ever_allied_mean, label="ever-allied pairs (cumulative)")
        ax[0].fill_between(c.season, c.ever_allied_p05, c.ever_allied_p95, alpha=0.25)
        ax[0].set_xlabel("season (year)"); ax[0].set_ylabel("pairs"); ax[0].legend(fontsize=8)
        ax[1].plot(c.season, c.help_mh_mean)
        ax[1].set_xlabel("season (year)"); ax[1].set_ylabel("help man-hours in the season (mean over seeds)")
        if comp is not None and (comp.scenario == n).any():
            d = comp[comp.scenario == n]
            g = d.groupby("upto", sort=False).agg(largest=("largest", "median"), n_networks=("n_networks", "median"))
            x = range(len(g))
            ax[2].bar([i - 0.2 for i in x], g.largest, width=0.4, label="largest network (sites, median)")
            ax[2].bar([i + 0.2 for i in x], g.n_networks, width=0.4, label="number of networks (median)")
            ax[2].set_xticks(list(x)); ax[2].set_xticklabels([f"season <= {u}" if u != "end" else "end" for u in g.index])
            ax[2].legend(fontsize=8)
        fig.suptitle(f"{n}: network formation - {phasing_label(n)}")
        fig.tight_layout()
        fig.savefig(os.path.join(a.dir, f"formation_{n}.png"), dpi=130)
        plt.close(fig)
        print(f"{n}: formation_{n}.png")


if __name__ == "__main__":
    main()
