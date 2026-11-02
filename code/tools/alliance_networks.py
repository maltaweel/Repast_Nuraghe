"""Cooperation networks by role (layer) at the end of the alliance runs.

  python tools/alliance_networks.py config.yaml [scenario ...] [--core-freq 0.5] [--jobs 4]

Input: the per-seed pair files of the alliance model (cache/runs/alliance_<scenario>/<hash>/seed_NNNN.pairs.csv.gz),
which carry help per directed pair and stage (help_ab_quarry ... help_ba_track) and task counts (n_ab_<stage>).
Layers: stone = quarry + dress; transport = relay leg 1 and transport help + trackway labour (track folded into
transport: it is transport infrastructure); build = build/lift; all = every stage.

Output per scenario and layer, in output/scenarios_alliance/<scenario>/network/<layer>/:
  edges.csv.gz        all directed help links aggregated over seeds: FREQ (share of seeds with help on the link),
                      MH_MEAN (mean man-hours per run over ALL seeds), MH_WHEN (mean in the seeds where present),
                      TRUST (the helped community's trust in the helper at the end of the run), ALLIED, RECIP, DIST_KM, TASKS
  edges.shp           the links present in >= freq_min (0.05) of seeds (the full list is in edges.csv.gz)
  core_edges.shp      links present in >= core_freq (0.5) of seeds
  nodes.csv / .shp    per community: per-seed mean out/in degree, out/in strength (mean network), betweenness
                      (undirected network of links with FREQ >= freq_min, distance = 1/MH_MEAN, 300 sampled sources),
                      Louvain community and component size on the core network, HUB flag (top hub_share by out-strength)
  network.graphml     the mean directed network of links with FREQ >= freq_min, with coordinates
  network_by_seed.csv per seed: nodes, links, reciprocal share, largest component, clustering, Louvain modularity,
                      helpers, share of helpers serving >= 5 communities, max out-degree, pass-through share
  degree_distribution.csv  per-seed out- and in-degree distribution (mean count of nodes per degree)
  metrics.json        the row of network_comparison.csv (incl. asks, refusals and the refusal rate of the layer)
Asks/refusals (a Nurnet collaborator's counters): per request, which is always for one stage task (quarry, dress, relay leg 1 =
transport, build); track work is never requested, so the transport layer's rate covers relay requests only.
Pair rows known only from asks (ask_only = 1) carry no help and are ignored for help edges (help > 0 filter).
Per scenario: community_roles.csv / .shp (ROLE = the layer a community gives most labour to in a seed, modal over the
seeds in which it helps; ROLE_CONS = share of those seeds with the modal role; HELP_FREQ = share of seeds with any
help given; GV_* = mean labour given per run by layer; SK_* = mean final skill).
Across scenarios: output/scenarios_alliance/network_comparison.csv (one row per scenario x layer).
"""
import argparse
import glob
import json
import os
import sys
from multiprocessing import Pool

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import LineString

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

SCEN = ["A1_ask", "A2_trust", "A3_trust_learning", "A4_trust_track", "A5_full", "A5_full_freerider"]
LAYERS = {"stone": ["quarry", "dress"], "transport": ["transport", "track"], "build": ["build"],
          "all": ["quarry", "dress", "transport", "build", "track"]}
FREQ_MIN = 0.05
HUB_SHARE = 0.05          # hubs = top 5% of helper nodes by out-strength in the layer (FREE)
SERVE_MIN = 5             # "hub-like" helper: serves >= 5 communities in one seed (spec)


def run_dir(cache, scen):
    """The complete, most recent signature directory (100 .done files) - not simply the last hash; None (with a
    printed message) when the scenario has no run with pair files (NEW-3: the caller skips it)."""
    dirs = [d for d in glob.glob(os.path.join(cache, "runs", f"alliance_{scen}", "*"))
            if glob.glob(os.path.join(d, "seed_*.pairs.csv.gz"))]
    if not dirs:
        print(f"  {scen}: no run directory with pair files in {cache}/runs -> skipped", flush=True)
        return None
    return max(dirs, key=lambda d: (len(glob.glob(os.path.join(d, "*.done"))), os.path.getmtime(d)))


