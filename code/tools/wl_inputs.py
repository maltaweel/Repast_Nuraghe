"""Wider-literature scenarios (1 Nov 2026 b): inputs along the k-best quarry routes of cache/alliance/kbest.npz.

  python tools/wl_inputs.py CFG

(1) Per-move drag cost (flat-metre equivalents) at extra friction coefficients, on the SAME routes (found at mu 0.3),
    for the sledge on wetted sand (M3; Fall et al. 2014: 175502-3/-4: dynamic friction down 10-40% by sand, "almost a
    factor of 2" at best):  mu 0.2812 = 0.38 x (1 - 0.26);  mu 0.228 = 0.38 x (1 - 0.40);  mu 0.19 = 0.38 / 2.
    Same arithmetic as tools/build_cost_mu.py (float32: t = clip((z_nb - z) / d, -1, 1); cost = max(0.5, |mu + t| / mu) * d;
    np.rint), but evaluated only on the route moves, from the DEM. CHECK: the same code at mu 0.3 and mu 0.38 must give
    exactly the stored mv_c03 (kbest.npz) and mv_c038 (kbest_mu038.npz), else the script stops.
(2) Distance of every route move (its from-cell) and every site cell to the nearest mapped stream (RAS 'fiumitorrenti'
    layer, water/sardinia_rivers_25832.shp; modern network used as a proxy for Bronze Age water courses), on the DEM grid
    (rasterised all_touched, Euclidean distance transform x 30 m). Per route: share of its length within 250 / 500 /
    1000 m of a stream.
(3) Wettable sand (M3): route moves whose from-cell lies on loose sandy deposits of the ARPAS lithology (DESC_EN
    'Alluvial fan/plain deposits', 'Beach deposits', 'Wind-blown sands') AND within 500 m of a mapped stream or of the
    sea (water within carrying distance: ASSUMPTION). Per route: share of its length on wettable sand; per site: its cell.
Writes cache/alliance/kbest_wl.npz.
"""
import os
import sys

import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from scipy import ndimage

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import DIRS, load_config  # noqa: E402

MUS = {"c019": 0.19, "c0281": 0.38 * (1 - 0.26), "c0228": 0.38 * (1 - 0.40)}
SANDS = ("Alluvial fan/plain deposits", "Beach deposits", "Wind-blown sands")
DISTS = (250, 500, 1000)


