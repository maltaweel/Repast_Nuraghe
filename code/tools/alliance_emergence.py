"""Print emergence statistics of the alliance runs (concentration of help, skills, strategy trends, defectors).
  python tools/alliance_emergence.py config.yaml   ->  stdout (saved as cache/logs/alliance_emergence.log)"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
root = os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance")
for n in cfg["alliance"]["list"]:
    d = os.path.join(root, n)
    sp = pd.read_csv(os.path.join(d, "specialisation.csv"))
    st = pd.read_csv(os.path.join(d, "strategy_by_season.csv"))
    st = st[st.towers_started >= 5]
    craft = sp[["given_quarry", "given_dress", "given_build"]].sum(axis=1).sort_values(ascending=False).to_numpy()
    allg = sp[[c for c in sp.columns if c.startswith("given_")]].sum(axis=1)
    line = f"{n}: "
    if allg.sum() > 0:
        top10 = craft[: max(1, len(craft) // 10)].sum() / max(craft.sum(), 1e-9)
        line += (f"communities giving any help {100 * (allg > 0).mean():.1f}%; top 10% of suppliers give "
                 f"{100 * top10:.1f}% of craft-stage help; ")
    for s in ("quarry", "dress", "build"):
        line += f"skill_{s} median {sp['skill_' + s].median():.3f} min {sp['skill_' + s].min():.3f}; "
    a, b = st.iloc[0], st.iloc[-1]
    line += (f"first->last {int(a.season_from)}-{int(a.season_to)} vs {int(b.season_from)}-{int(b.season_to)}: "
             f"ask quarry {a.req_quarry:.3f}->{b.req_quarry:.3f}, dress {a.req_dress:.3f}->{b.req_dress:.3f}, "
             f"build {a.req_build:.3f}->{b.req_build:.3f}, relay {a.relay_any:.3f}->{b.relay_any:.3f}, "
             f"relay 0.75 {a['relay_0.75']:.3f}->{b['relay_0.75']:.3f}, track {a.track:.3f}->{b.track:.3f}, "
             f"cheapest face {a.face0_share:.3f}->{b.face0_share:.3f}, imitated {a.imitated:.3f}->{b.imitated:.3f}")
    print(line)
    for f in ("handoffs", "alliances"):
        p = os.path.join(d, f + ".shp")
        if os.path.exists(p):
            import geopandas as gpd
            g = gpd.read_file(p)
            if f == "handoffs":
                print(f"  hand-off cells used: {len(g):,} (all seeds), uses per seed {g.USES_SEED.sum():,.1f}")
            else:
                print(f"  allied pairs in any seed: {len(g):,}; allied in >= 50% of seeds: {int((g.FRAC_ALL >= 0.5).sum())}; "
                      f"mean trust {g.TRUST.mean():.3f}; help per pair per seed {g.HELP_MH.mean():,.0f} MH")
    sj = json.load(open(os.path.join(d, "stats.json")))
    if sj.get("track_cells_mean"):
        print(f"  track cells built per seed {sj['track_cells_mean']:,.0f}")