def load_layer(files, stages):
    rows = []
    for f in files:
        p = pd.read_csv(f)
        if "help_ab_quarry" not in p.columns:
            raise SystemExit(f"{f}: no per-stage columns (rerun the alliance model)")
        for d, (x, y) in (("ab", ("a", "b")), ("ba", ("b", "a"))):
            h = sum(p[f"help_{d}_{s}"] for s in stages)
            n = sum(p[f"n_{d}_{s}"] for s in stages)
            o = "ba" if d == "ab" else "ab"
            back = sum(p[f"help_{o}_{s}"] for s in stages)
            # src = helper, dst = helped; trust = the helped community's trust in the helper at the end
            # (pair columns: trust_ab = a's trust in b)
            r = pd.DataFrame({"seed": p.seed, "src": p[x], "dst": p[y], "help": h, "tasks": n,
                              "trust": p["trust_ba" if d == "ab" else "trust_ab"], "allied": p.allied,
                              "recip": (h > 0) & (back > 0)})
            rows.append(r[r.help > 0])
    return pd.concat(rows, ignore_index=True)


ASK_STAGES = ("quarry", "dress", "transport", "build")


def ask_stats(files, stages, n_nodes):
    """Asks and refusals in a layer (a Nurnet collaborator's counters; each request is for exactly one stage task, so the
    attribution to layers is exact). asks_ab = a asked b, refused_ab = b refused a. Track work is never asked for."""
    st = [x for x in stages if x in ASK_STAGES]
    asked = np.zeros(n_nodes); refused = np.zeros(n_nodes); made = np.zeros(n_nodes)
    tot_a = tot_r = 0
    for f in files:
        p = pd.read_csv(f)
        if not len(p) or "asks_ab_quarry" not in p.columns or not st:
            continue
        for d, (x, y) in (("ab", ("a", "b")), ("ba", ("b", "a"))):
            a = sum(p[f"asks_{d}_{s}"] for s in st).to_numpy()
            r = sum(p[f"refused_{d}_{s}"] for s in st).to_numpy()
            np.add.at(made, p[x].to_numpy(), a)          # asker
            np.add.at(asked, p[y].to_numpy(), a)         # the community that decided
            np.add.at(refused, p[y].to_numpy(), r)
            tot_a += int(a.sum()); tot_r += int(r.sum())
    return tot_a, tot_r, made, asked, refused


SEED_COLS = ["seed", "nodes", "links", "reciprocal_share", "undirected_pairs", "largest_component", "mean_clustering",
             "modularity", "n_louvain", "helpers", "helpers_serving_ge5", "max_out_degree", "mean_out_degree",
             "receivers_ge2_helpers", "pass_through_share"]