def main():
    cfg = load_config(sys.argv[1])
    P = cfg["paths"]
    kb = np.load(os.path.join(P["cache_dir"], "alliance", "kbest.npz"))
    k38 = np.load(os.path.join(P["cache_dir"], "alliance", "kbest_mu038.npz"))
    meta = pd.DataFrame(kb["meta"])
    W = int(kb["W"])
    ptr, cell = kb["ptr"], kb["mv_cell"]
    h = pd.read_csv(os.path.join(P["cache_dir"], "sites_haul.csv"))
    site_cell = (h.row.to_numpy().astype(np.int64) * W + h.col.to_numpy().astype(np.int64))
    nxt = np.empty_like(cell)
    nxt[:-1] = cell[1:]
    nonempty = ptr[1:] > ptr[:-1]
    last = (ptr[1:] - 1)[nonempty]
    nxt[last] = site_cell[meta.gid.to_numpy()[nonempty]]
    dr = nxt // W - cell // W
    dc = nxt % W - cell % W
    dlook = {(int(a), int(b)): k for k, (a, b) in enumerate(DIRS)}
    code = np.array([dlook[(int(a), int(b))] for a, b in zip(dr, dc)], np.int64)
    rr, cc = cell // W, cell % W
    dem = os.path.join(cfg["data_dir"], cfg["lit_scenarios"]["dem"])
    with rasterio.open(dem) as r:
        z = r.read(1).astype("float32"); nod = r.nodata; res = r.res[0]; tr = r.transform; shp = r.shape
        assert np.allclose(np.array(tr)[:6], kb["transform"]), "DEM grid != kbest grid"
    z[(z == nod) | ~np.isfinite(z)] = np.nan

    def cost(mu):
        out = np.zeros(cell.size, np.int32)
        for k, (a, b) in enumerate(DIRS):
            m = code == k
            if not m.any():
                continue
            d = res * (2 ** 0.5 if a and b else 1.0)
            z0 = z[rr[m], cc[m]]
            z1 = z[rr[m] + a, cc[m] + b]
            t = np.clip((z1 - z0) / d, -1, 1)
            c = (np.maximum(0.5, np.abs(mu + t) / mu) * d).astype("float32")
            out[m] = np.where(np.isfinite(c), np.rint(c), 0).astype(np.int32)
        return out
    ok03 = bool(np.array_equal(cost(0.3), kb["mv_c03"]))
    ok38 = bool(np.array_equal(cost(0.38), k38["mv_c038"]))
    print(f"CHECK route-move recomputation: mu 0.3 == stored mv_c03: {ok03}; mu 0.38 == stored mv_c038: {ok38}", flush=True)
    if not (ok03 and ok38):
        sys.exit("recomputation differs from the stored move costs: stop")
    out = {}
    for key, mu in MUS.items():
        out["mv_" + key] = cost(mu)
        cs = np.concatenate([[0], np.cumsum(out["mv_" + key].astype(np.int64))])
        rc = cs[ptr[1:]] - cs[ptr[:-1]]
        rat = rc / np.maximum(meta.cost03.to_numpy(), 1)
        print(f"mu {mu:.4f}: route cost / mu 0.3 cost median {np.median(rat):.3f} (p10 {np.percentile(rat, 10):.3f}, "
              f"p90 {np.percentile(rat, 90):.3f})", flush=True)
    sea = ~np.isfinite(z)
    del z
    # streams
    import pyogrio
    riv = pyogrio.read_dataframe(os.path.join(cfg["data_dir"], "water", "sardinia_rivers_25832.shp"))
    ras = features.rasterize(((g, 1) for g in riv.geometry if g is not None), out_shape=shp, transform=tr,
                             all_touched=True, dtype="uint8")
    dist = ndimage.distance_transform_edt(ras == 0).astype(np.float32) * float(res)
    del ras
    dmv = dist[rr, cc]
    out["mv_dstream"] = dmv
    out["site_dstream"] = dist[h.row.to_numpy(), h.col.to_numpy()]
    ln = kb["mv_len"].astype(np.float64)
    cl = np.concatenate([[0], np.cumsum(ln)])
    tot = cl[ptr[1:]] - cl[ptr[:-1]]
    for D in DISTS:
        cw = np.concatenate([[0], np.cumsum(ln * (dmv <= D))])
        out[f"site_wet{D}"] = (out["site_dstream"] <= D).astype(np.float64)
        out[f"route_wet{D}"] = np.where(tot > 0, (cw[ptr[1:]] - cw[ptr[:-1]]) / np.maximum(tot, 1e-9), np.nan)
        print(f"streams <= {D} m: sites {np.mean(out['site_dstream'] <= D):.1%}; route moves {np.mean(dmv <= D):.1%}",
              flush=True)
    dsea = ndimage.distance_transform_edt(~sea).astype(np.float32) * float(res)
    lit_ = pyogrio.read_dataframe(os.path.join(cfg["data_dir"], cfg["paths"]["lithology"]), columns=["DESC_EN"])
    lit_ = lit_[lit_.DESC_EN.isin(SANDS)]
    sand = features.rasterize(((g, 1) for g in lit_.geometry if g is not None), out_shape=shp, transform=tr,
                              dtype="uint8").astype(bool)
    wetsand = sand & ((dist <= 500) | (dsea <= 500))
    del dsea, sand
    ws = wetsand[rr, cc]
    cw = np.concatenate([[0], np.cumsum(ln * ws)])
    out["route_sandwet500"] = np.where(tot > 0, (cw[ptr[1:]] - cw[ptr[:-1]]) / np.maximum(tot, 1e-9), np.nan)
    out["site_sandwet500"] = wetsand[h.row.to_numpy(), h.col.to_numpy()].astype(np.float64)
    print(f"wettable sand (sandy deposits within 500 m of a stream or the sea): {wetsand.mean():.1%} of grid cells; "
          f"sites {out['site_sandwet500'].mean():.1%}; route moves {ws.mean():.1%}", flush=True)
    print(f"rivers: {len(riv):,d} segments; site distance to a stream median {np.median(out['site_dstream']):.0f} m",
          flush=True)
    np.savez_compressed(os.path.join(P["cache_dir"], "alliance", "kbest_wl.npz"), **out)


if __name__ == "__main__":
    main()
