"""Tests of the lift rule (9 Nov 2026; SP-22 ruling): lift priced at the undiscounted rate.

Ruling (specified by the authors, 9 Nov 2026: no discount on lift, long-term rates; spec addendum k):
"Lift (all lift rules) is priced at the undiscounted rate: the learning factor (PM:23) and skill (PM:173) apply to
quarrying, dressing and building only, never to lift."
Fake models only (no kbest / raster loading, no simulation); engine B via lit.stage_hours with a real config.

  cd code && NURAGHE_TEST_CONFIG=/path/to/config.yaml PYTHONDONTWRITEBYTECODE=1 python tests/test_lift.py
"""
import inspect
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import alliance  # noqa: E402
import lit  # noqa: E402
from nbcommon import load_config  # noqa: E402

assert os.path.dirname(os.path.abspath(alliance.__file__)) == os.path.dirname(HERE), alliance.__file__   # this code folder
import lit as _lit_check
assert _lit_check.CODE_VERSION == "2026-11-09-v17", _lit_check.CODE_VERSION   # the code version of the model (part of every run signature)
# Configuration read by the tests: NURAGHE_TEST_CONFIG = the model's configuration with data_dir and a derived-input
# cache set (e.g. WORK_DIR/config.yaml written by notebooks/02_inputs.ipynb; README, "Tests").
CFG = os.environ.get("NURAGHE_TEST_CONFIG", "NURAGHE_TEST_CONFIG-not-set")
AM = alliance.AllianceModel
RATE = 0.15
BUILD1, LS = 1000.0, 0.3                                  # per-tower build stage (build + lift) and its lift share


