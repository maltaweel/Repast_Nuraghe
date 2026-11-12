"""Tests of the addendum-4 flags (5 Nov 2026; add4 defaults L2, L3 ON): flags L1-L4 (off = v15b, on = the new rule), L5, S1-S3 and the v16 summary
columns. Light unit tests (no kbest / raster loading); the whole-run identity (all flags off vs v15b) and the
flag-on runs are in the run's v16_test/ folder (not published).

  cd code && NURAGHE_TEST_CONFIG=/path/to/config.yaml PYTHONDONTWRITEBYTECODE=1 python tests/test_add4_flags.py      (or python -m pytest -q ...)
"""
import copy
import math
import os
import sys
import types

import numpy as np
import pandas as pd
try:
    import pytest
except ImportError:                                          # the geo-venv has no pytest: see __main__ below
    pytest = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import alliance  # noqa: E402
import lit  # noqa: E402
import report_alliance  # noqa: E402
import sea as seamod  # noqa: E402
from nbcommon import load_config  # noqa: E402

# Configuration read by the tests: NURAGHE_TEST_CONFIG = the model's configuration with data_dir and a derived-input
# cache set (e.g. WORK_DIR/config.yaml written by notebooks/02_inputs.ipynb; README, "Tests").
CFG = os.environ.get("NURAGHE_TEST_CONFIG", "NURAGHE_TEST_CONFIG-not-set")


class approx:
    def __init__(self, x, rel=1e-9, abs=1e-9):
        self.x, self.rel, self.abs = x, rel, abs

    def __eq__(self, o):
        a, b = np.atleast_1d(np.asarray(o, float)), np.atleast_1d(np.asarray(self.x, float))
        return a.shape == b.shape and bool(np.all(np.abs(a - b) <= np.maximum(self.abs, self.rel * np.abs(b))))

    def __repr__(self):
        return f"approx({self.x})"


def _cfg():
    return load_config(CFG)


cfg = pytest.fixture(scope="module")(_cfg) if pytest else _cfg


def with_flags(cfg, **kw):
    c = copy.deepcopy(cfg)
    c["add4"] = dict(kw)
    return c


# --------------------------------------------------------------------------- flags
def test_flags_default_off(cfg):
    """code_v16_final: defaults L2, L3 ON, L1, L4 OFF (was all OFF in code_v16_flags); explicit False switches off."""
    assert "add4" not in cfg
    F = lit.add4(cfg)
    assert {k: F[k] for k in lit.ADD4_FLAGS} == {"rails_cost_choice": False, "bedrock_everywhere": True,
                                                 "load_per_tonne": True, "sea_priced_as_charged": False}
    assert lit.add4_any(cfg)
    assert F["rail_lay_mh_per_m"] == 2.0 and F["load_ph_per_t"] == 1.2
    off = with_flags(cfg, bedrock_everywhere=False, load_per_tonne=False, rails_cost_choice=False, rail_lay_mh_per_m=20)
    assert not lit.add4_any(off)
    assert lit.add4_any(with_flags(cfg, load_per_tonne=True))


# --------------------------------------------------------------------------- L2
def test_L2_bedrock(cfg):
    L = lit.scenario(cfg, "REALISTIC")
    off = {"TWR_N": 1, "on_outcrop": False, "lit_haul_rule": "short", "lit_type": ""}
    on = dict(off, on_outcrop=True)
    assert lit.resolve_site(cfg, L, off)["quarry"] == "joints_low"          # code_v16_final: L2 ON by default
    c2 = with_flags(cfg, bedrock_everywhere=True)
    cfg = with_flags(cfg, bedrock_everywhere=False)                         # explicit OFF = v15b
    assert lit.resolve_site(cfg, L, off)["quarry"] == "scree"               # v15b: loose stone off the outcrop
    assert lit.resolve_site(cfg, L, on)["quarry"] == "joints_low"
    assert lit.resolve_site(c2, L, off)["quarry"] == "joints_low"           # L2: bedrock along joints everywhere
    assert lit.resolve_site(c2, L, on)["quarry"] == "joints_low"
    st_off = lit.stage_hours(cfg, dict(lit.resolve_site(cfg, L, off), learning=False), 1, "basalt", 3000)
    st_on = lit.stage_hours(c2, dict(lit.resolve_site(c2, L, off), learning=False), 1, "basalt", 3000)
    vol = cfg["stone"]["tonnes_per_tower"] * 1000.0 / cfg["lit_scenarios"]["webster_density_kg_m3"]
    assert st_off["quarry"] == approx(2.0 * vol * 2.0)                # scree 2.0 ph/m3 x hardness 2
    assert st_on["quarry"] == approx(11.1 * vol * 2.0)                # joints 11.1 ph/m3 x hardness 2


