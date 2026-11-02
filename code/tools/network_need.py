"""Network need: do nuraghi NEED outside help? (specified by the authors).

  python tools/network_need.py --root OUT/scenarios_alliance --pairs MOST_REALISTIC_P10:MOST_REALISTIC_alone_P10 \
         MOST_REALISTIC_P20:MOST_REALISTIC_alone_P20 MOST_REALISTIC_P100:MOST_REALISTIC_alone_P100 \
         A3_trust_learning:A0_alone --out OUT/network_need

Each pair is NET:ALONE, two alliance runs with the SAME technical rules, work party draw and seeds; ALONE is the
A0-equivalent (no requests, no trust: every community builds with its own people only). The comparison is per
(seed, site), joined on UID, so a site's own-crew-only time is SIMULATED, not estimated. A second, labour-only
estimate is reported as a check: own_est_days = the NET run's site labour / (builders x 8 h) (the builders are never
idle in the labour model; ignores chain waits).

Per tower class (TWR_N) and overall, means over seeds:
  share_received   sum of labour received from other communities / sum of site labour (NET)
  net_years        site's own build span in NET (days / 90): mean, median
  alone_years      the same site's span in ALONE: mean, median
  pct_alone_gt25   % of sites whose ALONE span exceeds 25 years (2,250 days)
  pct_cut_gt50     % of sites where NET span < 0.5 x ALONE span (the network halves the time)
  work_party       mean builders (the per-nuraghe work party)
Writes <out>/network_need_by_towers.csv, network_need_sites.csv.gz (per seed and site) and network_need.txt.
"""
import argparse
import os

import numpy as np
import pandas as pd

H, SD = 8.0, 90.0
COLS = ["seed", "UID", "TWR_N", "mh_total", "mh_own", "mh_received", "builders", "days"]


def load(roots, name):
    for root in roots[::-1]:                              # the last root that has it
        f = os.path.join(root, name, "nuraghe_manhours_runs.csv.gz")
        if os.path.exists(f):
            return pd.read_csv(f, usecols=COLS)
    raise SystemExit(f"{name}: not found under {roots}")


def summarise(d, label):
    rows = []
    for tw, g in list(d.groupby("TWR_N")) + [("all", d)]:
        per_seed = []
        for s, x in g.groupby("seed"):
            per_seed.append({
                "share_received": x.mh_received.sum() / x.mh_total.sum(),
                "net_years_mean": (x.days / SD).mean(), "net_years_median": (x.days / SD).median(),
                "alone_years_mean": (x.days_alone / SD).mean(), "alone_years_median": (x.days_alone / SD).median(),
                "own_est_years_mean": (x.own_est_days / SD).mean(),
                "pct_alone_gt25": 100.0 * (x.days_alone / SD > 25).mean(),
                "pct_cut_gt50": 100.0 * (x.days < 0.5 * x.days_alone).mean(),
                "work_party": x.builders.mean()})
        r = pd.DataFrame(per_seed).mean().to_dict()
        r.update({"pair": label, "TWR_N": tw, "n_sites": int(g.UID.nunique()), "n_seeds": int(g.seed.nunique())})
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", nargs="+", required=True, help="scenarios_alliance output root(s); later roots win")
    ap.add_argument("--pairs", nargs="+", required=True, help="NET:ALONE scenario names")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    allrows, sites = [], []
    for p in a.pairs:
        net, alone = p.split(":")
        n, z = load(a.root, net), load(a.root, alone)
        z = z[["seed", "UID", "days", "builders"]].rename(columns={"days": "days_alone", "builders": "builders_alone"})
        d = n.merge(z, on=["seed", "UID"], how="inner", validate="one_to_one")
        assert len(d) == len(n), f"{p}: site/seed sets differ"
        assert (d.builders == d.builders_alone).all(), f"{p}: work parties differ (not the same draw)"
        d["own_est_days"] = d.mh_total / (d.builders * H)
        label = f"{net} vs {alone}"
        allrows += summarise(d, label)
        d["pair"] = label
        sites.append(d)
    t = pd.DataFrame(allrows)
    cols = ["pair", "TWR_N", "n_sites", "n_seeds", "work_party", "share_received", "net_years_mean", "net_years_median",
            "alone_years_mean", "alone_years_median", "own_est_years_mean", "pct_alone_gt25", "pct_cut_gt50"]
    t = t[cols]
    t.to_csv(os.path.join(a.out, "network_need_by_towers.csv"), index=False)
    pd.concat(sites).to_csv(os.path.join(a.out, "network_need_sites.csv.gz"), index=False, compression="gzip")
    with open(os.path.join(a.out, "network_need.txt"), "w") as fh:
        with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", "{:,.3f}".format):
            fh.write(t.to_string(index=False) + "\n")
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", "{:,.3f}".format):
        print(t.to_string(index=False))


if __name__ == "__main__":
    main()
