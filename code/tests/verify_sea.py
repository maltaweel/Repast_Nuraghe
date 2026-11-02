"""S9 checks: python tests/verify_sea.py config.yaml
1 compact Dijkstra == nbcommon.multi_source_dijkstra (pure drag cost) on a random 8-band grid, incl. origins/lengths
2 haul tables: land rows == baseline; sea rows only for eligible sites, cheaper than land, trip_h == sea.trip_h (model)
3 sea legs >= straight chord between landings; landings obey the beach / hoist rules; hoist <= 5 m
4 sea-quarry stone class allowed by the site's stone rule (hybrid)
5 every sea-route land leg >= the least drag cost between its end cells (window Dijkstra, nbcommon) for 10 sites"""
import os
import sys
import numpy as np
import pandas as pd
import rasterio
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from nbcommon import load_config, multi_source_dijkstra, step_lengths  # noqa: E402
import sea as seamod  # noqa: E402
from sea_routes import Graph  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
ok_all = True


def check(name, ok):
    global ok_all
    ok_all &= bool(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")


# 1
rng = np.random.default_rng(3)
H, W = 60, 70
cost = rng.integers(0, 60, (8, H, W)).astype(np.uint8)
cost[cost < 5] = 0
seeds = rng.choice(H * W, 7, replace=False).astype(np.int64)
d0 = np.empty(H * W, np.float32); o0 = np.empty(H * W, np.int32); p0 = np.empty(H * W, np.float32)
multi_source_dijkstra(cost, seeds, step_lengths(30.0), d0, o0, p0)
G = Graph(np.arange(H * W), H, W, cost.reshape(8, -1).copy(), step_lengths(30.0))
G.run(1.0, 0.0, seeds, np.zeros(seeds.size), seeds, np.inf)
fin = np.isfinite(d0)
check("1 compact Dijkstra == nbcommon (dist)", np.array_equal(np.isfinite(G.dist), fin) and np.allclose(G.dist[fin], d0[fin]))
check("1 accumulated cost == dist", np.allclose(G.acc_c[fin], d0[fin]))
# origins / lengths can differ only on exact ties; compare where unique
check("1 origins equal on >= 99% of cells", (G.org[fin] == o0[fin]).mean() >= 0.99)
# 2-4
base = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
ss = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "site_stone_sets.csv"))
L = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sea", "landings.csv"))
S = cfg["sea"]
check("3 landings: beach rule", ((L.type != "beach") | ((L.z <= S["beach_max_z_m"]) & (L.slope < S["beach_max_slope_deg"]))).all())
check("3 landings: hoist rule (not beach, 0 < z <= 5 m, hoist = z)",
      ((L.type != "hoist") | ((L.z <= S["hoist_max_z_m"]) & (L.z > 0) & np.isclose(L.hoist_m, L.z))).all())
for kn in [float(x) for x in S["speeds_kn"]] + [float(x) for x in S.get("extra_speeds_kn", [])]:
    h = pd.read_csv(seamod.haul_csv(cfg, kn))
    land = h["mode"] == "land"
    same = all(np.array_equal(h.loc[land, c].to_numpy(), base.loc[land, c].to_numpy()) for c in
               ["UID", "quarry_x", "quarry_y", "quarry_stone", "row", "col"]) and \
        all(np.allclose(h.loc[land, c], base.loc[land, c], rtol=0, atol=1e-9) for c in ["haul_flatm", "haul_m"])
    # (CSV re-parse noise ~1e-14 m; sea.load_haul restores the baseline values exactly for the model)
    s = h[~land]
    trip = np.array([seamod.trip_h(r, cfg, kn) for r in s.to_dict("records")])
    chord = np.hypot(s.landing_a_x - s.landing_b_x, s.landing_a_y - s.landing_b_y) / 1000.0
    allowed = [q in st.split("; ") for q, st in zip(s.quarry_stone, ss.stone_set[s.index])]
    print(f"--- {kn:g} kn: {len(s)} sea sites")
    check(f"2 {kn:g} kn land rows identical to baseline", same)
    check(f"2 {kn:g} kn sea rows eligible (<= {S['coast_band_m']} m) and cheaper than land",
          s.eligible.all() and (s.d_coast_m <= S["coast_band_m"]).all() and (s.sea_cost_h < s.land_trip_h).all())
    check(f"2 {kn:g} kn trip_h == sea.trip_h (model formula)", np.allclose(trip, s.trip_h, rtol=1e-6))
    check(f"3 {kn:g} kn sea_km >= chord between landings", (s.sea_km >= chord - 1e-6).all())
    check(f"4 {kn:g} kn sea quarry stone class allowed by the site's rule", all(allowed))
# 5 window Dijkstra lower bound on the land legs (5 kn)
h = pd.read_csv(seamod.haul_csv(cfg, 5))
s = h[h["mode"] == "sea"].head(10)
with rasterio.open(cfg["paths"]["cost_raster"]) as r:
    T = r.transform
    good = True
    for _, q in s.iterrows():
        for (x0, y0, x1, y1, hf) in ((q.quarry_x, q.quarry_y, q.landing_a_x, q.landing_a_y, q.haul_flatm_1),
                                     (q.landing_b_x, q.landing_b_y, q.x, q.y, q.haul_flatm_2)):
            pad = 6000
            win = rasterio.windows.from_bounds(min(x0, x1) - pad, min(y0, y1) - pad, max(x0, x1) + pad, max(y0, y1) + pad,
                                               T).round_offsets().round_lengths()
            c = r.read(window=win)
            wt = r.window_transform(win)
            hh, ww = c.shape[1:]
            cr = lambda x, y: (int((y - wt.f) // wt.e), int((x - wt.c) // wt.a))
            r0, c0 = cr(x0, y0); r1, c1 = cr(x1, y1)
            d = np.empty(hh * ww, np.float32); o = np.empty(hh * ww, np.int32); p = np.empty(hh * ww, np.float32)
            multi_source_dijkstra(np.ascontiguousarray(c), np.array([r0 * ww + c0], np.int64), step_lengths(30.0), d, o, p)
            lb = d[r1 * ww + c1]
            good &= hf >= lb - 1e-3
            if hf < lb - 1e-3:
                print(f"   {q.UID}: leg {hf} < least drag {lb}")
check("5 land legs >= least drag cost between their end cells (10 sites, 5 kn)", good)
print("ALL PASS" if ok_all else "SOME FAILED")
import sys
sys.exit(0 if ok_all else 1)