# --------------------------------------------------------------------------- L1 (mixed_haul override + choice)
def _tables():
    short = pd.DataFrame({"UID": ["a", "b", "c"], "haul_m": [500.0, 1500.0, 1500.0], "haul_flatm": [600.0, 1700.0, 1700.0],
                          "on_outcrop": [False, False, False], "quarry_stone": ["basalt"] * 3, "TWR_N": [1, 1, 1]})
    lng = short.copy()
    lng["haul_flatm"] = [900.0, 2000.0, np.nan]
    lng["quarry_stone"] = ["granite"] * 3
    return short, lng


def test_L1_mixed_haul_override(cfg, monkeypatch):
    monkeypatch.setattr(lit, "site_types", lambda cfg, f: {})
    short, lng = _tables()
    L = lit.scenario(cfg, "REALISTIC")
    load = lambda p: (lng if p.endswith("mu0.1.csv") else short).copy()   # noqa: E731
    old = lit.mixed_haul(cfg, L, load)                                     # v15b threshold (1,000 m)
    assert list(old.lit_haul_rule) == ["short", "long", "short"]           # c: no rails route -> short
    new = lit.mixed_haul(cfg, L, load, use_long=[True, False, True])
    assert list(new.lit_haul_rule) == ["long", "short", "short"]
    assert new.quarry_stone.iat[0] == "granite" and new.quarry_stone.iat[1] == "basalt"


def _fake_static(cfg, L_m, tw=1):
    """One site, face 0 = a real kbest route of 1 move: dry-ground cost C38 = 1.2 L, rails C01 = 1.1 L."""
    ns = types.SimpleNamespace()
    ns.N = 1
    ns.faces = [[{"route": 0, "a": 0, "b": 1, "C": L_m, "L": L_m}]]
    ns.mv_c038 = np.array([1.2 * L_m]); ns.mv_c01 = np.array([1.1 * L_m])
    ns.haul = pd.DataFrame({"UID": ["a"], "TWR_N": [tw], "quarry_stone": ["basalt"]})
    ns._face0_costs = lambda i: alliance.Static._face0_costs(ns, i)
    ns._face0_stone = lambda t: alliance.Static._face0_stone(ns, t)        # code_v16_final D11
    return ns


def _load_one(stone="basalt"):
    t = pd.DataFrame({"UID": ["a"], "haul_m": [100.0], "haul_flatm": [100.0], "on_outcrop": [True],
                      "quarry_stone": [stone], "TWR_N": [1]})
    return lambda p: t.copy()


