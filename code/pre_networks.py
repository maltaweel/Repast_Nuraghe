"""Pre-existing networks (config.yaml -> pre_networks): tie sets that exist before any building starts.

Requests go ONLY along ties (accepted with p_tie, no trust needed), up to `reach` ties away (brokers add a walk).
Everything else is the alliance model (A2 rules: stage tasks, relays, helper walking, seasons, phasing, quarry setup,
learning by doing on own towers). Tie sets are fixed per scenario (generator_seed), the same in every run.

Groups: seeded contiguous spatial clusters (k-means on site coordinates, k = round(N / size)), or nearest-seed
assignment for G3_canton (seeds = multi-tower nuraghi) and for the location variants (seeds drawn from on- or
off-outcrop sites). G133_tribe is two-level: canton groups merged into tribes by k-means on the canton seats.
Shapes inside a group: chain, kmesh2/4/8, hub, smallworld, complete; or `partners` (k nearest, no groups).
"""
import math

import numpy as np
import pandas as pd
from scipy.cluster.vq import kmeans2
from scipy.spatial import cKDTree

STAGE_SETS = ("stone", "move", "build")          # stone = quarry + dress; move = relay leg 1; build = build/lift


def expand(cfg):
    """All pre-network scenario definitions: the main grid plus the explicit extras (self-contained for GPU sweeps)."""
    P = cfg["pre_networks"]
    out = {"P_none": {"all": None}}
    for size in P["main_grid"]["sizes"]:
        for shape in P["main_grid"]["shapes"]:
            out[f"P_{size}_{shape}"] = {"all": {"groups": size, "shape": shape}}
    out.update({k: v for k, v in (P.get("extra") or {}).items()})
    return out


def sens_expand(cfg):
    P = cfg["pre_networks"]; G = P["sensitivity"]
    out = {}
    for size in G["sizes"]:
        for shape in G["shapes"]:
            for h in G["reach"]:
                for lr in G["learning"]:
                    d = {"all": {"groups": size, "shape": shape}, "reach": h}
                    if lr:
                        d["specialisation"] = True
                    out[f"PS_{size}_{shape}_h{h}_{'L' if lr else 'N'}"] = d
    return out


def scenario_spec(cfg, name):
    if name in expand(cfg):
        return expand(cfg)[name]
    return sens_expand(cfg)[name]


# ----------------------------------------------------------------------------------- groups
def _hub(members, xy, tw):
    m = np.asarray(members)
    best = tw[m].max()
    cand = m[tw[m] == best]
    if len(cand) == 1:
        return int(cand[0])
    c = xy[m].mean(axis=0)
    tot = [np.hypot(*(xy[m] - xy[j]).T).sum() for j in cand]
    return int(cand[int(np.argmin(tot))])


def groups(cfg, haul, gname, seed_from=None):
    """Group label per site (int array)."""
    P = cfg["pre_networks"]
    G = P["sizes"][gname]
    xy = haul[["x", "y"]].to_numpy() / 1000.0
    N = len(haul)
    rng = np.random.default_rng(int(P["generator_seed"]))
    if G.get("seed_rule") == "multi_tower" and seed_from is None:
        seeds = np.flatnonzero(haul.TWR_N.to_numpy() >= 2)
        lab = cKDTree(xy[seeds]).query(xy)[1]
        return lab
    if G.get("two_level"):
        can = groups(cfg, haul, G["two_level"])
        seats = np.flatnonzero(haul.TWR_N.to_numpy() >= 2)          # canton seats = the multi-tower seeds
        k = max(1, int(round(N / G["size"])))
        _, sl = kmeans2(xy[seats], k, seed=int(P["generator_seed"]), minit="++", iter=30)
        return sl[can]                                              # every member inherits its canton's tribe
    k = max(1, int(round(N / G["size"])))
    if seed_from is not None:
        elig = np.flatnonzero(haul.on_outcrop.to_numpy() == (seed_from == "on_outcrop"))
        seeds = rng.choice(elig, size=min(k, len(elig)), replace=False)
        return cKDTree(xy[seeds]).query(xy)[1]
    _, lab = kmeans2(xy, k, seed=int(P["generator_seed"]), minit="++", iter=30)
    return lab


def _shape_edges(members, shape, xy, tw, P, rng, outside_tree=None, lab=None, gid=None):
    m = np.asarray(members)
    E = set()
    if len(m) < 2:
        return E
    if shape == "chain":
        rest = list(m); cur = _hub(m, xy, tw); rest.remove(cur)
        while rest:
            d = np.hypot(*(xy[rest] - xy[cur]).T)
            nxt = rest[int(np.argmin(d))]
            E.add((min(cur, nxt), max(cur, nxt))); rest.remove(nxt); cur = nxt
    elif shape.startswith("kmesh") or shape == "smallworld":
        k = 4 if shape == "smallworld" else int(shape[5:])
        t = cKDTree(xy[m])
        _, nn = t.query(xy[m], k=min(k + 1, len(m)))
        nn = np.atleast_2d(nn)
        for a, row in zip(m, nn):
            for b in m[row[1:]]:
                E.add((min(a, b), max(a, b)))
        if shape == "smallworld":
            p = float(P["smallworld_p"]); R = float(P["smallworld_radius_m"]) / 1000.0
            out = set()
            for (a, b) in sorted(E):
                if rng.random() < p:
                    cand = [j for j in outside_tree.query_ball_point(xy[a], r=R) if lab[j] != gid]
                    if cand:
                        j = int(cand[int(rng.integers(len(cand)))])
                        out.add((min(a, j), max(a, j))); continue
                out.add((a, b))
            E = out
    elif shape == "hub":
        h = _hub(m, xy, tw)
        for a in m:
            if a != h:
                E.add((min(a, h), max(a, h)))
    elif shape == "complete":
        mm = sorted(m)
        for i, a in enumerate(mm):
            for b in mm[i + 1:]:
                E.add((a, b))
    else:
        raise ValueError(shape)
    return E


