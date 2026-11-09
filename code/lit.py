"""Literature-based chaîne opératoire / logistics scenarios (config.yaml -> lit_scenarios).

Each scenario changes ONE axis of the stage-explicit Webster baseline (`webster`), except the bounds LOW/HIGH.
Stages (person-hours per site): quarry (MH_QUA), transport (simulated by the ABM, MH_TRA), dressing (MH_DRE),
walling/setting (MH_BLD) and lifting (MH_LIFT). Quarry + dressing + walling + lifting form the ABM's
quarry/build pool, which stays coupled to delivered stone exactly as before.

Every number comes from config.yaml; see METHODS.md section 8 for the source line of each one.
"""
import math
import os

import numpy as np

STAGES = ["quarry", "dress", "build", "lift"]


def scenario(cfg, name):
    L = cfg["lit_scenarios"]
    d = dict(L["defaults"])
    d.update(L["list"][name] or {})
    d["name"] = name
    return d


def haul_csv(cfg, lit):
    key = lit["haul"]
    if key == "base":
        return os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv")
    return os.path.join(cfg["paths"]["cache_dir"], "haul", f"sites_haul_{key}.csv")


def cone_course_weights(L):
    """Share of a tower's stone in each course, for a truncated cone (mass proportional to cross-section)."""
    g = L["geometry"]
    Hh, c, R0, R1 = g["tower_height_m"], g["course_height_m"], g["base_diam_m"] / 2, g["top_diam_m"] / 2
    n = int(math.ceil(Hh / c - 1e-9))
    edges = np.minimum(np.arange(n + 1) * c, Hh)

    def cum(z):   # integral of r(z)^2 dz, r linear from R0 to R1
        a, b = R0, (R1 - R0) / Hh
        return a * a * z + a * b * z * z + b * b * z ** 3 / 3
    w = np.diff(cum(edges))
    return w / w.sum()


def ramp_ph_per_tower(L, height=None, width=None):
    r = L["ramp"]
    Hh = L["geometry"]["tower_height_m"] if height is None else height
    W = r["width_m"] if width is None else width
    vol = 0.5 * (Hh / r["slope"]) * Hh * W                       # single-sided wedge rising to Hh
    rho = r["earth_density_kg_m3"]
    per_m3 = r["dig_ph_m3"] + rho / r["compact_kg_per_ph"] + rho / r["carry_load_kg"] * r["carry_dist_m"] * r["carry_h_per_m"]
    return vol, vol * per_m3 * r["build_remove_factor"]


def site_class(L, tw):
    for c in L["webster_classes"]:
        if c["min_towers"] <= tw <= c["max_towers"]:
            return c
    raise ValueError(tw)


def mass_factor(cfg, lit, stone):
    """S6: block volume fixed, mass scales with stone density relative to Webster's 2,386 kg/m3."""
    L = cfg["lit_scenarios"]
    if not lit.get("density"):
        return 1.0
    return L["density_kg_m3"].get(stone, L["webster_density_kg_m3"]) / L["webster_density_kg_m3"]


def target_kg(cfg, lit, tw):
    L = cfg["lit_scenarios"]
    if lit.get("classes"):
        return site_class(L, tw)["tonnes"] * 1000.0
    return cfg["stone"]["tonnes_per_tower"] * 1000.0 * tw


def md_hours(cfg, stage):
    """v11 (2 Nov 2026): hours in one of Webster's (1991: 852, Table 1) man-days of a stage. Webster takes quarrying
    (2,700 kg/man-day) and transport (1,200 kg/man-day) from Erasmus 1965 (pp. 286-7), whose man-day is a 5-h day
    (Erasmus 1965: 283, via Boswinkel 2021: 145); dressing (0.40 m3/man-day) and wall construction (0.80 m3/man-day)
    come from Abrams 1984, whose man-day is 8 h (Abrams 1994: 46-47, via Boswinkel 2021: 109; Devolder's 0.1 m3/ph
    from Abrams = 0.8 m3 / 8 h, Boswinkel 2021: 125, Table 7.11). With `v11.webster_day_fix` off (v10) every
    man-day is converted at the model's working day hours_per_day."""
    v = cfg.get("v11") or {}
    if v.get("webster_day_fix"):
        return float(v["webster_day_hours"][stage])
    return float(cfg["hours_per_day"])