def test_L1_choice_by_cost(cfg):
    L = lit.scenario(cfg, "REALISTIC")
    F = lit.add4(with_flags(cfg, rails_cost_choice=True, load_per_tonne=False))   # code_v16_final: L3 default ON
    tp = cfg["transport"]
    for Lm in (0.0, 300.0, 5000.0):
        ns = _fake_static(cfg, Lm)
        use = alliance.Static._l1_choice(ns, cfg, L, _load_one(), F)
        # hand computation of the two totals
        mf = lit.mass_factor(cfg, L, "basalt"); tn = 1350.0 * mf
        out = []
        for C, pull in ((1.2 * Lm, 30 / 0.38), (1.1 * Lm, 300.0)):
            cpt = lit.crews_per_tonne(cfg, pull, mf)[0]
            trip = max(C, 15) / tp["drag_speed_ms"] / 3600 + max(Lm, 15) / tp["return_walk_ms"] / 3600 + tp["load_unload_h"]
            out.append(cpt * tn * trip)
        out[1] += 2.0 * max(Lm, 15)
        assert list(ns.l1_cost[0]) == approx(out)
        assert bool(use[0]) == (out[1] < out[0])
        assert ns.l1_len[0] == max(Lm, 15.0)
    # a prohibitive laying cost keeps dry ground; 2.0 mh/m takes rails on a short route
    ns = _fake_static(cfg, 300.0)
    assert alliance.Static._l1_choice(ns, cfg, L, _load_one(), F)[0]
    F2 = dict(F, rail_lay_mh_per_m=1e6)
    assert not alliance.Static._l1_choice(ns, cfg, L, _load_one(), F2)[0]


# --------------------------------------------------------------------------- L3
def _fake_model(cfg, L3, tn=1350.0):
    m = types.SimpleNamespace()
    m.tp = cfg["transport"]; m.L3 = L3; m.lp = 1.2
    m.towers = [[(tn, 0, 0)]]; m.tower_idx = np.array([0])
    m.trip = lambda C, L, part, v=None, ld=None: alliance.AllianceModel.trip(m, C, L, part, v, ld)
    m.cz = None                                            # 2026-11-09: fake updated for alliance._load_t (fix 7 Nov,
    m._load_t = lambda o, t: alliance.AllianceModel._load_t(m, o, t)   # S17 fill tonnes); no S17 fill here
    return m


def test_L3_loading(cfg):
    tp = cfg["transport"]
    off, on = _fake_model(cfg, False), _fake_model(cfg, True)
    crews, C, L = 18000, 800.0, 700.0
    t_whole = C / tp["drag_speed_ms"] / 3600 + L / tp["return_walk_ms"] / 3600
    assert alliance.AllianceModel._crew_trip_mh(off, crews, C, L, "whole", 0) == approx(crews * (t_whole + 0.25))
    assert alliance.AllianceModel._crew_trip_mh(on, crews, C, L, "whole", 0) == approx(crews * t_whole + 1350 * 1.2)
    assert alliance.AllianceModel._crew_trip_mh(off, crews, C, L, "leg", 0) == approx(crews * (t_whole + 0.125))
    assert alliance.AllianceModel._crew_trip_mh(on, crews, C, L, "leg", 0) == approx(crews * t_whole + 1350 * 0.6)
    # min-haul floor kept on whole routes
    t0 = 15 / tp["drag_speed_ms"] / 3600 + 15 / tp["return_walk_ms"] / 3600
    assert alliance.AllianceModel._crew_trip_mh(on, 10, 0.0, 0.0, "whole", 0) == approx(10 * t0 + 1350 * 1.2)


# --------------------------------------------------------------------------- L4
def _sea_face(row, cfg, kn, rails=(False, False)):
    return {"sea": True, "legs": [(row["haul_flatm_1"], row["haul_m_1"]), (row["haul_flatm_2"], row["haul_m_2"])],
            "leg_rails": list(rails), "boat_h": seamod.boat_h(row["sea_km"], cfg, kn),
            "hoist_ph": seamod.hoist_ph_per_block(row, cfg)}


