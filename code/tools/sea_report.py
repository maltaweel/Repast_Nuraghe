"""S9 sanity numbers on the full-island sea haul tables + maps (no simulation).

  python tools/sea_report.py config.yaml

Prints per speed: eligible sites, sites switching to sea, their median land vs sea trip and transport man-hours,
island stone-weighted haul flat-m and estimated transport man-hours (land vs sea-aware). Writes
output/sea/sea_switch_summary.csv, sea_landings.png, sea_switch_sites.png.
Transport MH estimate per site = towers x (crew-trips per tower) x trip_h + hoist, with crew-trips per tower =
tonnes_per_tower x 1000 / mean block kg x mean crew per block (the block draw; the ABM gives the exact value).
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402

BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#b9b8b0"


def main(cfg_path):
    cfg = load_config(cfg_path)
    P = cfg["paths"]
    sd = os.path.join(P["cache_dir"], "sea")
    od = os.path.join(P["output_dir"], "sea")
    os.makedirs(od, exist_ok=True)
    meta = json.load(open(os.path.join(sd, "sea_meta.json")))
    prm = meta["params"]
    crew_trips_tower = cfg["stone"]["tonnes_per_tower"] * 1000.0 / prm["mean_block_kg"] * prm["mean_crew"]
    blocks_tower = cfg["stone"]["tonnes_per_tower"] * 1000.0 / prm["mean_block_kg"]
    print(f"landings: {meta['n_landings']:,} cells (beach {meta['n_beach']:,}, hoist {meta['n_hoist']:,}); "
          f"eligible sites (<= {prm['coast_band_m']:.0f} m of the coast): {meta['n_eligible_sites']}")
    print(f"crew-trips per tower (estimate) {crew_trips_tower:,.0f}; blocks per tower {blocks_tower:,.0f}")
    rows = []
    tabs = {}
    for kn in meta["speeds"]:
        h = pd.read_csv(os.path.join(sd, f"sites_haul_sea{kn:g}kn.csv"))
        tabs[kn] = h
        s = h[h["mode"] == "sea"]
        mh_land = h.TWR_N * crew_trips_tower * h.land_trip_h
        mh_new = h.TWR_N * (crew_trips_tower * h.trip_h + blocks_tower * prm["hoist_ph_per_block_m"] * h.hoist_m)
        fl_land = (h.TWR_N * h.land_haul_flatm).sum()
        fl_new = (h.TWR_N * h.haul_flatm).sum()
        r = {"kn": kn, "eligible": int(h.eligible.sum()), "sea_sites": len(s), "sea_towers": int(s.TWR_N.sum()),
             "hoist_landings_used": int((s.landing_a_type == "hoist").sum() + (s.landing_b_type == "hoist").sum()),
             "median_land_haul_flatm": s.land_haul_flatm.median(), "median_sea_land_legs_flatm": s.haul_flatm.median(),
             "median_sea_km": s.sea_km.median(), "median_land_trip_h": s.land_trip_h.median(),
             "median_sea_trip_h": s.trip_h.median(),
             "median_land_mh_site": mh_land[s.index].median(), "median_sea_mh_site": mh_new[s.index].median(),
             "island_flatm_land": fl_land, "island_flatm_sea": fl_new, "island_flatm_change_pct": 100 * (fl_new / fl_land - 1),
             "island_transport_mh_land": mh_land.sum(), "island_transport_mh_sea": mh_new.sum(),
             "island_transport_mh_change_pct": 100 * (mh_new.sum() / mh_land.sum() - 1),
             "switching_sites_mh_change_pct": 100 * (mh_new[s.index].sum() / mh_land[s.index].sum() - 1)}
        base = pd.read_csv(os.path.join(P["cache_dir"], "sites_haul.csv")).set_index("UID")
        bq = base.loc[s.UID]
        r["quarry_changed"] = int(((bq.quarry_row.to_numpy() != s.quarry_row.to_numpy()) |
                                   (bq.quarry_col.to_numpy() != s.quarry_col.to_numpy())).sum())
        r["stone_class_changed"] = int((bq.quarry_stone.to_numpy() != s.quarry_stone.to_numpy()).sum())
        rows.append(r)
        print(f"{kn:g} kn: sea for {len(s)} of {r['eligible']} eligible sites ({r['sea_towers']} towers); "
              f"median land haul {r['median_land_haul_flatm']:.0f} flat-m vs sea route land legs {r['median_sea_land_legs_flatm']:.0f} "
              f"flat-m + {r['median_sea_km']:.1f} km by boat; median trip {r['median_land_trip_h']:.2f} h land vs "
              f"{r['median_sea_trip_h']:.2f} h sea; median site transport MH {r['median_land_mh_site']:,.0f} vs "
              f"{r['median_sea_mh_site']:,.0f}; quarry cell changed {r['quarry_changed']}, stone class changed "
              f"{r['stone_class_changed']}; hoist landings used {r['hoist_landings_used']}")
        print(f"      island stone-weighted drag flat-m {fl_land:,.0f} -> {fl_new:,.0f} ({r['island_flatm_change_pct']:+.2f}%); "
              f"island transport MH (estimate) {mh_land.sum():,.0f} -> {mh_new.sum():,.0f} "
              f"({r['island_transport_mh_change_pct']:+.2f}%); switching sites {r['switching_sites_mh_change_pct']:+.1f}%")
    pd.DataFrame(rows).to_csv(os.path.join(od, "sea_switch_summary.csv"), index=False)

    # ---- maps
    with rasterio.open(os.path.join(cfg["data_dir"], cfg["sea"]["dem"])) as r:
        f = 6
        z = r.read(1, out_shape=(r.height // f, r.width // f))
        T = r.transform
    land = z > 0
    ext = [T.c, T.c + T.a * r.width, T.f + T.e * r.height, T.f]
    L = pd.read_csv(os.path.join(sd, "landings.csv"))

    def base_ax(ax):
        ax.imshow(np.where(land, 1.0, np.nan), extent=ext, cmap=matplotlib.colors.ListedColormap(["#efeee8"]), interpolation="nearest")
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#cfcec6")

    fig, axs = plt.subplots(1, 2, figsize=(13, 11), gridspec_kw={"width_ratios": [1, 1]})
    ax = axs[0]
    base_ax(ax)
    b = L[L.type == "beach"]; hh = L[L.type == "hoist"]
    ax.scatter(b.x, b.y, s=0.4, c=BLUE, lw=0, label=f"beach (z <= 10 m, slope < 10 deg): {len(b):,} cells ({100 * len(b) / len(L):.0f}%)")
    ax.scatter(hh.x, hh.y, s=0.4, c=ORANGE, lw=0, label=f"hoist (cliff top <= 5 m): {len(hh):,} cells ({100 * len(hh) / len(L):.0f}%)")
    ax.set_title("S9 landings (30 m coastal land cells)", loc="left", fontsize=12)
    ax.legend(loc="lower left", markerscale=12, frameon=False, fontsize=9)
    # zoom: the densest hoist window (20 km)
    ax = axs[1]
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    gx = (hh.x // 20000).astype(int); gy = (hh.y // 20000).astype(int)
    cx, cy = pd.Series(list(zip(gx, gy))).value_counts().index[0]
    x0, y0 = cx * 20000, cy * 20000
    m = (L.x > x0 - 5000) & (L.x < x0 + 25000) & (L.y > y0 - 5000) & (L.y < y0 + 25000)
    with rasterio.open(os.path.join(cfg["data_dir"], cfg["sea"]["dem"])) as r:
        win = rasterio.windows.from_bounds(x0 - 5000, y0 - 5000, x0 + 25000, y0 + 25000, r.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, r.width, r.height))   # clip at the raster edge
        zz = r.read(1, window=win)
        wl, wb, wr, wt = r.window_bounds(win)
    ax.imshow(np.where(zz > 0, 1.0, np.nan), extent=[wl, wr, wb, wt],
              cmap=matplotlib.colors.ListedColormap(["#efeee8"]), interpolation="nearest")
    lb = L[m & (L.type == "beach")]; lh = L[m & (L.type == "hoist")]
    ax.scatter(lb.x, lb.y, s=3, c=BLUE, lw=0, label="beach")
    ax.scatter(lh.x, lh.y, s=5, c=ORANGE, lw=0, label="hoist")
    ax.set_xlim(x0 - 5000, x0 + 25000); ax.set_ylim(y0 - 5000, y0 + 25000)
    ax.set_title(f"Zoom 30 x 30 km (densest hoist area, E {x0 / 1000:.0f} N {y0 / 1000:.0f} km)", loc="left", fontsize=12)
    ax.legend(loc="lower left", markerscale=3, frameon=False, fontsize=9)
    axs[0].add_patch(plt.Rectangle((x0 - 5000, y0 - 5000), 30000, 30000, fill=False, ec="#444441", lw=1))
    fig.tight_layout()
    fig.savefig(os.path.join(od, "sea_landings.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 13))
    base_ax(ax)
    h5 = tabs[float(cfg["sea"]["default_kn"])]
    ax.scatter(h5.x, h5.y, s=1.5, c=GREY, lw=0, label="nuraghe (land route)")
    e = h5[h5.eligible & (h5["mode"] == "land")]
    ax.scatter(e.x, e.y, s=3, c="#7d7c75", lw=0, label=f"within {prm['coast_band_m'] / 1000:.0f} km of the coast, land still cheaper ({len(e)})")
    s = h5[h5["mode"] == "sea"]
    for _, q in s.iterrows():
        ax.plot([q.quarry_x, q.landing_a_x], [q.quarry_y, q.landing_a_y], c=ORANGE, lw=0.8)
        ax.plot([q.landing_a_x, q.landing_b_x], [q.landing_a_y, q.landing_b_y], c=BLUE, lw=0.8, ls=(0, (3, 2)))
        ax.plot([q.landing_b_x, q.x], [q.landing_b_y, q.y], c=ORANGE, lw=0.8)
    ax.plot([], [], c=ORANGE, lw=1, label="drag leg (quarry -> landing, landing -> site)")
    ax.plot([], [], c=BLUE, lw=1, ls=(0, (3, 2)), label="boat leg (landing a -> landing b, straight chord; route hugs coast)")
    other = {kn: set(t.UID[t["mode"] == "sea"]) for kn, t in tabs.items()}
    only6 = other.get(6.0, set()) - set(s.UID)
    ax.scatter(s.x, s.y, s=22, c=BLUE, edgecolors="white", linewidths=0.8, zorder=5, label=f"switches to sea at 5 kn ({len(s)})")
    if only6:
        o = tabs[6.0][tabs[6.0].UID.isin(only6)]
        ax.scatter(o.x, o.y, s=22, c=AQUA, edgecolors="white", linewidths=0.8, zorder=5, label=f"switches only at 6 kn ({len(o)})")
    gone4 = set(s.UID) - other.get(4.0, set())
    if gone4:
        o = h5[h5.UID.isin(gone4)]
        ax.scatter(o.x, o.y, s=40, facecolors="none", edgecolors="#444441", linewidths=1, zorder=6, label=f"not at 4 kn ({len(o)})")
    cnt = ", ".join(f"{kn:g} kn {len(other[kn])}" for kn in sorted(other))
    ax.set_title(f"S9: nuraghi whose stone comes cheaper by sea\n(sites switching: {cnt})", loc="left", fontsize=12)
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(od, "sea_switch_sites.png"), dpi=150)
    plt.close(fig)
    print(f"wrote {od}/sea_switch_summary.csv, sea_landings.png, sea_switch_sites.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