def stage_hours(cfg, lit, tw, stone, n_blocks):
    """Deterministic person-hours of the non-transport stages for one site."""
    L = cfg["lit_scenarios"]
    Hq, Hd, Hb = md_hours(cfg, "quarry"), md_hours(cfg, "dress"), md_hours(cfg, "build")   # v11 (H each when off)
    md = L["webster_md_per_tower"]
    share = L["lift_share_of_build"]
    if lit.get("classes"):                                    # S7: Webster's class totals instead of x TWR_N
        c = site_class(L, tw)
        q, dr, b = c["quarry_md"] * Hq, c["dress_md"] * Hd, c["build_md"] * Hb
        mass_t = c["tonnes"]
    else:
        q, dr, b = md["quarry"] * Hq * tw, md["dress"] * Hd * tw, md["build"] * Hb * tw
        mass_t = cfg["stone"]["tonnes_per_tower"] * tw
    vol = mass_t * 1000.0 / L["webster_density_kg_m3"]          # m3 of stone (block volume held in S6)
    # S1 procurement
    if lit["quarry"] != "webster":
        q = L["quarry_ph_m3"][lit["quarry"]] * vol
    # S2 dressing
    if lit["dress"] == "none":
        dr = 0.0
    elif lit["dress"] == "fine" and tw >= L["fine_min_towers"]:
        g = L["geometry"]
        R0, R1, Hh = g["base_diam_m"] / 2, g["top_diam_m"] / 2, g["tower_height_m"]
        area = math.pi * (R0 + R1) * math.sqrt(Hh ** 2 + (R0 - R1) ** 2)       # outer face of one tower
        facing = area * L["facing_thickness_m"] * tw
        f = L["facade"]
        dr = dr + facing * (f["facade_ph_m3_mid"] - f["cyclopean_ph_m3_mid"])
    # S6 hardness multiplier on quarrying and dressing
    if lit.get("density"):
        h = L["hardness"].get(stone, 1.0)
        q, dr = q * h, dr * h
    # S4 lifting (part of the building stage)
    build = b * (1.0 - share)
    lift = b * share
    if lit["lift"] == "lever":
        w = cone_course_weights(L)
        lift = n_blocks * float(np.sum(w * np.arange(w.size))) * L["lever_ph_per_block_course"]
    elif lit["lift"] == "ramp":
        lift = ramp_ph_per_tower(L)[1] * tw
    elif lit["lift"] == "stair":
        w = cone_course_weights(L)
        c = L["geometry"]["course_height_m"]
        lift = n_blocks * (1.0 - w[0]) * L["lever_ph_per_block_course"] * (L["stair_lever_last_m"] / c)
    # S8 learning: tower i (0-based) costs (1 - rate)^i of the first one
    if lit.get("learning") and tw > 1:
        f = sum((1.0 - L["learning_rate"]) ** i for i in range(tw)) / tw
        q, dr, build, lift = q * f, dr * f, build * f, lift * f
    return {"quarry": q, "dress": dr, "build": build, "lift": lift}


def transport(cfg, lit):
    """(pull_kg_per_person or None for oxen, drag_speed, return_speed, oxen settings)."""
    L = cfg["lit_scenarios"]
    tp = cfg["transport"]
    mu = lit["mu"]
    if lit.get("oxen"):
        o = L["oxen"]
        return None, o["speed_ms"], o["return_speed_ms"], o
    pull = tp["pull_kg_per_person"] if mu == L["baseline_mu"] else L["f_person_kgf"] / mu
    return pull, tp["drag_speed_ms"], tp["return_walk_ms"], None


def oxen_yokes(mass, o):
    """Fewest yokes (pairs) whose sustained pull, after the multi-yoke efficiency loss, moves the block."""
    F = mass * 9.81 * o["mu"]
    eff = np.asarray(o["yoke_efficiency"], dtype=float)       # 1, 2, 3 yokes; >3 keeps the last value
    y = np.ones(mass.size, np.int64)
    while True:
        e = eff[np.minimum(y, eff.size) - 1]
        bad = y * 2 * o["pull_N_per_ox"] * e < F
        if not bad.any():
            return y
        y[bad] += 1


