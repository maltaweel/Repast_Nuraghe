"""How the cooperation networks form over time (a Nurnet collaborator's help_log / allied_season bookkeeping, folded into v4).

  python tools/formation.py config.yaml

Reads seed_NNNN.helplog.csv.gz (season, helper, owner, man-hours) and seed_NNNN.allied.csv.gz (a, b, first season
allied) of each alliance scenario, all seeds. Writes output/formation_v4/:
  formation_curves.csv   per scenario and season: cumulative helping pairs (unordered pairs with any help so far),
                         cumulative ever-allied pairs (pairs allied at any time so far), help man-hours in the season;
                         mean, 5th and 95th percentile over seeds
  alliance_counts.csv    per scenario: ever-allied pairs per seed (allied at any time) vs allied pairs at the END of a run
                         (pair column `allied`), mean over seeds; and a Nurnet collaborator's seed-1 numbers for comparison
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")


def _opt(flag):                                          # merged: optional --names a,b and --out-sub DIR (defaults as before)
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


OUT = os.path.join(cfg["paths"]["output_dir"], _opt("--out-sub") or "formation_v4")
os.makedirs(OUT, exist_ok=True)
names = _opt("--names").split(",") if _opt("--names") else [n for n in cfg["alliance"]["list"] if n != "A0_alone"]
curves, counts = [], []
for n in names:
    dirs = glob.glob(os.path.join(cfg["paths"]["cache_dir"], "runs", f"alliance_{n}", "*"))
    if not dirs:                                         # B6: scenario not run: skip it
        print(f"{n}: no run directory, skipped")
        continue
    rd = max(dirs, key=lambda d: (len(glob.glob(os.path.join(d, "*.helplog.csv.gz"))), os.path.getmtime(d)))
    files = sorted(glob.glob(os.path.join(rd, "seed_*.helplog.csv.gz")))
    if not files:                                        # B6: no helplog files (missing or partial run): skip it
        print(f"{n}: no helplog files in {rd}, skipped")
        continue
    S = max([int(cfg["alliance"]["max_seasons"])] + [int(v.get("max_seasons", 0)) for v in (cfg.get("alliance_extra") or {}).values()
                                                       if isinstance(v, dict)])
    smax = 0
    per = []
    ever, end = [], []
    for f in files:
        seed = os.path.basename(f)[5:9]
        h = pd.read_csv(f)
        a = pd.read_csv(f.replace(".helplog.", ".allied."))
        p = pd.read_csv(f.replace(".helplog.", ".pairs."))
        if "ask_only" in p.columns:
            p = p[p.ask_only == 0]
        h["pa"] = np.minimum(h.helper, h.owner); h["pb"] = np.maximum(h.helper, h.owner)
        first = h.groupby(["pa", "pb"]).season.min()
        last_season = int(max(h.season.max() if len(h) else 0, a.season_first_allied.max() if len(a) else 0))
        smax = max(smax, last_season)
        per.append((np.bincount(first.to_numpy(), minlength=S + 2), np.bincount(a.season_first_allied.to_numpy(), minlength=S + 2)
                    if len(a) else np.zeros(S + 2, int), np.bincount(h.season.to_numpy(), weights=h.mh.to_numpy(), minlength=S + 2)))
        ever.append(len(a)); end.append(int(p.allied.sum()))
    seasons = np.arange(1, smax + 1)
    H = np.array([np.cumsum(x[0])[1:smax + 1] for x in per]); A = np.array([np.cumsum(x[1])[1:smax + 1] for x in per])
    M = np.array([x[2][1:smax + 1] for x in per])
    for k, s in enumerate(seasons):
        curves.append({"scenario": n, "season": int(s), "seeds": len(files),
                       "helping_pairs_mean": H[:, k].mean(), "helping_pairs_p05": np.percentile(H[:, k], 5),
                       "helping_pairs_p95": np.percentile(H[:, k], 95), "ever_allied_mean": A[:, k].mean(),
                       "ever_allied_p05": np.percentile(A[:, k], 5), "ever_allied_p95": np.percentile(A[:, k], 95),
                       "help_mh_mean": M[:, k].mean()})
    counts.append({"scenario": n, "seeds": len(files), "ever_allied_per_seed_mean": float(np.mean(ever)),
                   "allied_at_end_per_seed_mean": float(np.mean(end)), "ever_allied_seed1": ever[0], "allied_at_end_seed1": end[0]})
    print(f"{n}: {len(files)} seeds; ever-allied {np.mean(ever):.2f} vs allied at end {np.mean(end):.2f} per seed; "
          f"seed 1: {ever[0]} vs {end[0]}")
pd.DataFrame(curves).to_csv(os.path.join(OUT, "formation_curves.csv"), index=False, float_format="%.3f")
pd.DataFrame(counts).to_csv(os.path.join(OUT, "alliance_counts.csv"), index=False, float_format="%.3f")