def per_seed(e, ns_seeds):
    out = []
    for s in ns_seeds:
        d = e[e.seed == s]
        if not len(d):              # NEW-3: a seed without help in this layer gets the full schema (counts 0, ratios NaN)
            out.append({"seed": s, "nodes": 0, "links": 0, "reciprocal_share": np.nan, "undirected_pairs": 0,
                        "largest_component": 0, "mean_clustering": np.nan, "modularity": np.nan, "n_louvain": 0,
                        "helpers": 0, "helpers_serving_ge5": np.nan, "max_out_degree": 0, "mean_out_degree": np.nan,
                        "receivers_ge2_helpers": np.nan, "pass_through_share": np.nan})
            continue
        g = nx.Graph()
        for a, b, w in zip(d.src, d.dst, d.help):
            g.add_edge(int(a), int(b), weight=float(w) + (g[int(a)][int(b)]["weight"] if g.has_edge(int(a), int(b)) else 0.0))
        comms = nx.community.louvain_communities(g, weight="weight", seed=1)
        outdeg = d.groupby("src").dst.nunique()
        indeg = d.groupby("dst").src.nunique()
        both = len(set(outdeg.index) & set(indeg.index))
        pairs = {(min(a, b), max(a, b)) for a, b in zip(d.src, d.dst)}
        out.append({"seed": s, "nodes": g.number_of_nodes(), "links": len(d),
                    "reciprocal_share": float(d.recip.sum() / len(d)),
                    "undirected_pairs": len(pairs),
                    "largest_component": max(len(c) for c in nx.connected_components(g)),
                    "mean_clustering": nx.average_clustering(g),
                    "modularity": nx.community.modularity(g, comms, weight="weight"), "n_louvain": len(comms),
                    "helpers": int(outdeg.size), "helpers_serving_ge5": float((outdeg >= SERVE_MIN).mean()),
                    "max_out_degree": int(outdeg.max()), "mean_out_degree": float(outdeg.mean()),
                    "receivers_ge2_helpers": float((indeg >= 2).mean()),
                    "pass_through_share": float(both / g.number_of_nodes())})
    return pd.DataFrame(out, columns=SEED_COLS)


ROOT_SUB = "scenarios_alliance"


