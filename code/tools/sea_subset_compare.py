"""S9 subset comparison (subset/dev/*, sites300.txt, seeds 1-3): sea scenario vs its sea-off twin.
  python tools/sea_subset_compare.py  ->  prints a table, writes subset/sea_vs_land.csv"""
import os
import pandas as pd
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "subset", "dev")
sea = set(pd.read_csv(os.path.join(D, "..", "..", "cache", "sea", "sites_haul_sea5kn.csv")).query("mode == 'sea'").UID)
pairs = [("full", "S9_sea_4kn"), ("full", "S9_sea_5kn"), ("full", "S9_sea_6kn"), ("high", "high_sea"),
         ("alliance/A1_ask", "alliance/A1_ask_sea"), ("alliance/A5_full", "alliance/A5_full_sea"),
         ("pre/P_G50_hub", "pre/P_G50_hub_sea")]
ref = {"full": "../dev/full", "high": "../dev/high", "alliance/A1_ask": "../dev/alliance/A1_ask",
       "alliance/A5_full": "../dev/alliance/A5_full", "pre/P_G50_hub": "../dev/pre/P_G50_hub"}


def load(p):
    return pd.read_csv(os.path.join(D, p, "nuraghe_manhours_runs.csv.gz"))


rows = []
for a, b in pairs:
    x, y = load(a), load(b)
    walk = "mh_walk" if "mh_walk" in x.columns else "mh_help"
    r = {"pair": f"{b} vs {a}"}
    for nm, d in (("land", x), ("sea", y)):
        g = d.groupby("seed")
        r[f"MH_{nm}"] = g.mh_total.sum().mean()
        r[f"TR_{nm}"] = g.mh_transport.sum().mean()
        r[f"{walk}_{nm}"] = g[walk].sum().mean()
        s = d[d.UID.isin(sea)].groupby("seed")
        r[f"MH_seasites_{nm}"] = s.mh_total.sum().mean()
        r[f"days_mean_{nm}"] = d.days.mean()
    r["dMH_pct"] = 100 * (r["MH_sea"] / r["MH_land"] - 1)
    r["dTR_pct"] = 100 * (r["TR_sea"] / r["TR_land"] - 1)
    r["dMH_seasites_pct"] = 100 * (r["MH_seasites_sea"] / r["MH_seasites_land"] - 1)
    r["dWalk_pct"] = 100 * (r[f"{walk}_sea"] / r[f"{walk}_land"] - 1) if r[f"{walk}_land"] else float("nan")
    r["dDays_pct"] = 100 * (r["days_mean_sea"] / r["days_mean_land"] - 1)
    r["walk_col"] = walk
    rows.append(r)
t = pd.DataFrame(rows)
t.to_csv(os.path.join(D, "..", "sea_vs_land.csv"), index=False)
pd.set_option("display.width", 250)
print(f"300-site subset, seeds 1-3; {len(sea & set(load('full').UID))} subset sites use the sea at 5 kn")
for r in rows:
    print(f"{r['pair']:42s} island MH {r['MH_land']:>12,.0f} -> {r['MH_sea']:>12,.0f} ({r['dMH_pct']:+.2f}%); transport "
          f"{r['dTR_pct']:+.2f}%; sea sites MH {r['dMH_seasites_pct']:+.1f}%; {r['walk_col']} {r['dWalk_pct']:+.2f}%; mean days {r['dDays_pct']:+.2f}%")
