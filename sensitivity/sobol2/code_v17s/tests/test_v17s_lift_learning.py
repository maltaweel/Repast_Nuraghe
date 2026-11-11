"""code_v17s tests (10 Nov 2026): config flag sobol.lift_learning (Sobol run 2 factor "lift_learning").

  default False / absent = code_v17 exactly (SP-22: lift priced undiscounted)
  True                   = the v16_final behaviour: lift is part of the build skill stage, discounted by S8 learning
                           (PM:23) and A3 skill (PM:173), and split into mh_build / mh_lift by the lift share afterwards.

Fake models with the real methods (no simulation), engine B against code_v16_final's own lit.stage_hours (subprocess),
the source of start_tower / perform, and the run signatures. The full-model equality checks (seeds 1-2 of the headline,
code_v17 vs code_v17s default-off byte for byte; flag on vs v16_final mh_lift) are in
runs/2026-11-10-sobol2-v17/checks/ (check_v17s.py).

  cd code_v17s && PYTHONDONTWRITEBYTECODE=1 python tests/test_v17s_lift_learning.py
"""
import inspect
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import test_v17_lift as T  # noqa: E402  (the code_v17 fakes; asserts alliance / lit come from this code dir)
from test_v17_lift import AM, BUILD1, CFG, LS, RATE, alliance, approx, lit, load_config  # noqa: E402

assert os.path.basename(os.path.dirname(HERE)) == "code_v17s"
V16 = os.path.join(os.path.dirname(os.path.dirname(HERE)), "code_v16_final")
PY = sys.executable


def _fake(flag, **kw):
    m = T._fake(**kw)
    if flag is not None:
        m.lift_learning = flag
    return m


def _tower(m, t, xlift=0.0):
    """One tower t of owner 0 built by its own party, priced exactly as perform()'s handover path does it with the flag
    -> (d mh_build, d mh_lift, task mh)."""
    m.tower_idx[0] = t
    b0, l0 = m.acc["mh_build"][0], m.acc["mh_lift"][0]
    bb, lb = m._build_lift(0, xlift)
    mh = m._handover_mh(0, 0, "build", bb, 0.0, t, lb)
    m.add_task(0, mh, "build")
    m.charge(0, 0, mh, "build", 0.0, lift=None if getattr(m, "lift_learning", False) else lb)
    return m.acc["mh_build"][0] - b0, m.acc["mh_lift"][0] - l0, mh


# --------------------------------------------------------------------------- flag reader
def test_flag_reader():
    assert lit.lift_learning({}) is False
    assert lit.lift_learning({"sobol": None}) is False
    assert lit.lift_learning({"sobol": {}}) is False
    assert lit.lift_learning({"sobol": {"lift_learning": False}}) is False
    assert lit.lift_learning({"sobol": {"lift_learning": True}}) is True
    cfg = load_config(CFG)
    assert "sobol" not in cfg and lit.lift_learning(cfg) is False          # the headline config: default off


# --------------------------------------------------------------------------- season engine
def test_default_off_equals_v17():
    """Flag absent or False: every price and booking identical (==) to code_v17's (the fakes of test_v17_lift)."""
    for xl in (0.0, 40.0):
        ref = T._fake()
        rows_ref = [T._tower_handover(ref, t, xl) for t in range(5)]
        for flag in (None, False):
            m = _fake(flag)
            rows = [_tower(m, t, xl)[:2] for t in range(5)]
            assert rows == rows_ref, (flag, rows, rows_ref)
            assert all(np.array_equal(m.acc[k], ref.acc[k]) for k in m.acc)
    for f in (0.0, 0.3, 0.8):
        a, b = T._fake(skill={0: 1.0, 1: 0.6}, f=f), _fake(False, skill={0: 1.0, 1: 0.6}, f=f)
        for m in (a, b):
            m.tower_idx[0] = 3
            bb, lb = m._build_lift(0)
            m._perform_join(0, 1, "build", (0.0, 0.0), -1, True, bb, 0.0, 3, 100, {}, lift=lb)
        assert a.tasks == b.tasks and all(np.array_equal(a.acc[k], b.acc[k]) for k in a.acc)


