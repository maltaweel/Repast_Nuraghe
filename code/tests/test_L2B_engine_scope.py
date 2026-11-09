"""Fix of 9 Nov 2026: addendum-4 L2 (bedrock_everywhere) acts in the season engine only.

Addendum 4 of the specification, scope clarification (lines 41-42): L2 and L3 apply to the
season-based community engine (alliance.py); day-based engine-B rows (model.py, SCENARIOS section 19) keep their own
quarry rule (SC:881: joints_low on the outcrop, else scree) and their load_unload_h. Before the fix, model.py's
REALISTIC rows called lit.resolve_site with L2 on, so off-outcrop sites were quarried as joints_low.

  cd code_v16_final && PYTHONDONTWRITEBYTECODE=1 python tests/test_L2B_engine_scope.py
"""
import inspect
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import alliance  # noqa: E402
import lit  # noqa: E402
import model  # noqa: E402
from nbcommon import load_config  # noqa: E402

FA = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "runs/2026-11-02-v12-census/full_audited")
CFG = FA + "/v16_final/configs/config_full_audited.yaml"

OFF = {"TWR_N": 1, "on_outcrop": False, "lit_haul_rule": "short", "lit_type": ""}


def _cfg():
    cfg = load_config(CFG)
    assert "add4" not in cfg                                     # add4 defaults: L2, L3 ON
    F = lit.add4(cfg)
    assert F["bedrock_everywhere"] and F["load_per_tonne"]
    return cfg


def test_resolve_site_engine_scope():
    cfg = _cfg()
    L = lit.scenario(cfg, "REALISTIC")
    m = L["mixed"]
    assert m["quarry_off_outcrop"] != m["quarry_on_outcrop"]
    # season engine (alliance.py call, default engine_b=False): L2 -> bedrock along joints everywhere
    assert lit.resolve_site(cfg, L, OFF)["quarry"] == m["quarry_on_outcrop"]
    # engine B: the row's own quarry rule
    assert lit.resolve_site(cfg, L, OFF, engine_b=True)["quarry"] == m["quarry_off_outcrop"]
    assert lit.resolve_site(cfg, L, dict(OFF, on_outcrop=True), engine_b=True)["quarry"] == m["quarry_on_outcrop"]


def test_alliance_call_keeps_L2():
    src = inspect.getsource(alliance)
    assert "lit.resolve_site(cfg, L, r)" in src and "engine_b" not in src


def _site(cfg, name, rec):
    sc = model.scenario_params(cfg, name, "lit")
    fake = types.SimpleNamespace(context=types.SimpleNamespace(add=lambda a: None))
    return model.Site(0, 0, rec, 1, cfg, sc, fake), sc


def test_engine_b_site_off_outcrop_gets_scree():
    """A REALISTIC (and REALISTIC_oxen) engine-B site off the outcrop is quarried with quarry_off_outcrop, with the add4
    defaults; the per-trip load time stays load_unload_h (no L3 in engine B)."""
    cfg = _cfg()
    rec = dict(OFF, uid_int=12345, quarry_stone="basalt", haul_flatm=800.0, haul_m=700.0, mode="land")
    for name in ("REALISTIC", "REALISTIC_oxen"):
        s, sc = _site(cfg, name, rec)
        L = sc["lit"]
        exp_b = lit.resolve_site(cfg, L, rec, engine_b=True)
        assert exp_b["quarry"] == L["mixed"]["quarry_off_outcrop"]
        q = lit.stage_hours(cfg, exp_b, 1, "basalt", int(s.mass.size))["quarry"]
        q_l2 = lit.stage_hours(cfg, lit.resolve_site(cfg, L, rec), 1, "basalt", int(s.mass.size))["quarry"]
        assert abs(s.stages["quarry"] - q) < 1e-9 * max(1.0, q)
        assert abs(s.stages["quarry"] - q_l2) > 1e-6             # differs from the L2 (joints_low) price
        tp = cfg["transport"]
        _, v_drag, v_back, _ = lit.transport(cfg, exp_b)
        hf, hm = max(800.0, tp["min_haul_flatm"]), max(700.0, tp["min_haul_flatm"])
        trip = hf / v_drag / 3600.0 + hm / v_back / 3600.0 + tp["load_unload_h"]
        assert abs(s.st[model.S_TRIP] - trip) < 1e-12


def test_season_engine_site_gets_bedrock():
    """The season engine (alliance.Static._init_tech -> lit.resolve_site default) still gives quarry_on_outcrop."""
    cfg = _cfg()
    L = lit.scenario(cfg, "REALISTIC")
    assert lit.resolve_site(cfg, L, OFF)["quarry"] == L["mixed"]["quarry_on_outcrop"]


if __name__ == "__main__":
    n_ok = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        fn()
        n_ok += 1
        print(f"PASS {name}")
    print(f"{n_ok} tests passed")
