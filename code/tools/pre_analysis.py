"""Pre-existing networks: comparison, size x shape, reach, location and hub analysis.

  python tools/pre_analysis.py config.yaml

Reads output/scenarios_pre/<scenario>/{stats.json, nuraghe_manhours_summary.csv, group_membership.csv} and the
alliance A0_alone / A2_trust / A5_full outputs. Writes to output/scenarios_pre/:
  pre_comparison.csv  one row per scenario: size / shape / reach / variant, realised group size, ties, island
                      man-hours mean/min/max, % vs A0_alone, A2_trust, A5_full, stage shares, received share,
                      medians for 1/2/3 towers, % of sites over 30k, median seasons for one tower
  pre_location.csv    like-for-like: man-hours of the networked sites vs the same sites in A0_alone (and in the
                      island-wide G20 kmesh4 network); for G20 kmesh4, groups with vs without an on-outcrop member
  pre_hubs.csv        for hub-shaped networks: share of help given / received by the hubs vs their share of sites
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pre_networks  # noqa: E402
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
OUT = cfg["paths"]["output_dir"]
ROOT = os.path.join(OUT, "scenarios_pre")
AL = os.path.join(OUT, "scenarios_alliance")
THR = float(cfg["lit_scenarios"]["community_threshold_ph"])
specs = pre_networks.expand(cfg)
ref = {n: json.load(open(os.path.join(AL, n, "stats.json"))) for n in ("A0_alone", "A2_trust", "A5_full")}
a0s = pd.read_csv(os.path.join(AL, "A0_alone", "nuraghe_manhours_summary.csv"))[["UID", "mh_mean"]]
haul = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))


def describe(name, spec):
    if spec.get("all", 0) is None:
        return dict(size="none", shape="none", reach=1, variant="no ties")
    v = []
    for k in ("trust", "tie_loss_refusals", "specialisation", "tracks"):
        if spec.get(k):
            v.append({"trust": "D7 ties + trust", "tie_loss_refusals": f"D8 tie lost after {spec[k]} refusals",
                      "specialisation": "specialisation", "tracks": "tracks"}[k])
    if "all" in spec:
        a = spec["all"]
        if "partners" in a:
            return dict(size=f"partners {a['partners']}", shape="nearest", reach=spec.get("reach", 1), variant="; ".join(v) or "")
        for k in ("seed_from", "region"):
            if k in a:
                v.append(f"{k}={a[k]}")
        return dict(size=a["groups"], shape=a["shape"], reach=spec.get("reach", 1), variant="; ".join(v))
    return dict(size="per stage", shape="per stage", reach=spec.get("reach", 1),
                variant="stone " + "/".join(str(spec["stone"][k]) for k in ("groups", "shape")) + "; move " +
                "/".join(str(spec["move"][k]) for k in ("groups", "shape")) + "; build " +
                "/".join(str(spec["build"][k]) for k in ("groups", "shape")))


rows = []
for n, spec in specs.items():
    d = os.path.join(ROOT, n)
    if not os.path.exists(os.path.join(d, "stats.json")):
        continue
    st = json.load(open(os.path.join(d, "stats.json")))
    r = {"scenario": n, **describe(n, spec)}
    gm_p = os.path.join(d, "group_membership.csv")
    if os.path.exists(gm_p):
        gm = pd.read_csv(gm_p)
        g = gm[gm.group_stone >= 0].groupby("group_stone").size()
        r["groups"] = int(g.size); r["group_size_mean"] = float(g.mean()) if g.size else 0.0
        r["group_size_median"] = float(g.median()) if g.size else 0.0
        r["ties_per_site_mean"] = float(gm.ties_stone.mean()); r["tied_sites"] = int((gm.ties_stone > 0).sum())
    else:
        r.update(groups=0, group_size_mean=0.0, group_size_median=0.0, ties_per_site_mean=0.0, tied_sites=0)
    for k in ("island_mh_mean", "island_mh_min", "island_mh_max", "share_received", "median_mh_twr1",
              "median_mh_twr2", "median_mh_twr3", "pct_sites_over_30k", "median_years_twr1", "n_alliances_mean",
              "share_quarry", "share_dress", "share_transport", "share_build", "share_lift", "share_setup", "share_walk"):
        r[k] = st.get(k)
    for a in ("A0_alone", "A2_trust", "A5_full"):
        r[f"pct_vs_{a}"] = 100 * (st["island_mh_mean"] / ref[a]["island_mh_mean"] - 1)
    rows.append(r)
comp = pd.DataFrame(rows)
for a in ("A0_alone", "A2_trust", "A5_full"):
    rr = {"scenario": a, "size": "alliance reference", "shape": "", "reach": "", "variant": "emergent",
          **{k: ref[a].get(k) for k in ("island_mh_mean", "island_mh_min", "island_mh_max", "share_received",
                                       "median_mh_twr1", "median_mh_twr2", "median_mh_twr3", "pct_sites_over_30k",
                                       "median_years_twr1", "n_alliances_mean")}}
    for b in ("A0_alone", "A2_trust", "A5_full"):
        rr[f"pct_vs_{b}"] = 100 * (ref[a]["island_mh_mean"] / ref[b]["island_mh_mean"] - 1)
    comp = pd.concat([comp, pd.DataFrame([rr])], ignore_index=True)
comp.to_csv(os.path.join(ROOT, "pre_comparison.csv"), index=False, float_format="%.4f")
# ---- location: like-for-like
loc = []


def site_mh(n):
    return pd.read_csv(os.path.join(ROOT, n, "nuraghe_manhours_summary.csv"))[["UID", "mh_mean"]]


base_net = "P_G20_system_kmesh4"
for n in [x for x in specs if x.startswith("P_G20_kmesh4_") or x == base_net]:
    if not os.path.exists(os.path.join(ROOT, n, "group_membership.csv")):
        continue
    gm = pd.read_csv(os.path.join(ROOT, n, "group_membership.csv"))
    net = gm.UID[gm.ties_stone > 0]
    s = site_mh(n).merge(a0s, on="UID", suffixes=("", "_A0"))
    if os.path.exists(os.path.join(ROOT, base_net, "nuraghe_manhours_summary.csv")):
        s = s.merge(site_mh(base_net).rename(columns={"mh_mean": "mh_G20"}), on="UID")
    m = s.UID.isin(net)
    row = {"scenario": n, "networked_sites": int(m.sum()), "mh_networked": s.mh_mean[m].sum(),
           "mh_same_sites_A0": s.mh_mean_A0[m].sum(), "pct_networked_vs_A0": 100 * (s.mh_mean[m].sum() / s.mh_mean_A0[m].sum() - 1),
           "pct_rest_vs_A0": 100 * (s.mh_mean[~m].sum() / s.mh_mean_A0[~m].sum() - 1) if (~m).any() else np.nan}
    if "mh_G20" in s:
        row["pct_networked_vs_same_sites_G20_islandwide"] = 100 * (s.mh_mean[m].sum() / s.mh_G20[m].sum() - 1)
    loc.append(row)
if os.path.exists(os.path.join(ROOT, base_net, "group_membership.csv")):
    gm = pd.read_csv(os.path.join(ROOT, base_net, "group_membership.csv")).merge(haul[["UID", "on_outcrop"]], on="UID")
    has = gm.groupby("group_stone").on_outcrop.transform("max").astype(bool)
    s = site_mh(base_net).merge(a0s, on="UID", suffixes=("", "_A0")).merge(gm[["UID"]].assign(has=has.values), on="UID")
    for flag, lab in ((True, "groups with >= 1 on-outcrop member"), (False, "groups with no on-outcrop member")):
        m = s.has == flag
        loc.append({"scenario": f"{base_net}: {lab}", "networked_sites": int(m.sum()), "mh_networked": s.mh_mean[m].sum(),
                    "mh_same_sites_A0": s.mh_mean_A0[m].sum(),
                    "pct_networked_vs_A0": 100 * (s.mh_mean[m].sum() / s.mh_mean_A0[m].sum() - 1)})
loc = pd.DataFrame(loc)
loc.to_csv(os.path.join(ROOT, "pre_location.csv"), index=False, float_format="%.4f")
# ---- hubs
hub = []
for n, spec in specs.items():
    a = spec.get("all") or {}
    if a.get("shape") != "hub" or not os.path.exists(os.path.join(ROOT, n, "group_membership.csv")):
        continue
    gm = pd.read_csv(os.path.join(ROOT, n, "group_membership.csv"))
    sm = pd.read_csv(os.path.join(ROOT, n, "nuraghe_manhours_summary.csv"))
    rr = pd.read_csv(os.path.join(ROOT, n, "nuraghe_manhours_runs.csv.gz"), usecols=["UID", "mh_given", "mh_received"])
    g = rr.groupby("UID")[["mh_given", "mh_received"]].mean().reset_index().merge(gm[["UID", "hub_stone"]], on="UID")
    h = g.hub_stone == 1
    hub.append({"scenario": n, "hubs": int(h.sum()), "hub_share_of_sites": float(h.mean()),
                "hub_share_of_help_given": float(g.mh_given[h].sum() / max(g.mh_given.sum(), 1e-9)),
                "hub_share_of_help_received": float(g.mh_received[h].sum() / max(g.mh_received.sum(), 1e-9)),
                "hub_mean_given_mh": float(g.mh_given[h].mean()), "member_mean_given_mh": float(g.mh_given[~h].mean())})
hub = pd.DataFrame(hub)
hub.to_csv(os.path.join(ROOT, "pre_hubs.csv"), index=False, float_format="%.4f")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 120)
print(comp[["scenario", "size", "shape", "reach", "variant", "group_size_mean", "island_mh_mean", "pct_vs_A0_alone",
            "pct_vs_A2_trust", "pct_vs_A5_full", "share_received", "median_mh_twr1"]].round(3).to_string(index=False))
print(loc.round(3).to_string(index=False))
print(hub.round(3).to_string(index=False))
