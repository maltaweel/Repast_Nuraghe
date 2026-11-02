"""Relationship census (a Nurnet collaborator's definitions), recomputed from the v4 pair files with ask/refusal counters.

  python tools/census.py config.yaml [--seeds 1-100]

Population: all unordered pairs of communities <= R (10 km, straight line). Each pair is put, for each seed, in the
highest class it reached over the whole build:
  allied     mutual trust >= the alliance threshold at the end (pair column `allied`)
  reciprocal help flowed both ways (help_ab > 0 and help_ba > 0), not allied
  one-way    help flowed one way only
  refused    at least one request (asks_ab + asks_ba > 0) but no help either way
  ignore     everything else (no request, no help)
Scenario-level columns: asks per seed, refusal rate (% of requests refused), labour received (% of island
man-hours), island man-hours and island completion (seasons), all means over the same seeds.
Writes output/census/relationship_census_v4_seeds<a>-<b>.csv in a Nurnet collaborator's column layout.
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

CLASSES = ["ignore", "refused", "one-way help", "reciprocal", "allied"]


def run_dir(cache, scen):
    dirs = [d for d in glob.glob(os.path.join(cache, "runs", f"alliance_{scen}", "*"))
            if glob.glob(os.path.join(d, "seed_*.pairs.csv.gz"))]
    if not dirs:                                                     # B7: clear error instead of max() of nothing
        raise FileNotFoundError(f"no alliance_{scen} run with pair files under {os.path.join(cache, 'runs')}")
    return max(dirs, key=lambda d: (len(glob.glob(os.path.join(d, "*.done"))), os.path.getmtime(d)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("config"); ap.add_argument("--seeds", default="1-100")
    ap.add_argument("--sites", help="comma-separated UIDs: the same subset the runs used (default: all sites)")
    a = ap.parse_args()
    cfg = load_config(a.config)
    s0, s1 = (int(x) for x in a.seeds.split("-"))
    seeds = list(range(s0, s1 + 1))
    sites = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    sites = sites[sites.haul_flatm.notna()]                          # as model.load_haul
    if a.sites:                                                      # B7: population of the run's own sites
        sites = sites[sites.UID.isin(a.sites.split(","))]
    R = float(cfg["alliance"]["R_m"])
    pop = len(cKDTree(sites[["x", "y"]].to_numpy()).query_pairs(r=R))
    rows = []
    for scen in cfg["alliance"]["list"]:
        rd = run_dir(cfg["paths"]["cache_dir"], scen)
        counts = {c: [] for c in CLASSES}
        asks, refused, rcv, isl, seas = [], [], [], [], []
        for s in seeds:
            p = pd.read_csv(os.path.join(rd, f"seed_{s:04d}.pairs.csv.gz"))
            st = pd.read_csv(os.path.join(rd, f"seed_{s:04d}.sites.csv.gz"))
            if len(st) != len(sites):                                # B7: else `ignore` (= pop - classes) is wrong
                raise ValueError(f"{rd}: the run has {len(st)} sites but the census population has {len(sites)}; "
                                 f"pass the run's --sites")
            if len(p):
                hab, hba = p.help_ab > 0, p.help_ba > 0
                ask = (p.asks_ab + p.asks_ba) > 0
                al = p.allied == 1
                rec = hab & hba & ~al
                one = (hab ^ hba) & ~al
                ref = ask & ~hab & ~hba & ~al
                n = {"allied": int(al.sum()), "reciprocal": int(rec.sum()), "one-way help": int(one.sum()),
                     "refused": int(ref.sum())}
                asks.append(int(p.asks_ab.sum() + p.asks_ba.sum())); refused.append(int(p.refused_ab.sum() + p.refused_ba.sum()))
            else:
                n = {"allied": 0, "reciprocal": 0, "one-way help": 0, "refused": 0}
                asks.append(0); refused.append(0)
            n["ignore"] = pop - sum(n.values())
            for c in CLASSES:
                counts[c].append(n[c])
            rcv.append(st.mh_received.sum()); isl.append(st.mh_total.sum()); seas.append(st.finish_season.max())
        for c in CLASSES:
            m = float(np.mean(counts[c]))
            rows.append({"scenario": scen, "cls": c, "pairs_mean": round(m, 1), "pct_of_pairs": round(100 * m / pop, 4),
                         "pair_population": pop,
                         "population_def": f"unordered pairs of communities <= {R / 1000:g} km apart (straight line)",
                         "seeds": f"{s0}-{s1}", "n_seeds": len(seeds), "asks_mean": round(float(np.mean(asks)), 1),
                         "refusal_rate_pct": round(100 * sum(refused) / sum(asks), 2) if sum(asks) else np.nan,
                         "share_received_pct": round(100 * float(np.sum(rcv) / np.sum(isl)), 2),
                         "island_mh_mean": round(float(np.mean(isl)), 1), "seasons_mean": round(float(np.mean(seas)), 1)})
    df = pd.DataFrame(rows)
    out = os.path.join(cfg["paths"]["output_dir"], "census", f"relationship_census_v4_seeds{s0}-{s1}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)                 # output/census may not exist yet
    df.to_csv(out, index=False)
    print(f"wrote {out}; pair population {pop:,}")
    print(df.pivot(index="scenario", columns="cls", values="pct_of_pairs")[CLASSES].round(4).to_string())
    print(df.drop_duplicates("scenario")[["scenario", "asks_mean", "refusal_rate_pct", "share_received_pct",
                                          "island_mh_mean", "seasons_mean"]].to_string(index=False))


if __name__ == "__main__":
    main()