# --------------------------------------------------------------------------- v16: addendum 4 flags
# Addendum 4 of the specification, L1-L4, each behind its own flag in the top-level config block `add4:`.
# code_v16_flags: default OFF (5 Nov 2026). code_v16_final (CHANGES_V16_FINAL.md): L2 bedrock_everywhere and L3
# load_per_tonne default ON (kept after the flag test, CHANGES_V16.md); L1 rails_cost_choice and L4 sea_priced_as_charged default
# OFF (not kept). The flags stay, so a row can still switch any of them with its own `add4:` block.
ADD4_FLAGS = ("rails_cost_choice", "bedrock_everywhere", "load_per_tonne", "sea_priced_as_charged")
ADD4_DEFAULTS = {"rails_cost_choice": False, "bedrock_everywhere": True, "load_per_tonne": True,
                 "sea_priced_as_charged": False, "rail_lay_mh_per_m": 2.0, "load_ph_per_t": 1.2}

# Code version of every result-changing code path (code_v16_final). Hashed into EVERY run signature (alliance.signature,
# model.run_signature) together with the effective add4 settings, so part files written by older code are never reused.
CODE_VERSION = "2026-11-05-v16_final"


def add4(cfg):
    """Effective addendum-4 settings: ADD4_DEFAULTS updated by cfg['add4'] (flags as bool, params as float)."""
    d = dict(ADD4_DEFAULTS)
    d.update(cfg.get("add4") or {})
    for k in ADD4_FLAGS:
        d[k] = bool(d[k])
    d["rail_lay_mh_per_m"] = float(d["rail_lay_mh_per_m"])
    d["load_ph_per_t"] = float(d["load_ph_per_t"])
    return d


def add4_any(cfg):
    return any(add4(cfg)[k] for k in ADD4_FLAGS)


_CPT = {}


def crews_per_tonne(cfg, pull, mf):
    """Expected sledge crew (person-trips) per tonne of stone for blocks of the config's lognormal draw scaled by the
    S6 mass factor mf: E[ceil(m mf / pull)] / E[m mf / 1000]. Fixed sample (default_rng(0), 200,000 blocks, as
    tools/sea_routes.py mean_crew), so it is deterministic and seed-independent (used only for the v16 static
    choices L1 / L4, which are made once per site before the run)."""
    s = cfg["stone"]
    key = (float(pull), float(mf), float(s["block_median_kg"]), float(s["block_sigma"]), float(s["block_min_kg"]),
           float(s["block_max_kg"]))
    if key not in _CPT:
        m = np.clip(np.random.default_rng(0).lognormal(np.log(s["block_median_kg"]), s["block_sigma"], 200000),
                    s["block_min_kg"], s["block_max_kg"]) * float(mf)
        _CPT[key] = (float(np.ceil(m / float(pull)).mean()) / float(m.mean() / 1000.0), float(m.mean() / 1000.0))
    return _CPT[key]


# --------------------------------------------------------------------------- mixed (per-site) combinations
# A scenario with a `mixed:` block (REALISTIC) picks, for every site, one value per axis from site attributes.
# The result is an ordinary single-rule scenario dict per site (`resolve_site`), so stage_hours, transport and
# mass_factor run unchanged. All rules are deterministic functions of the site (no random draw), hence
# identical in every seed. Rules and sources: REALISTIC_NOTES.md.

def site_types(cfg, field):
    """UID -> site TYPE from the sites shapefile (attributes only)."""
    import pyogrio
    uid = cfg["site_fields"]["uid"]
    t = pyogrio.read_dataframe(cfg["paths"]["sites"], columns=[uid, field], read_geometry=False)
    return dict(zip(t[uid], t[field]))


