"""Centrality of the network scenarios, two layers (specified by the authors).

  python tools/centrality.py [A2_trust A5_full P_G20_system_kmesh4 ...] [--cache REF/cache] [--out-root REF/output]
                             [--out dev_phase/output/centrality] [--k 500] [--no-maps]

Input (no rerun needed): the per-seed alliance pair files cache/runs/alliance_<scen>/<hash>/seed_NNNN.pairs.csv.gz
(the complete, most recent hash dir, as tools/alliance_networks.py). They already log, per unordered pair:
  help_ab / help_ba     man-hours a gave b / b gave a (all stages)          -> COOPERATION layer
  asks_ab / refused_ab  requests a made to b / of which b refused (a Nurnet collaborator's counters, every decision branch)
                        (rows with ask_only = 1 are pairs known only from requests)   -> COMMUNICATION layer
Pre-existing networks (P_*): the scenario's ties (output/scenarios_pre/<scen>/tie_networks.dbf, identical in every run)
are added to the communication layer as 1 request-equivalent per run in both directions (a standing channel).
Layers are mean directed networks over seeds: weight = mean per run (sum over seeds / n seeds); FREQ = share of seeds.
  cooperation   helper -> helped, weight = man-hours
  communication asker -> asked, weight = requests (accepted + refused) [+ ties]
Measures per community:
  OUT_W / IN_W   weighted out/in degree (strength) in the mean network
  OUT_DEG/IN_DEG distinct partners on links present in >= 5% of seeds
  BETWEEN        directed betweenness, links with FREQ >= 0.05, length = 1 / weight, k sampled sources (seed 1), normalised
  EIG            eigenvector centrality of the symmetrised weighted network (dominant eigenvector; concentrates on the
                 strongest component when the network is disconnected, so also:)
  PAGERANK       PageRank of the directed weighted network (alpha 0.85) - defined on disconnected graphs; it ranks the
                 communities that RECEIVE (help / requests), weighted by how central their senders are
Outputs in <out>/<scen>/<layer>/: nodes.csv, centrality.shp (points, all measures), top20.csv (UID, NAME, COMUNE, score
per measure), map_<MEASURE>.png (island outline, nodes sized/coloured by score, top 20 numbered and listed), edges.csv.gz,
summary.json; and <out>/centrality_top20_all.csv across scenarios.
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import eigsh
from scipy.sparse.csgraph import connected_components

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _scen  # noqa: E402

REF = os.environ.get("NURAGHE_PROJECT", ".")
FREQ_MIN = 0.05
MEASURES = ["OUT_W", "IN_W", "BETWEEN", "EIG", "PAGERANK"]
LABEL = {"OUT_W": "weighted out-degree", "IN_W": "weighted in-degree", "BETWEEN": "betweenness",
         "EIG": "eigenvector", "PAGERANK": "PageRank"}
UNIT = {"cooperation": "man-hours per run", "communication": "requests per run"}
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]   # dataviz sequential ramp


def run_dir(cache, scen):
    dirs = [d for d in glob.glob(os.path.join(cache, "runs", f"alliance_{scen}", "*"))
            if glob.glob(os.path.join(d, "seed_*.pairs.csv.gz"))]
    if not dirs:
        raise SystemExit(f"no pair files for {scen}")
    return max(dirs, key=lambda d: (len(glob.glob(os.path.join(d, "*.done"))), os.path.getmtime(d)))


def load_edges(rd):
    files = sorted(glob.glob(os.path.join(rd, "seed_*.pairs.csv.gz")))
    cols = ["a", "b", "help_ab", "help_ba", "asks_ab", "asks_ba", "refused_ab", "refused_ba"]
    coop, comm = [], []
    for f in files:
        p = pd.read_csv(f, usecols=cols)
        for x, y, d in (("a", "b", "ab"), ("b", "a", "ba")):
            h = p[f"help_{d}"].to_numpy()
            k = h > 0
            coop.append(pd.DataFrame({"src": p[x].to_numpy()[k].astype(np.int32), "dst": p[y].to_numpy()[k].astype(np.int32),
                                      "w": h[k].astype(np.float64)}))
            q = p[f"asks_{d}"].to_numpy()
            k = q > 0
            comm.append(pd.DataFrame({"src": p[x].to_numpy()[k].astype(np.int32), "dst": p[y].to_numpy()[k].astype(np.int32),
                                      "w": q[k].astype(np.float64), "ref": p[f"refused_{d}"].to_numpy()[k].astype(np.float64)}))
    ns = len(files)
    out = {}
    for name, L in (("cooperation", coop), ("communication", comm)):
        e = pd.concat(L, ignore_index=True)
        agg = {"w": ("w", "sum"), "freq": ("w", "size")}
        if "ref" in e:
            agg["ref"] = ("ref", "sum")
        g = e.groupby(["src", "dst"]).agg(**agg).reset_index()
        g["w"] /= ns; g["freq"] /= ns
        if "ref" in g:
            g["ref"] /= ns
        out[name] = g
        del e
    return out, ns


def add_ties(comm, out_root, scen, uid_index):
    f = os.path.join(out_root, "scenarios_pre", scen, "tie_networks.dbf")
    if not os.path.exists(f):
        return comm, 0
    import pyogrio
    t = pyogrio.read_dataframe(f, columns=["UID_A", "UID_B"], read_geometry=False)
    a = t.UID_A.map(uid_index).to_numpy(); b = t.UID_B.map(uid_index).to_numpy()
    und = np.unique(np.sort(np.stack([a, b], 1), 1), axis=0)          # a tie in several stage sets counts once
    tie = pd.DataFrame({"src": np.concatenate([und[:, 0], und[:, 1]]), "dst": np.concatenate([und[:, 1], und[:, 0]]),
                        "w": 1.0, "freq": 1.0, "ref": 0.0, "tie": 1})
    comm = comm.assign(tie=0)
    m = pd.concat([comm, tie]).groupby(["src", "dst"]).agg(w=("w", "sum"), freq=("freq", "max"), ref=("ref", "sum"),
                                                         tie=("tie", "max")).reset_index()
    return m, len(und)


def pagerank(N, src, dst, w, alpha=0.85, tol=1e-12, it=500):
    M = sp.csr_matrix((w, (src, dst)), shape=(N, N))
    out = np.asarray(M.sum(1)).ravel()
    inv = np.where(out > 0, 1.0 / np.where(out > 0, out, 1), 0.0)
    P = sp.diags(inv) @ M                                   # row-stochastic on non-dangling rows
    PT = P.T.tocsr()
    x = np.full(N, 1.0 / N)
    dang = out == 0
    for _ in range(it):
        xn = alpha * (PT @ x + x[dang].sum() / N) + (1 - alpha) / N
        if np.abs(xn - x).sum() < tol:
            x = xn; break
        x = xn
    return x / x.sum()


def eigvec(N, src, dst, w):
    A = sp.csr_matrix((w, (src, dst)), shape=(N, N))
    S = (A + A.T).astype(np.float64)
    if S.nnz == 0 or not np.any(S.data):        # 19:45: empty layer (no help / no ties, e.g. _alone_, P_none): all-zero centrality
        return np.zeros(N)
    vals, vecs = eigsh(S, k=1, which="LA")
    v = np.abs(vecs[:, 0])
    return v / v.max() if v.max() > 0 else v


def betweenness(N, e, k):
    import networkx as nx
    f = e[e.freq >= FREQ_MIN]
    G = nx.DiGraph()
    G.add_weighted_edges_from(zip(f.src.tolist(), f.dst.tolist(), (1.0 / f.w).tolist()), weight="dist")
    if G.number_of_nodes() < 3:
        return np.zeros(N), 0
    bc = nx.betweenness_centrality(G, weight="dist", k=min(k, G.number_of_nodes()), seed=1, normalized=True)
    v = np.zeros(N)
    for i, x in bc.items():
        v[i] = x
    return v, G.number_of_edges()


def island_outline(cache_png):
    """DEM footprint (decimated x8), polygonised, as report/make_report.py; cached as GeoJSON."""
    import geopandas as gpd
    if os.path.exists(cache_png):
        return gpd.read_file(cache_png)
    import rasterio
    from rasterio import features
    from shapely.geometry import shape
    sys.path.insert(0, os.path.join(HERE, ".."))
    from nbcommon import load_config
    cfg = load_config(os.path.join(HERE, "..", "config.yaml"))
    dem = os.path.join(cfg["data_dir"], cfg["lit_scenarios"]["dem"])
    with rasterio.open(dem) as r:
        f = 8
        h, wd = r.height // f, r.width // f
        a = r.read(1, out_shape=(h, wd))
        T = r.transform * r.transform.scale(r.width / wd, r.height / h)
        nod = r.nodata
    mask = ((a != nod) & np.isfinite(a)).astype("uint8")
    polys = [shape(s) for s, v in features.shapes(mask, mask=mask == 1, transform=T) if v == 1]
    gs = gpd.GeoDataFrame(geometry=gpd.GeoSeries(polys, crs=cfg["crs"]))
    gs = gs[gs.area > 2e6]
    gs["geometry"] = gs.simplify(250)
    gs.to_file(cache_png, driver="GeoJSON")
    return gs


def draw_map(nodes, m, outline, title, unit, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    v = nodes[m].to_numpy()
    fig = plt.figure(figsize=(11.5, 9.5))
    ax = fig.add_axes([0.0, 0.03, 0.62, 0.9])
    outline.plot(ax=ax, facecolor="#f4f3ef", edgecolor="#b9b8b2", linewidth=0.5, zorder=0)
    ax.scatter(nodes.x, nodes.y, s=0.6, c="#c9c8c2", linewidths=0, zorder=1)
    k = v > 0
    if k.any():
        vmax = np.quantile(v[k], 0.995) if k.sum() > 50 else v[k].max()
        r = np.clip(v[k] / vmax, 0, 1)
        o = np.argsort(r)
        ax.scatter(nodes.x.to_numpy()[k][o], nodes.y.to_numpy()[k][o], s=2 + 60 * np.sqrt(r[o]), c=r[o], cmap=cmap,
                   norm=Normalize(0, 1), edgecolors="white", linewidths=0.25, zorder=2)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=Normalize(0, vmax)); sm.set_array([])
        cax = fig.add_axes([0.06, 0.07, 0.2, 0.012])
        cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
        cb.set_label(f"{LABEL[m]} ({unit})" if m in ("OUT_W", "IN_W") else LABEL[m], fontsize=8, color="#3a3a38")
        cb.ax.tick_params(labelsize=7, colors="#3a3a38"); cb.outline.set_linewidth(0.3)
    top = nodes[k].nlargest(20, m)
    for rank, row in enumerate(top.itertuples(), 1):
        ax.scatter([row.x], [row.y], s=95, facecolors="none", edgecolors="#1a1a19", linewidths=0.8, zorder=3)
        ax.annotate(str(rank), (row.x, row.y), xytext=(4, 3), textcoords="offset points", fontsize=7.5,
                    color="#1a1a19", zorder=4,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75))
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_visible(False)
    fig.text(0.02, 0.965, title, fontsize=12, color="#1a1a19", weight="bold")
    tx = fig.add_axes([0.63, 0.03, 0.36, 0.9]); tx.axis("off")
    tx.text(0, 1, f"Top 20 by {LABEL[m]}", fontsize=9.5, weight="bold", va="top", color="#1a1a19")
    for rank, row in enumerate(top.itertuples(), 1):
        nm = str(row.NAME)[:30]; cm = str(row.COMUNE)[:18]
        tx.text(0, 1 - 0.045 * rank, f"{rank:>2}. {nm} ({cm})", fontsize=7.8, va="top", color="#1a1a19")
        tx.text(1, 1 - 0.045 * rank, f"{getattr(row, m):,.4g}", fontsize=7.8, va="top", ha="right", color="#5e5d59")
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scen", nargs="*", default=["A2_trust", "A5_full"])
    ap.add_argument("--cache", default=os.path.join(REF, "cache"))
    ap.add_argument("--out-root", default=os.path.join(REF, "output"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output", "centrality"))
    ap.add_argument("--k", type=int, default=500, help="betweenness: sampled sources")
    ap.add_argument("--no-maps", action="store_true")
    a = ap.parse_args()
    import geopandas as gpd
    import pyogrio
    o0 = _scen.oom_kill(); t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    haul = pd.read_csv(os.path.join(a.cache, "sites_haul.csv"), usecols=["UID", "TWR_N", "x", "y"])
    meta = pyogrio.read_dataframe(os.path.join(REF, "data", "nurnet_nuraghi.dbf"), columns=["UID", "NAME", "COMUNE"],
                                  read_geometry=False).drop_duplicates("UID")
    nodes0 = haul.merge(meta, on="UID", how="left")
    assert len(nodes0) == len(haul)
    N = len(haul)
    uid_index = {u: i for i, u in enumerate(haul.UID)}
    outline = None if a.no_maps else island_outline(os.path.join(a.out, "island_outline.geojson"))
    tops = []
    for scen in a.scen:
        rd = run_dir(a.cache, scen)
        layers, ns = load_edges(rd)
        nties = 0
        if scen.startswith("P_"):
            layers["communication"], nties = add_ties(layers["communication"], a.out_root, scen, uid_index)
        for layer, e in layers.items():
            od = os.path.join(a.out, scen, layer); os.makedirs(od, exist_ok=True)
            src, dst, w = e.src.to_numpy(), e.dst.to_numpy(), e.w.to_numpy()
            nd = nodes0.copy()
            nd.insert(0, "gid", np.arange(N))
            nd["OUT_W"] = np.bincount(src, w, N); nd["IN_W"] = np.bincount(dst, w, N)
            fr = e.freq.to_numpy() >= FREQ_MIN
            nd["OUT_DEG"] = np.bincount(src[fr], minlength=N); nd["IN_DEG"] = np.bincount(dst[fr], minlength=N)
            if layer == "communication":
                nd["REFUSED_IN"] = np.bincount(dst, e.ref.to_numpy(), N)      # requests this community refused
            tb = time.time()
            nd["BETWEEN"], nbe = betweenness(N, e, a.k)
            tb = time.time() - tb
            nd["EIG"] = eigvec(N, src, dst, w)
            nd["PAGERANK"] = pagerank(N, src, dst, w)
            A = sp.csr_matrix((np.ones(len(src)), (src, dst)), shape=(N, N))
            ncomp, lab = connected_components(A, directed=True, connection="weak")
            active = np.flatnonzero((nd.OUT_W + nd.IN_W).to_numpy() > 0)
            sizes = np.bincount(lab[active]) if active.size else np.zeros(1, int)
            summ = {"scenario": scen, "layer": layer, "run_dir": rd, "seeds": ns, "links_any_seed": int(len(e)),
                    "links_freq05": int(fr.sum()), "betweenness_links": nbe, "betweenness_k": a.k,
                    "betweenness_s": round(tb, 1), "nodes_active": int(active.size),
                    "weak_components_active": int(len(np.unique(lab[active]))), "largest_component": int(sizes.max()),
                    "total_weight_per_run": float(w.sum()), "unit": UNIT[layer], "pre_ties": nties,
                    "eig_note": "network disconnected: EIG concentrates on the dominant component; use PAGERANK"
                    if len(np.unique(lab[active])) > 1 else "connected"}
            json.dump(summ, open(os.path.join(od, "summary.json"), "w"), indent=1)
            e.assign(FROM_UID=haul.UID.to_numpy()[src], TO_UID=haul.UID.to_numpy()[dst]).to_csv(
                os.path.join(od, "edges.csv.gz"), index=False, float_format="%.4g")
            nd.to_csv(os.path.join(od, "nodes.csv"), index=False, float_format="%.6g")
            g = gpd.GeoDataFrame(nd.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(nd.x, nd.y), crs="EPSG:25832")
            g = g.rename(columns={"PAGERANK": "PAGERNK", "REFUSED_IN": "REFUS_IN"})
            g.to_file(os.path.join(od, "centrality.shp"), engine="pyogrio", encoding="UTF-8")
            rows = []
            for m in MEASURES + ["OUT_DEG", "IN_DEG"]:
                for r, row in enumerate(nd.nlargest(20, m).itertuples(), 1):
                    rows.append({"scenario": scen, "layer": layer, "measure": m, "rank": r, "UID": row.UID,
                                 "NAME": row.NAME, "COMUNE": row.COMUNE, "TWR_N": row.TWR_N, "score": getattr(row, m)})
            top = pd.DataFrame(rows); top.to_csv(os.path.join(od, "top20.csv"), index=False, float_format="%.6g")
            tops.append(top)
            if not a.no_maps:
                for m in MEASURES:
                    draw_map(nd, m, outline, f"{scen} - {layer} layer: {LABEL[m]} (mean of {ns} runs)", UNIT[layer],
                             os.path.join(od, f"map_{m}.png"))
            t1 = top[top.measure == "OUT_W"].head(3)
            print(f"  {scen:22s} {layer:13s} links {len(e):7,d} (freq>=5%: {fr.sum():6,d}) active {active.size:5d} "
                  f"comps {summ['weak_components_active']:4d} largest {summ['largest_component']:5d}  "
                  f"top OUT_W: {', '.join(f'{r.NAME} ({r.COMUNE}) {r.score:,.0f}' for r in t1.itertuples())}  "
                  f"[{time.time() - t0:.0f} s, peak {_scen.rss_mb()} MB]", flush=True)
        del layers
    pd.concat(tops).to_csv(os.path.join(a.out, "centrality_top20_all.csv"), index=False, float_format="%.6g")
    print(f"wrote {a.out}; peak RSS {_scen.rss_mb()} MB; oom_kill {o0} -> {_scen.oom_kill()}")


if __name__ == "__main__":
    main()