def approx(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def _fake(skill=None, tech=True, s8_rate=RATE, f=0.0, N=2):
    """Owner 0 (single site), optional helper 1; real _stage/_lift_share/_build_lift/_handover_mh/_perform_join/
    _join_task/charge/_owner_skill, fake task layer."""
    m = types.SimpleNamespace()
    m.N = N
    m.S = types.SimpleNamespace(tech={} if tech else None)
    m.s8_rate = s8_rate
    m.unit_stage, m.unit_ls, m.cz = None, {}, None
    m.site_stage = [{"quarry": 500.0, "dress": 800.0, "build": BUILD1} for _ in range(N)]
    m.site_lift_share = np.full(N, LS)
    m.base_stage = {"quarry": 500.0, "dress": 800.0, "build": BUILD1}
    m.lift_share = LS
    m.tower_idx = np.zeros(N, np.int64)
    m.cum = np.zeros((N, len(alliance.SKILL_STAGES)))
    sk = skill or {}
    m.skill = lambda j, stage: sk.get(j, 1.0)
    m._join_split = lambda i, h, stage, nblk: f
    m.B = np.array([40.0] * N)
    m.tp = {"return_walk_ms": 1.4}
    m.sc = {"specialisation": False}
    m.wdist = lambda p, loc, tgt=None: 0.0
    m.join_part = {}
    m.acc = {k: np.zeros(N) for k in ("mh_total", "mh_walk", "mh_own", "mh_received", "mh_given", "mh_build",
                                      "mh_lift", "mh_quarry", "mh_dress", "mh_transport", "mh_track")}
    m.given_stage = np.zeros((N, len(alliance.STAGES)))
    m.help_mh, m.help_stage, m.help_log, m.season, m.soc = {}, {}, {}, 0, None
    m.tasks = []

    def add_task(perf, total, stage, up=-1, final=False):
        m.tasks.append((perf, total, stage))
        return len(m.tasks) - 1
    m.add_task = add_task
    for n in ("_stage", "_lift_share", "_build_lift", "_handover_mh", "_perform_join", "_join_task", "charge",
              "_owner_skill"):
        setattr(m, n, getattr(AM, n).__get__(m))
    return m


def _tower_handover(m, t, xlift=0.0):
    """One tower t of owner 0 built by its own party (no help), as perform() prices it -> (d mh_build, d mh_lift)."""
    m.tower_idx[0] = t
    b0, l0 = m.acc["mh_build"][0], m.acc["mh_lift"][0]
    bb, lb = m._build_lift(0, xlift)
    mh = m._handover_mh(0, 0, "build", bb, 0.0, t, lb)
    m.add_task(0, mh, "build")
    m.charge(0, 0, mh, "build", 0.0, lift=lb)
    return m.acc["mh_build"][0] - b0, m.acc["mh_lift"][0] - l0


# --------------------------------------------------------------------------- season engine
def test_lift_equal_every_tower_under_learning():
    """Single site, no help, S8 learning on (A3 skill 1): tower t's lift MH == tower 0's; build x (1 - rate)^t."""
    m = _fake()
    rows = [_tower_handover(m, t) for t in range(5)]
    b0, l0 = rows[0]
    assert approx(l0, BUILD1 * LS) and approx(b0, BUILD1 * (1 - LS))
    for t, (b, l) in enumerate(rows):
        assert approx(l, l0), (t, l, l0)                                   # lift undiscounted
        assert approx(b, b0 * (1 - RATE) ** t), (t, b)                     # build still discounted
        if t:
            assert not approx(l, l0 * (1 - RATE) ** t)                     # v16_final would have discounted it
    assert approx(m.acc["mh_total"][0], m.acc["mh_build"][0] + m.acc["mh_lift"][0])   # columns add up


def test_lift_not_skill_discounted():
    """A3 skill (no S8): owner's own skill 0.7 and a helper's skill 0.6 discount build, never lift."""
    m = _fake(skill={0: 0.7, 1: 0.6}, s8_rate=0.0)
    bb, lb = m._build_lift(0)
    assert approx(m._handover_mh(0, 0, "build", bb, 0.0, 3, lb), bb * 0.7 + lb)
    assert approx(m._handover_mh(0, 1, "build", bb, 0.0, 3, lb), bb * 0.6 + lb)
    # quarry / dress unchanged (lift 0): base x skill + extra
    assert approx(m._handover_mh(0, 0, "quarry", 500.0, 20.0, 3), 500.0 * 0.7 + 20.0)


def test_no_tech_webster_lift_share():
    """Without tech rules (Webster stages, island lift share) the same split applies; S8 is tech-only as before."""
    m = _fake(skill={0: 0.8}, tech=False)
    b, l = _tower_handover(m, 2)
    assert approx(l, BUILD1 * LS) and approx(b, BUILD1 * (1 - LS) * 0.8)


def test_join_lift_undiscounted_and_booked():
    """Join mode: owner (S8, t = 3) and helper (skill 0.6) each price their build share at their own factor; the
    lift is split by the hands share f at factor 1; mh_lift == the whole tower's lift; f = 0 = no help."""
    for f in (0.0, 0.3, 0.8):
        m = _fake(skill={0: 1.0, 1: 0.6}, f=f)
        t = 3
        m.tower_idx[0] = t
        bb, lb = m._build_lift(0)
        m._perform_join(0, 1, "build", (0.0, 0.0), -1, True, bb, 0.0, t, 100, {}, lift=lb)
        mo = bb * (1 - f) * (1 - RATE) ** t + lb * (1 - f)
        mh_h = bb * f * 0.6 + lb * f
        assert approx(m.tasks[0][1], mo)
        if f > 0:
            assert approx(m.tasks[1][1], mh_h)
        assert approx(m.acc["mh_lift"][0], lb) and approx(m.acc["mh_build"][0], mo + mh_h - lb)
        # the same tower's lift at t = 0 is identical
        m2 = _fake(skill={0: 1.0, 1: 0.6}, f=f)
        bb0, lb0 = m2._build_lift(0)
        m2._perform_join(0, 1, "build", (0.0, 0.0), -1, True, bb0, 0.0, 0, 100, {}, lift=lb0)
        assert approx(m2.acc["mh_lift"][0], m.acc["mh_lift"][0])


def test_sea_xlift_and_unit_share():
    """xlift (lift of the extra sea-payload pieces) is all lift; S10 / S13 per-tower lift shares are used."""
    m = _fake()
    b, l = _tower_handover(m, 2, xlift=40.0)
    assert approx(l, BUILD1 * LS + 40.0) and approx(b, BUILD1 * (1 - LS) * (1 - RATE) ** 2)
    m = _fake()
    m.unit_ls[(0, 1)] = 0.5
    assert np.allclose(m._build_lift(0), (BUILD1 * (1 - LS), BUILD1 * LS))     # tower 0: site share
    m.tower_idx[0] = 1
    assert np.allclose(m._build_lift(0), (BUILD1 * 0.5, BUILD1 * 0.5))         # tower 1: its own share


def test_start_tower_routes_lift():
    """start_tower(): both build paths (normal, M2 lower part + vault) split via _build_lift and pass lift=; no build
    stage reaches perform() whole any more; perform's handover path prices via _handover_mh."""
    src = inspect.getsource(AM.start_tower)
    assert 'base=self._stage(i, "build")' not in src
    assert src.count('self._build_lift(i, sea_x["xlift"])') == 2
    assert "base=(1.0 - v) * bb, lift=(1.0 - v) * lb" in src and "base=v * bb, credit=False" in src \
        and "lift=v * lb" in src and "base=bb, lift=lb" in src
    assert "self._handover_mh(i, p, stage, base, extra, t_s8, lift)" in src
    assert src.count("lift=lift)") >= 2                                # levy + join paths carry the lift


def test_broker_charge_fallback():
    """charge() without lift (broker walks: w = 0) keeps the old split (nothing booked)."""
    m = _fake()
    m.charge(0, 1, 5.0, "build", 5.0)
    assert m.acc["mh_build"][0] == 0.0 and m.acc["mh_lift"][0] == 0.0 and m.acc["mh_walk"][0] == 5.0


# --------------------------------------------------------------------------- engine B
def test_engine_b_stage_hours_lift_undiscounted():
    """lit.stage_hours (engine B S8 rows): learning scales quarry, dress, build, never lift (every lift rule)."""
    cfg = load_config(CFG)
    L = cfg["lit_scenarios"]
    tw = 4
    f = sum((1.0 - L["learning_rate"]) ** i for i in range(tw)) / tw
    for rule in ("webster", "lever", "stair", "ramp"):
        d = dict(lit.scenario(cfg, "webster"), lift=rule)
        off = lit.stage_hours(cfg, dict(d, learning=False), tw, "basalt", 1200)
        on = lit.stage_hours(cfg, dict(d, learning=True), tw, "basalt", 1200)
        assert off["lift"] > 0 and approx(on["lift"], off["lift"]), rule
        for k in ("quarry", "dress", "build"):
            assert approx(on[k], off[k] * f), (rule, k)


def test_code_version():
    assert alliance.CODE_VERSION == lit.CODE_VERSION == "2026-11-09-v17"


if __name__ == "__main__":
    n_ok = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        fn()
        n_ok += 1
        print(f"PASS {name}")
    print(f"{n_ok} tests passed")