def job(args):
    cfg, scen, layer, core_freq, sub = args
    global ROOT_SUB
    ROOT_SUB = sub
    rd = run_dir(cfg["paths"]["cache_dir"], scen)
    files = sorted(glob.glob(os.path.join(rd, "seed_*.pairs.csv.gz")))
    seeds = [int(os.path.basename(f)[5:9]) for f in files]
    ns = len(files)
    sites = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    xy = sites[["x", "y"]].to_numpy()
    uid = sites.UID.to_numpy()
    e = load_layer(files, LAYERS[layer])
    if not len(e):                  # NEW-3: no help in this layer in any seed (e.g. A0_alone) -> clean skip
        return _empty_layer(cfg, scen, layer, files, ns, per_seed(e, seeds), len(sites))
    e["dist_km"] = np.hypot(*(xy[e.src.to_numpy()] - xy[e.dst.to_numpy()]).T) / 1000.0
    st = per_seed(e, seeds)
    agg = e.groupby(["src", "dst"]).agg(n=("help", "size"), help_sum=("help", "sum"), tasks=("tasks", "sum"),
                                        trust=("trust", "mean"), allied=("allied", "mean"),
                                        recip=("recip", "mean")).reset_index()
    agg["FREQ"] = agg.n / ns
    agg["MH_MEAN"] = agg.help_sum / ns
    agg["MH_WHEN"] = agg.help_sum / agg.n
    agg["DIST_KM"] = np.hypot(*(xy[agg.src.to_numpy()] - xy[agg.dst.to_numpy()]).T) / 1000.0
    out = os.path.join(cfg["paths"]["output_dir"], ROOT_SUB, scen, "network", layer)
    os.makedirs(out, exist_ok=True)
    ed = pd.DataFrame({"FROM_UID": uid[agg.src], "TO_UID": uid[agg.dst], "FREQ": agg.FREQ.round(3),
                       "MH_MEAN": agg.MH_MEAN.round(1), "MH_WHEN": agg.MH_WHEN.round(1),
                       "TASKS": (agg.tasks / ns).round(3), "TRUST": agg.trust.round(3), "ALLIED": agg.allied.round(3),
                       "RECIP": agg.recip.round(3), "DIST_KM": agg.DIST_KM.round(2)})
    ed.to_csv(os.path.join(out, "edges.csv.gz"), index=False, compression={"method": "gzip", "mtime": 0})
    crs = cfg.get("crs", "EPSG:25832")
    keep = (agg.FREQ >= FREQ_MIN).to_numpy()
    core = (agg.FREQ >= core_freq).to_numpy()
    for mask, fn in ((keep, "edges.shp"), (core, "core_edges.shp")):
        a = agg[mask]
        geom = [LineString([xy[s], xy[t]]) for s, t in zip(a.src, a.dst)]
        if len(a):
            gpd.GeoDataFrame(ed[mask].reset_index(drop=True), geometry=geom, crs=crs).to_file(
                os.path.join(out, fn), engine="pyogrio", encoding="UTF-8")
    # node metrics
    pd_out = e.groupby(["seed", "src"]).dst.nunique().groupby("src").sum() / ns       # mean per-seed out-degree
    pd_in = e.groupby(["seed", "dst"]).src.nunique().groupby("dst").sum() / ns
    out_mh = agg.groupby("src").MH_MEAN.sum(); in_mh = agg.groupby("dst").MH_MEAN.sum()
    K = agg[keep]
    U = nx.Graph()
    for a, b, w in zip(K.src, K.dst, K.MH_MEAN):
        a, b = int(a), int(b)
        U.add_edge(a, b, weight=float(w) + (U[a][b]["weight"] if U.has_edge(a, b) else 0.0))
    for a, b in U.edges():
        U[a][b]["dist"] = 1.0 / U[a][b]["weight"]
    bc = nx.betweenness_centrality(U, weight="dist", k=min(300, U.number_of_nodes()), seed=1) if U.number_of_nodes() > 2 else {}
    C = nx.Graph()
    A = agg[core]
    for a, b, w in zip(A.src, A.dst, A.MH_MEAN):
        a, b = int(a), int(b)
        C.add_edge(a, b, weight=float(w) + (C[a][b]["weight"] if C.has_edge(a, b) else 0.0))
    lvc = nx.community.louvain_communities(C, weight="weight", seed=1) if C.number_of_edges() else []
    lv = {n: i for i, c in enumerate(lvc) for n in c}
    comp = {n: len(c) for c in nx.connected_components(C) for n in c} if C.number_of_edges() else {}
    nodes = pd.DataFrame({"gid": np.arange(len(sites)), "UID": uid, "TWR_N": sites.TWR_N})
    nodes["OUT_DEG"] = nodes.gid.map(pd_out).fillna(0).round(3)
    nodes["IN_DEG"] = nodes.gid.map(pd_in).fillna(0).round(3)
    nodes["OUT_MH"] = nodes.gid.map(out_mh).fillna(0).round(1)
    nodes["IN_MH"] = nodes.gid.map(in_mh).fillna(0).round(1)
    nodes["BETWEEN"] = [round(bc.get(i, 0.0), 6) for i in nodes.gid]
    nodes["CORE_COMM"] = [lv.get(i, -1) for i in nodes.gid]
    nodes["CORE_COMP"] = [comp.get(i, 0) for i in nodes.gid]
    nodes["HAUL_M"] = sites.haul_m.round(1); nodes["ON_OUTCR"] = sites.on_outcrop.astype(int)
    tot_a, tot_r, made, asked, refused = ask_stats(files, LAYERS[layer], len(sites))
    nodes["ASKS_MADE"] = (made / ns).round(3); nodes["ASKED"] = (asked / ns).round(3)
    nodes["REFUSED"] = (refused / ns).round(3)
    helpers = nodes[nodes.OUT_MH > 0]
    thr = helpers.OUT_MH.quantile(1 - HUB_SHARE) if len(helpers) else np.inf
    nodes["HUB"] = ((nodes.OUT_MH >= thr) & (nodes.OUT_MH > 0)).astype(int)
    helpers = nodes[nodes.OUT_MH > 0]
    nodes.to_csv(os.path.join(out, "nodes.csv"), index=False)
    gpd.GeoDataFrame(nodes.drop(columns="gid"), geometry=gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=crs).to_file(
        os.path.join(out, "nodes.shp"), engine="pyogrio", encoding="UTF-8")
    G = nx.DiGraph()
    for a, b, w, f in zip(K.src, K.dst, K.MH_MEAN, K.FREQ):
        G.add_edge(int(a), int(b), weight=float(w), freq=float(f))
    for i in G.nodes:
        G.nodes[i].update(UID=str(uid[i]), x=float(xy[i, 0]), y=float(xy[i, 1]), towers=int(sites.TWR_N[i]))
    nx.write_graphml(G, os.path.join(out, "network.graphml"))
    st.to_csv(os.path.join(out, "network_by_seed.csv"), index=False)
    od = e.groupby(["seed", "src"]).dst.nunique().value_counts().sort_index() / ns
    idd = e.groupby(["seed", "dst"]).src.nunique().value_counts().sort_index() / ns
    dd = pd.DataFrame({"degree": sorted(set(od.index) | set(idd.index))})
    dd["out_nodes_per_seed"] = dd.degree.map(od).fillna(0); dd["in_nodes_per_seed"] = dd.degree.map(idd).fillna(0)
    dd.to_csv(os.path.join(out, "degree_distribution.csv"), index=False)
    hubs = nodes[nodes.HUB == 1]
    m = dict(scenario=scen, layer=layer, seeds=ns, links_any_seed=len(agg), links_freq05=int(keep.sum()),
             core_links=int(core.sum()), core_nodes=C.number_of_nodes(),
             core_largest_component=max(comp.values()) if comp else 0, core_communities=len(lvc),
             core_modularity=float(nx.community.modularity(C, lvc, weight="weight")) if lvc else np.nan,
             core_reciprocal_share=_core_recip(A),
             mh_per_seed=float(e.help.sum() / ns),
             asks_per_seed=tot_a / ns, refusals_per_seed=tot_r / ns,
             refusal_rate=(tot_r / tot_a) if tot_a else np.nan,
             median_link_km=float(e.dist_km.median()), median_link_km_weighted=float(_wmedian(e.dist_km, e.help)),
             median_core_link_km=float(A.DIST_KM.median()) if len(A) else np.nan,
             n_hubs=int(len(hubs)), hub_out_mh_min=float(thr) if np.isfinite(thr) else np.nan,
             hub_share_of_layer_mh=float(hubs.OUT_MH.sum() / max(nodes.OUT_MH.sum(), 1e-9)),
             hub_median_haul_m=float(hubs.HAUL_M.median()) if len(hubs) else np.nan,
             hub_on_outcrop_share=float(hubs.ON_OUTCR.mean()) if len(hubs) else np.nan,
             helper_median_haul_m=float(helpers.HAUL_M.median()) if len(helpers) else np.nan,
             hub_mean_haul_m=float(hubs.HAUL_M.mean()) if len(hubs) else np.nan,
             helper_mean_haul_m=float(helpers.HAUL_M.mean()) if len(helpers) else np.nan,
             helper_on_outcrop_share=float(helpers.ON_OUTCR.mean()) if len(helpers) else np.nan,
             max_out_degree_any_seed=int(st.max_out_degree.max()),
             **{f"per_seed_{k}_median": float(st[k].median()) for k in
                ["nodes", "links", "reciprocal_share", "largest_component", "mean_clustering", "modularity", "helpers",
                 "helpers_serving_ge5", "max_out_degree", "mean_out_degree", "receivers_ge2_helpers", "pass_through_share"]})
    with open(os.path.join(out, "metrics.json"), "w") as fh:
        json.dump(m, fh, indent=1, default=float)
    core_set = set(zip(A.src.astype(int), A.dst.astype(int)))
    print(f"  {scen}/{layer}: links {len(agg):,}, core {int(core.sum())}, hubs {len(hubs)}", flush=True)
    return m, core_set, set(hubs.gid.astype(int))