def tie_set(cfg, haul, spec):
    """One tie set (edge set) from a spec {groups, shape} | {partners: k} | {..., seed_from, region}."""
    P = cfg["pre_networks"]
    xy = haul[["x", "y"]].to_numpy() / 1000.0
    tw = haul.TWR_N.to_numpy()
    N = len(haul)
    rng = np.random.default_rng(int(P["generator_seed"]) + 1)
    E = set()
    lab = np.full(N, -1)
    hubs = set()
    if "partners" in spec:
        k = int(spec["partners"])
        if k <= 0:                                                 # NEW-5: an explicit error, not a silent empty set
            raise ValueError(f"pre_networks: partners must be >= 1, got {spec['partners']!r}")
        k_eff = min(k, N - 1)                                      # NEW-5: k >= N would add the missing-neighbour index N
        if k_eff > 0:
            _, nn = cKDTree(xy).query(xy, k=k_eff + 1)
            for a, row in enumerate(nn):
                for b in row[1:]:
                    E.add((min(a, int(b)), max(a, int(b))))
    else:
        gname, shape = spec["groups"], spec["shape"]
        lab = groups(cfg, haul, gname, spec.get("seed_from"))
        tree = cKDTree(xy)
        G = P["sizes"][gname]
        if G.get("two_level") and shape == "hub":                  # tribe hub over canton hubs
            can = groups(cfg, haul, G["two_level"])
            for c in np.unique(can):
                m = np.flatnonzero(can == c)
                E |= _shape_edges(m, "hub", xy, tw, P, rng)
                hubs.add(_hub(m, xy, tw))
            for t in np.unique(lab):
                seats = [h for h in hubs if lab[h] == t]
                if len(seats) > 1:
                    th = _hub(np.array(seats), xy, tw)
                    for s_ in seats:
                        if s_ != th:
                            E.add((min(s_, th), max(s_, th)))
        else:
            for gid in np.unique(lab):
                m = np.flatnonzero(lab == gid)
                E |= _shape_edges(m, shape, xy, tw, P, rng, tree, lab, gid)
                if len(m):
                    hubs.add(_hub(m, xy, tw))
    E = {(a, b) for (a, b) in E if a != b}           # no self-ties (coincident sites can be their own k-nearest)
    reg = spec.get("region")
    if reg:
        keep = region_mask(cfg, haul, reg)
        E = {(a, b) for (a, b) in E if keep[a] and keep[b]}
    return E, lab, hubs


def region_mask(cfg, haul, reg):
    """north / central / south = latitude thirds (PROVINCIA mixes two administrative schemes, see the data README);
    dense = sites in 30 km cells whose nuraghe count is in the top tercile of occupied cells."""
    y = haul.y.to_numpy()
    q1, q2 = np.quantile(y, [1 / 3, 2 / 3])
    if reg == "north":
        return y >= q2
    if reg == "central":
        return (y >= q1) & (y < q2)
    if reg == "south":
        return y < q1
    if reg == "dense":
        c = float(cfg["pre_networks"]["density_cell_m"])
        cx = np.floor(haul.x.to_numpy() / c).astype(int); cy = np.floor(y / c).astype(int)
        key = cx * 100000 + cy
        cnt = pd.Series(key).value_counts()
        thr = np.quantile(cnt.to_numpy(), 2 / 3)
        return pd.Series(key).map(cnt).to_numpy() > thr
    raise ValueError(reg)


def build(cfg, haul, spec):
    """Adjacency per stage set: {'stone': [sorted np arrays], 'move': [...], 'build': [...]}, plus edge lists."""
    N = len(haul)
    per = {}
    info = {}
    if spec.get("all", "missing") is None:                       # P_none: empty tie sets
        sets = {s: (set(), np.full(N, -1), set()) for s in STAGE_SETS}
    elif "all" in spec:
        E = tie_set(cfg, haul, spec["all"])
        sets = {s: E for s in STAGE_SETS}
    else:
        sets = {s: tie_set(cfg, haul, spec[s]) for s in STAGE_SETS}
    cache = {}
    for s in STAGE_SETS:
        E, lab, hubs = sets[s]
        key = id(sets[s])
        if key not in cache:                                    # one shared adjacency when stages share a tie set
            a = np.array(sorted(E), dtype=np.int32).reshape(-1, 2)
            src = np.concatenate([a[:, 0], a[:, 1]]); dst = np.concatenate([a[:, 1], a[:, 0]])
            o = np.lexsort((dst, src))
            src, dst = src[o], dst[o]
            ptr = np.searchsorted(src, np.arange(N + 1))
            cache[key] = ([dst[ptr[i]:ptr[i + 1]] for i in range(N)], {"edges": a, "groups": lab, "hubs": hubs})
        per[s], info[s] = cache[key]
    return per, info