def mixed_haul(cfg, lit, load, use_long=None):
    """Haul table of a mixed scenario: each site's row from the short-haul (sledge) table, replaced by the
    long-haul table's row where the short-haul route is longer than long_min_haul_m. `load(path)` reads one
    haul table (model.load_haul). Adds the per-site technique columns lit_haul_rule, lit_type.
    v16 (addendum 4 L1, flag add4.rails_cost_choice): `use_long` (bool per row of the short table) replaces the
    long_min_haul_m threshold; None (default) = the threshold rule, unchanged. Rows with no long-haul route stay short."""
    m = lit["mixed"]
    short = load(haul_csv(cfg, {"haul": m["short"]["haul"]}))
    lng = load(haul_csv(cfg, {"haul": m["long"]["haul"]})).set_index("UID").reindex(short.UID).reset_index()
    if use_long is None:
        use_long = (short.haul_m.to_numpy() > float(m["long_min_haul_m"])) & lng.haul_flatm.notna().to_numpy()
    else:
        use_long = np.asarray(use_long, bool) & lng.haul_flatm.notna().to_numpy()
    h = short.copy()
    for c in short.columns:
        if c not in ("UID", "uid_int"):
            h[c] = np.where(use_long, lng[c].to_numpy(), short[c].to_numpy())
    h["lit_haul_rule"] = np.where(use_long, "long", "short")
    types = site_types(cfg, m["type_field"])
    h["lit_type"] = [types.get(u, "") for u in h.UID]
    return h


def resolve_site(cfg, lit, rec, engine_b=False):
    """Single-rule scenario dict for one site of a mixed scenario.
    engine_b=True (model.py, day-based engine-B rows, SCENARIOS section 19): addendum-4 L2 is NOT applied, the row
    keeps its own quarry rule (addendum 4 of the specification, scope clarification, lines 41-42; fix 9 Nov 2026)."""
    m = lit["mixed"]
    tw = int(rec["TWR_N"])
    d = {k: v for k, v in lit.items() if k != "mixed"}
    d.update(m[rec["lit_haul_rule"]])                                     # mu, haul (+ oxen in a variant)
    d["quarry"] = m["quarry_on_outcrop"] if bool(rec["on_outcrop"]) else m["quarry_off_outcrop"]
    if add4(cfg)["bedrock_everywhere"] and not engine_b:                 # v16 L2: bedrock along joints everywhere
        d["quarry"] = m["quarry_on_outcrop"]
    if tw <= int(m["dress_none_max_towers"]):
        d["dress"] = "none"
    elif tw >= int(m["dress_fine_min_towers"]):
        d["dress"] = "fine"                                               # tw >= fine_min_towers too, see stage_hours
    else:
        d["dress"] = "webster"
    d["lift"] = m["lift_by_type"].get(rec["lit_type"], m["lift_default"])
    return d


# --------------------------------------------------------------------------- per-scenario work party (builders)
def draw_builders(rule, tw, rng):
    """Builders of one site from a per-scenario rule, with exactly ONE uniform draw from the site's stream (as the
    default rule), so the block draws that follow are unchanged.
      {residents_by_towers: [[lo, hi], ...] (index = TWR_N - 1, last row for larger), adult_share: a}:
          residents ~ U[lo, hi], builders = floor(a x residents + 0.5) (MOST_REALISTIC, specified by the authors)
      {base, per_extra_tower, rand_min, rand_max, min, max}: the default rule with these values."""
    if "residents_by_towers" in rule:
        return builders_of(rule, draw_residents(rule, tw, rng))
    base = round(rule["base"] + rule["per_extra_tower"] * (tw - 1))
    fac = rng.uniform(rule["rand_min"], rule["rand_max"])
    return int(min(rule["max"], max(rule["min"], round(base * fac))))


def residents_range(rule, tw):
    rows = rule["residents_by_towers"]
    lo, hi = rows[min(tw, len(rows)) - 1]
    return float(lo), float(hi)


def draw_residents(rule, tw, rng):
    """Residents of one site ~ U[lo, hi] by tower count (one uniform draw)."""
    lo, hi = residents_range(rule, tw)
    return rng.uniform(lo, hi)


def builders_of(rule, residents):
    """Work party = round(adult_share x residents), at least 1."""
    return max(1, int(math.floor(float(rule["adult_share"]) * residents + 0.5)))