def _empty_layer(cfg, scen, layer, files, ns, st, n_sites):
    """Metrics row (same keys as a non-empty layer: counts 0, ratios NaN) for a layer without any help link; writes
    metrics.json and network_by_seed.csv only (no edges, nodes, shapefiles or graph)."""
    out = os.path.join(cfg["paths"]["output_dir"], ROOT_SUB, scen, "network", layer)
    os.makedirs(out, exist_ok=True)
    tot_a, tot_r, _, _, _ = ask_stats(files, LAYERS[layer], n_sites)
    nan = np.nan
    m = dict(scenario=scen, layer=layer, seeds=ns, links_any_seed=0, links_freq05=0, core_links=0, core_nodes=0,
             core_largest_component=0, core_communities=0, core_modularity=nan, core_reciprocal_share=nan,
             mh_per_seed=0.0, asks_per_seed=tot_a / ns if ns else nan, refusals_per_seed=tot_r / ns if ns else nan,
             refusal_rate=(tot_r / tot_a) if tot_a else nan, median_link_km=nan, median_link_km_weighted=nan,
             median_core_link_km=nan, n_hubs=0, hub_out_mh_min=nan, hub_share_of_layer_mh=nan, hub_median_haul_m=nan,
             hub_on_outcrop_share=nan, helper_median_haul_m=nan, hub_mean_haul_m=nan, helper_mean_haul_m=nan,
             helper_on_outcrop_share=nan, max_out_degree_any_seed=0,
             **{f"per_seed_{k}_median": float(st[k].median()) if len(st) else nan for k in
                ["nodes", "links", "reciprocal_share", "largest_component", "mean_clustering", "modularity", "helpers",
                 "helpers_serving_ge5", "max_out_degree", "mean_out_degree", "receivers_ge2_helpers", "pass_through_share"]})
    st.to_csv(os.path.join(out, "network_by_seed.csv"), index=False)
    with open(os.path.join(out, "metrics.json"), "w") as fh:
        json.dump(m, fh, indent=1, default=float)
    print(f"  {scen}/{layer}: no help links in any of {ns} seeds -> empty layer, skipped (metrics.json only)", flush=True)
    return m, set(), set()