def test_L4_pricing_matches_s9_when_same_rules(cfg):
    """L4 pricing with dry legs and per-crew loading = the v15b charge S038 x land_h + S03 x boat_h + hoist."""
    row = {"haul_flatm_1": 400.0, "haul_m_1": 350.0, "haul_flatm_2": 10.0, "haul_m_2": 5.0, "sea_km": 12.0, "hoist_m": 3.0}
    kn = 2.0
    m = _fake_model(cfg, False)
    m.cfg = cfg; m.F = lit.add4(cfg)
    m.S = types.SimpleNamespace(tech={"rule": np.array(["short"])})
    m.tw_n = np.array([1.0]); m.c01 = [[999]]
    face = _sea_face(row, cfg, kn)
    S038, S03p, nblk = 18000, 14000, 3000
    old = S038 * seamod.trip_h(row, cfg, 1e300) + S03p * (seamod.trip_h(row, cfg, kn) - seamod.trip_h(row, cfg, 1e300)) \
        + nblk * seamod.hoist_ph_per_block(row, cfg)
    new = alliance.AllianceModel._sea_l4_mh(m, 0, face, S038, S038, S03p, nblk, None)
    assert new == approx(old, rel=1e-12)
    # L3 on: per-crew transfers replaced by 2 x tonnes x load_ph_per_t
    m.L3 = True
    new3 = alliance.AllianceModel._sea_l4_mh(m, 0, face, S038, S038, S03p, nblk, None)
    assert new3 == approx(old - S038 * 2 * 0.25 + 2 * 1350 * 1.2, rel=1e-12)
    # a rails leg uses the rails crews (+ laying share when L1 is on)
    m.L3 = False
    m.F = lit.add4(with_flags(cfg, rails_cost_choice=True, sea_priced_as_charged=True))
    face_r = _sea_face(row, cfg, kn, rails=(True, False))
    r = alliance.AllianceModel._sea_l4_mh(m, 0, face_r, S038, S038, S03p, nblk, None)
    t1 = (400 / 0.27 + 350 / 1.39) / 3600
    assert r == approx(old - S038 * (t1 + 0.25) + 999 * (t1 + 0.25) + 2.0 * 350.0, rel=1e-12)


# --------------------------------------------------------------------------- S3
def test_S3_ceiling_all_communities(cfg):
    rule = {"residents_by_towers": [[100, 100]], "adult_share": 0.5}
    N = 20
    S = types.SimpleNamespace(N=N, haul=pd.DataFrame({"TWR_N": [1] * N, "uid_int": np.arange(N)}))
    m = types.SimpleNamespace(units=None)
    # 2,000 residents in all; every P10 cohort holds 200: v15b (cohort basis) never binds at 1,500, v16 does
    sc = {"builders_rule": rule, "population_ceiling": 1500, "phase_frac": 0.1}
    B = alliance.AllianceModel._population_ceiling(m, S, sc, 1)
    assert m.pop_info["ceiling_binding"] and m.pop_info["binding"] and m.pop_info["scale"] < 1.0
    assert m.pop_info["total_residents"] == approx(1500.0)
    assert len(B) == N
    sc["population_ceiling"] = 2500
    alliance.AllianceModel._population_ceiling(m, S, sc, 1)
    assert not m.pop_info["ceiling_binding"] and m.pop_info["redraws"] == 0


# --------------------------------------------------------------------------- S2
def test_S2_levy_carry():
    import census_scenarios
    cz = types.SimpleNamespace(levy={"days": 10, "share": 0.5}, lintel=None, wait=None,
                               m=types.SimpleNamespace(Hh=8.0, B=np.array([10, 20])))
    cz.levy_used_s = np.array([500.0, 100.0])                 # budgets 10 x 0.5 x B x 8 = 400, 800
    census_scenarios.Census.season_start(cz)
    assert list(cz.levy_used_s) == [100.0, 0.0]               # excess 100 carries; under-use does not


# --------------------------------------------------------------------------- L5 + summary columns
def _sites():
    rows = []
    rng = np.random.default_rng(3)
    for s in (1, 2, 3):
        start = 1
        for k in range(3):                                    # 3 cohorts of 40 sites, each starts after the last
            fin = start + rng.integers(0, 50, 40)
            for j, f in enumerate(fin):
                rows.append({"seed": s, "gid": k * 40 + j, "phase": k, "start_season": start, "finish_season": int(f)})
            start = int(fin.max()) + 1
    return pd.DataFrame(rows)


