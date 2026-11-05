"""S9 sea access: shared helpers for model.py and alliance.py (tables from tools/sea_routes.py, config `sea:`).

Nothing here is used unless a scenario carries `sea_kn` (coop list) or a `_sea` name suffix (alliance / pre).
"""
import os

import numpy as np
import pandas as pd

KN = 0.514444  # m/s per knot


def haul_csv(cfg, kn):
    return os.path.join(cfg["paths"]["cache_dir"], "sea", f"sites_haul_sea{float(kn):g}kn.csv")


def people_csv(cfg, kn):
    return os.path.join(cfg["paths"]["cache_dir"], "sea", f"people_sea{float(kn):g}kn.csv.gz")


def params(cfg):
    S = cfg["sea"]
    tp = cfg["transport"]
    L = cfg["lit_scenarios"]
    return {"min_haul": float(tp["min_haul_flatm"]), "v_drag": float(tp["drag_speed_ms"]), "v_back": float(tp["return_walk_ms"]),
            "transfer_h": float(S.get("transfer_h", tp["load_unload_h"])),
            "boat_factor": float(S["crew"]) * float(S.get("boat_pull_kg_per_person", tp["pull_kg_per_person"])) / float(S["payload_kg"]),
            "payload_kg": float(S["payload_kg"]),
            "hoist_ph_per_block_m": float(L["lever_ph_per_block_course"]) / float(L["geometry"]["course_height_m"])}


def trip_h(rec, cfg, kn):
    """Crew trip time (h) of a sea-mode site: two drag legs (each >= min haul) + walks back, a transfer at each
    landing, and the boat out and back at kn knots scaled by the boat factor (crew x pull / payload)."""
    p = params(cfg)
    mh = p["min_haul"]
    return ((max(rec["haul_flatm_1"], mh) + max(rec["haul_flatm_2"], mh)) / p["v_drag"]
            + (max(rec["haul_m_1"], mh) + max(rec["haul_m_2"], mh)) / p["v_back"]) / 3600.0 \
        + 2.0 * p["transfer_h"] + p["boat_factor"] * 2.0 * rec["sea_km"] * 1000.0 / (float(kn) * KN) / 3600.0


def hoist_ph_per_block(rec, cfg):
    return params(cfg)["hoist_ph_per_block_m"] * float(rec["hoist_m"])


SEA_COLS = ["mode", "haul_flatm_1", "haul_m_1", "haul_flatm_2", "haul_m_2", "sea_km", "hoist_m", "trip_h",
            "quarry_x", "quarry_y", "quarry_region"]


def load_haul(base_haul, cfg, kn):
    """The sea table rows of the sites in base_haul (same order and subset), with base_haul's uid_int."""
    t = pd.read_csv(haul_csv(cfg, kn)).set_index("UID")
    h = t.loc[base_haul.UID.to_numpy()].reset_index()
    h["uid_int"] = base_haul.uid_int.to_numpy()
    land = (h["mode"] == "land").to_numpy()
    for c in ("haul_flatm", "haul_m"):       # land rows: the baseline values bit for bit (CSV re-parse noise ~1e-14)
        b = base_haul[c].to_numpy()
        assert np.allclose(h[c].to_numpy()[land], b[land], rtol=0, atol=1e-6)
        h.loc[land, c] = b[land]
    return h


# v16 (addendum 4 L4, flag add4.sea_priced_as_charged): every sea route the table builder found (not only the rows
# whose route beat the land route in the builder's own per-crew currency), written by v16 tools/sea_routes.py as r_*
# columns. The model decides sea vs land on the cost it charges (alliance.Static._l4_sea_faces).
ROUTE_COLS = ["r_found", "r_hf1", "r_hm1", "r_hf2", "r_hm2", "r_sea_km", "r_hoist_m", "r_quarry_x", "r_quarry_y",
              "r_quarry_region", "r_quarry_stone"]


def load_routes(base_haul, cfg, kn):
    """The r_* route columns of the sea table for the sites of base_haul (same order). Needs a v16-built table."""
    t = pd.read_csv(haul_csv(cfg, kn)).set_index("UID")
    miss = [c for c in ROUTE_COLS if c not in t.columns]
    assert not miss, f"add4.sea_priced_as_charged needs sea tables rebuilt with v16 tools/sea_routes.py (missing {miss})"
    h = t.loc[base_haul.UID.to_numpy(), ROUTE_COLS].reset_index()
    h["r_found"] = h["r_found"].astype(bool)
    return h


def boat_h(sea_km, cfg, kn):
    """Boat leg crew hours per crew (out loaded + back empty), as trip_h's boat term."""
    p = params(cfg)
    return p["boat_factor"] * 2.0 * float(sea_km) * 1000.0 / (float(kn) * KN) / 3600.0


class Travel:
    """People travel by sea: effective walking distance = min(straight line, t_sea x walk speed)."""

    def __init__(self, cfg, kn, uids):
        pp = pd.read_csv(people_csv(cfg, kn))
        keep = set(uids)
        pp = pp[pp.src_UID.isin(keep)]
        self.site = {(s, t): h for s, t, h in zip(pp.src_UID[pp.kind == "site"], pp.tgt_UID[pp.kind == "site"],
                                                 pp.t_sea_h[pp.kind == "site"])}
        q = pp[pp.kind == "quarry"]
        self.point = {(s, int(x), int(y)): h for s, x, y, h in zip(q.src_UID, q.kx, q.ky, q.t_sea_h)}
        self.n_pairs = len(pp)

    def site_dist(self, src_uid, tgt_uid, d, walk_ms):
        t = self.site.get((src_uid, tgt_uid))
        return d if t is None else min(d, t * 3600.0 * walk_ms)

    def point_dist(self, src_uid, x, y, d, walk_ms, tgt_uid=None):
        t = self.site.get((src_uid, tgt_uid)) if tgt_uid is not None else self.point.get((src_uid, int(round(x)), int(round(y))))
        return d if t is None else min(d, t * 3600.0 * walk_ms)