def _core_recip(A):
    S = set(zip(A.src.astype(int), A.dst.astype(int)))
    return float(np.mean([(b, a) in S for a, b in S])) if S else np.nan


def _wmedian(x, w):
    o = np.argsort(x.to_numpy()); xs = x.to_numpy()[o]; ws = w.to_numpy()[o]
    c = np.cumsum(ws)
    return xs[np.searchsorted(c, c[-1] / 2.0)] if len(xs) else np.nan


def roles(cfg, scen, sub="scenarios_alliance"):
    rd = run_dir(cfg["paths"]["cache_dir"], scen)
    sp = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(rd, "seed_*.spec.csv.gz")))])
    ns = sp.seed.nunique()
    sp["stone"] = sp.given_quarry + sp.given_dress
    sp["transport"] = sp.given_leg1 + sp.given_transport
    sp["build"] = sp.given_build
    sp["track"] = sp.given_track
    cats = ["stone", "transport", "build", "track"]
    tot = sp[cats].sum(axis=1)
    sp["role"] = np.where(tot > 0, sp[cats].idxmax(axis=1), "none")
    sites = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    meta = gpd.read_file(cfg["paths"]["sites"])[["UID", "NAME"]]
    rows = []
    for gid, d in sp.groupby("gid"):
        h = d[d.role != "none"]
        if len(h):
            vc = h.role.value_counts()
            role, cons = vc.index[0], vc.iloc[0] / len(h)
        else:
            role, cons = "none", 0.0
        rows.append((gid, role, round(cons, 3), round(len(h) / ns, 3), *[round(d[c].mean(), 1) for c in cats],
                     round(d.skill_quarry.mean(), 4), round(d.skill_dress.mean(), 4), round(d.skill_build.mean(), 4)))
    r = pd.DataFrame(rows, columns=["gid", "ROLE", "ROLE_CONS", "HELP_FREQ", "GV_STONE", "GV_TRANS", "GV_BUILD",
                                    "GV_TRACK", "SK_QUA", "SK_DRE", "SK_BLD"])
    r.insert(1, "UID", sites.UID.to_numpy()[r.gid]); r.insert(3, "TWR_N", sites.TWR_N.to_numpy()[r.gid])
    r = r.merge(meta, on="UID", how="left")
    r = r[["UID", "NAME", "TWR_N", "ROLE", "ROLE_CONS", "HELP_FREQ", "GV_STONE", "GV_TRANS", "GV_BUILD", "GV_TRACK",
           "SK_QUA", "SK_DRE", "SK_BLD"]]
    out = os.path.join(cfg["paths"]["output_dir"], sub, scen)
    r.to_csv(os.path.join(out, "community_roles.csv"), index=False)
    gpd.GeoDataFrame(r, geometry=gpd.points_from_xy(sites.x, sites.y), crs=cfg["crs"]).to_file(
        os.path.join(out, "community_roles.shp"), engine="pyogrio", encoding="UTF-8")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config"); ap.add_argument("scenarios", nargs="*")
    ap.add_argument("--core-freq", type=float, default=0.5); ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--pre", action="store_true", help="the pre-existing network scenarios (output/scenarios_pre)")
    a = ap.parse_args()
    cfg = load_config(a.config)
    sub = "scenarios_pre" if a.pre else "scenarios_alliance"
    if a.pre:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        import pre_networks
        scens = a.scenarios or [n for n in pre_networks.expand(cfg) if n != "P_none"]
    else:
        scens = a.scenarios or SCEN
    scens = [s for s in scens if run_dir(cfg["paths"]["cache_dir"], s) is not None]   # NEW-3: skip unrun scenarios
    if not scens:
        print("no scenario with a run directory: nothing to do")
        return
    jobs = [(cfg, s, l, a.core_freq, sub) for s in scens for l in LAYERS]
    with Pool(a.jobs) as pool:
        res = pool.map(job, jobs, chunksize=1)
    rows = []
    for s in scens:
        R = {l: r for (cf, sc, l, _, _s), r in zip(jobs, res) if sc == s}
        lay = ["stone", "transport", "build"]
        jac = {}
        for i in range(3):
            for j in range(i + 1, 3):
                x, y = R[lay[i]][1], R[lay[j]][1]
                jac[f"jaccard_core_{lay[i]}_{lay[j]}"] = len(x & y) / len(x | y) if (x | y) else np.nan
        hubsets = [R[l][2] for l in lay]
        allh = set().union(*hubsets)
        multi = sum(1 for h in allh if sum(h in hs for hs in hubsets) > 1)
        rl = roles(cfg, s, sub)
        for l in LAYERS:
            m = dict(R[l][0]); m.update(jac); m["hub_multi_layer_share"] = multi / len(allh) if allh else np.nan
            for role in ("stone", "transport", "build", "track", "none"):
                m[f"roles_{role}"] = int((rl.ROLE == role).sum())
            rows.append(m)
            with open(os.path.join(cfg["paths"]["output_dir"], sub, s, "network", l, "metrics.json"), "w") as fh:
                json.dump(m, fh, indent=1, default=float)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(cfg["paths"]["output_dir"], sub, "network_comparison.csv"), index=False,
              float_format="%.4f")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 80)
    show = ["scenario", "layer", "links_any_seed", "core_links", "core_nodes", "core_largest_component",
            "per_seed_links_median", "per_seed_reciprocal_share_median", "median_link_km", "median_core_link_km",
            "per_seed_helpers_serving_ge5_median", "per_seed_max_out_degree_median", "max_out_degree_any_seed",
            "hub_share_of_layer_mh", "hub_on_outcrop_share", "hub_mean_haul_m", "helper_mean_haul_m", "refusal_rate",
            "per_seed_modularity_median"]
    print("\n================ NETWORK COMPARISON ================")
    print(df[show].to_string(index=False))
    print(df[["scenario", "jaccard_core_stone_transport", "jaccard_core_stone_build", "jaccard_core_transport_build",
              "hub_multi_layer_share", "roles_stone", "roles_transport", "roles_build", "roles_track",
              "roles_none"]].drop_duplicates("scenario").to_string(index=False))


if __name__ == "__main__":
    main()