def test_L5_island_years_p95():
    d = _sites()
    mx = report_alliance.island_years_q(d, 100.0)
    assert (mx == d.groupby("seed").finish_season.max().astype(float)).all()   # q = 100 -> island years
    p95 = report_alliance.island_years_q(d, 95.0)
    for s, g in d.groupby("seed"):
        exp = sum(np.percentile(c.finish_season - c.start_season.min() + 1, 95) for _, c in g.groupby("phase"))
        assert p95[s] == approx(exp)
        assert p95[s] <= mx[s]
    un = d.drop(columns=["phase"])                            # unphased: one cohort from season 1
    assert report_alliance.island_years_q(un, 95.0)[1] == approx(np.percentile(d[d.seed == 1].finish_season, 95))


def test_L5_island_wide_p95():
    d = _sites()
    g = d.groupby("seed").finish_season.quantile(0.95)
    for s, x in d.groupby("seed"):
        assert g[s] == approx(np.percentile(x.finish_season, 95))
    assert "finish_season.quantile(0.95)" in open(report_alliance.__file__).read()


def test_spread():
    x = [442, 658, 399, 500, 470]
    sp = report_alliance.spread(x)
    assert sp["mean"] == approx(np.mean(x)) and sp["sd"] == approx(np.std(x, ddof=1))
    assert sp["min"] == 399 and sp["max"] == 658
    assert sp["p5"] == approx(np.percentile(x, 5)) and sp["p95"] == approx(np.percentile(x, 95))
    assert report_alliance.spread([5.0])["sd"] == 0.0


# --------------------------------------------------------------------------- signature
def test_signature_flags(cfg):
    sc = alliance.scenario(cfg, "MOST_REALISTIC_AUDITED_LIT_P10")
    sc = {k: v for k, v in sc.items() if k != "sea_kn"}        # no sea table read in this unit test
    haul = pd.DataFrame({"UID": ["a"], "TWR_N": [1], "haul_flatm": [1.0], "haul_m": [1.0]})
    s0 = alliance.signature(cfg, sc, haul)
    # code_v16_final: the effective settings are hashed, so an explicit block equal to the defaults = no block
    s_def = alliance.signature(with_flags(cfg, rails_cost_choice=False, bedrock_everywhere=True, load_per_tonne=True),
                               sc, haul)
    assert s0 == s_def
    alloff = dict(rails_cost_choice=False, bedrock_everywhere=False, load_per_tonne=False)
    s_off = alliance.signature(with_flags(cfg, **alloff), sc, haul)
    assert s_off != s0
    sigs = {alliance.signature(with_flags(cfg, **dict(alloff, **{f: True})), sc, haul)
            for f in lit.ADD4_FLAGS if f != "sea_priced_as_charged"}
    assert len(sigs) == 3 and s_off not in sigs and s0 not in sigs
    assert alliance.signature(with_flags(cfg, rails_cost_choice=True, rail_lay_mh_per_m=20), sc, haul) not in sigs


def test_summary_columns_in_stats(tmp_path):
    """write_scenario's stats.json keeps the v15b keys and adds sd / p5 / p95 (and the L5 / stage spreads)."""
    src = open(report_alliance.__file__).read()
    for k in ("island_years_p95", "island_mh_", "relay_share_chosen", "relay_share_made", "island_by_seed.csv"):
        assert k in src
    # the key-building loop never overwrites existing keys
    st = {"island_mh_mean": 1.0, "island_mh_min": 0.5}
    for k, v in report_alliance.spread([1.0, 2.0]).items():
        st.setdefault(f"island_mh_{k}", v)
    assert st["island_mh_mean"] == 1.0 and st["island_mh_min"] == 0.5 and "island_mh_p95" in st


class _MP:
    def __init__(self):
        self.undo = []

    def setattr(self, obj, name, val):
        self.undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)

    def restore(self):
        for o, n, v in reversed(self.undo):
            setattr(o, n, v)


if __name__ == "__main__":
    import inspect
    import tempfile
    c = _cfg()
    n_ok = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        mp = _MP()
        args = {"cfg": c, "monkeypatch": mp, "tmp_path": tempfile.mkdtemp()}
        try:
            fn(**{a: args[a] for a in inspect.signature(fn).parameters})
            n_ok += 1
            print(f"PASS {name}")
        finally:
            mp.restore()
    print(f"{n_ok} tests passed")