def test_on_v16_handover_learning_and_skill():
    """Flag on, own party: tower t costs (build + lift) x min(skill, (1 - rate)^t) (v16_final), mh_lift = that x the
    lift share; xlift sits inside the discounted stage (v16_final) and is split by the share."""
    for xl in (0.0, 40.0):
        m = _fake(True)
        for t in range(5):
            b, l, mh = _tower(m, t, xl)
            tot = (BUILD1 + xl) * (1 - RATE) ** t
            assert approx(mh, tot) and approx(l, tot * LS) and approx(b, tot * (1 - LS)), (xl, t, b, l)
    m = _fake(True, skill={0: 0.7, 1: 0.6}, s8_rate=0.0)
    bb, lb = m._build_lift(0)
    assert (bb, lb) == (BUILD1, 0.0)
    assert m._handover_mh(0, 0, "build", bb, 0.0, 3, lb) == BUILD1 * 0.7          # v16: base x skill + extra, exactly
    assert m._handover_mh(0, 1, "build", bb, 0.0, 3, lb) == BUILD1 * 0.6
    m = _fake(True, skill={0: 0.8}, tech=False)                                      # Webster, no tech: A3 skill only
    b, l, mh = _tower(m, 2)
    assert approx(l, BUILD1 * 0.8 * LS) and approx(b, BUILD1 * 0.8 * (1 - LS))


def test_on_v16_join():
    """Flag on, join: owner part base (1 - f) x owner factor, helper part base f x helper skill (v16_final D6), lift
    inside both and booked by the share (no exact lift parts)."""
    for f in (0.0, 0.3, 0.8):
        m = _fake(True, skill={0: 1.0, 1: 0.6}, f=f)
        t = 3
        m.tower_idx[0] = t
        bb, lb = m._build_lift(0)
        m._perform_join(0, 1, "build", (0.0, 0.0), -1, True, bb, 0.0, t, 100, {}, lift=lb)
        mo = BUILD1 * (1 - f) * (1 - RATE) ** t
        mh_h = BUILD1 * f * 0.6
        assert m.tasks[0][1] == mo
        if f > 0:
            assert m.tasks[1][1] == mh_h
        assert approx(m.acc["mh_lift"][0], (mo + mh_h) * LS) and approx(m.acc["mh_build"][0], (mo + mh_h) * (1 - LS))


def test_on_differs_from_off():
    """Guard: with S8 on, flag on lowers tower 3's lift (discounted) and leaves tower 0's unchanged."""
    on, off = _fake(True), _fake(False)
    r_on = [_tower(on, t)[1] for t in range(4)]
    r_off = [_tower(off, t)[1] for t in range(4)]
    assert approx(r_on[0], r_off[0]) and r_on[3] < r_off[3] and approx(r_on[3], r_off[3] * (1 - RATE) ** 3)


def test_source_routes():
    """The flag is read once in AllianceModel.__init__ (lit.lift_learning(cfg)); perform() books lift=None when on."""
    assert "self.lift_learning = lit.lift_learning(cfg)" in inspect.getsource(AM.__init__)
    src = inspect.getsource(AM.start_tower)
    assert 'lift=lift if stage == "build" and not self.lift_learning else None' in src
    assert 'if stage == "build" and not getattr(self, "lift_learning", False)' in inspect.getsource(AM._perform_join)
    assert "lit.lift_learning(cfg)" in inspect.getsource(alliance.signature)


# --------------------------------------------------------------------------- engine B vs code_v16_final
def test_engine_b_on_equals_v16_final():
    """lit.stage_hours with the flag on == code_v16_final's lit.stage_hours (run in a subprocess from code_v16_final),
    for every lift rule, learning on and off; flag off: lift undiscounted (code_v17)."""
    rules = ("webster", "lever", "stair", "ramp")
    prog = ("import json, sys, lit; from nbcommon import load_config; c = load_config(sys.argv[1]); "
            "print(json.dumps({r + str(l): lit.stage_hours(c, dict(lit.scenario(c, 'webster'), lift=r, learning=l), "
            "4, 'basalt', 1200) for r in %r for l in (False, True)}))" % (rules,))
    out = subprocess.run([PY, "-c", prog, CFG], cwd=V16, capture_output=True, text=True,
                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=""), check=True).stdout
    ref = json.loads(out.strip().splitlines()[-1])
    cfg = load_config(CFG)
    on = dict(cfg, sobol={"lift_learning": True})
    for r in rules:
        for ln in (False, True):
            d = dict(lit.scenario(cfg, "webster"), lift=r, learning=ln)
            got = lit.stage_hours(on, d, 4, "basalt", 1200)
            assert got == ref[r + str(ln)], (r, ln, got, ref[r + str(ln)])          # exact, as v16_final
            off = lit.stage_hours(cfg, d, 4, "basalt", 1200)
            assert off["lift"] == lit.stage_hours(cfg, dict(d, learning=False), 4, "basalt", 1200)["lift"]
            if ln:
                assert got["lift"] < off["lift"]


def test_code_version_unchanged():
    assert alliance.CODE_VERSION == lit.CODE_VERSION == "2026-11-09-v17"


if __name__ == "__main__":
    n_ok = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)
                           and getattr(v, "__module__", "") == "__main__"):
        fn()
        n_ok += 1
        print(f"PASS {name}")
    print(f"{n_ok} tests passed")
