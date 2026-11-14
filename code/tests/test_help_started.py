"""Tests of the switch alliance.help_only_if_started (robustness check: in the reference engine a community
whose nuraghe has not started yet could help others). Default false = the published behaviour (every candidate in
range, started or not); true = communities not yet started (help_ok False: start not reached / cohort not yet fired)
are never help candidates (radius requests, tie requests, relays, lintel helpers) nor levy helpers. A season's whole
start batch is marked before its start_tower calls, so batch members can help one another's first towers. Fake models (no kbest / raster loading); the signature test reads
the configuration (NURAGHE_TEST_CONFIG, as the other tests).

  cd code && NURAGHE_TEST_CONFIG=/path/to/config.yaml PYTHONDONTWRITEBYTECODE=1 python tests/test_help_started.py
"""
import copy
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import alliance  # noqa: E402
import census_scenarios  # noqa: E402

CFG = os.environ.get("NURAGHE_TEST_CONFIG", "NURAGHE_TEST_CONFIG-not-set")
AM = alliance.AllianceModel

# 6 communities on a line, 1 km apart; 0 asks. Started: 0, 2, 5. Not started: 1, 3, 4.
XY = np.array([[0.0, 0.0], [1000.0, 0.0], [2000.0, 0.0], [3000.0, 0.0], [4000.0, 0.0], [5000.0, 0.0]])
START = np.array([0, -1, 3, -1, -1, 7], np.int64)


def _fake(flag, max_asks=3, spec=False, ties=None, reach=1, trust=False):
    m = types.SimpleNamespace()
    nb = np.array([1, 2, 3, 4, 5], np.int64)
    m.S = types.SimpleNamespace(xy=XY, nb={0: (nb, XY[nb, 0] - XY[0, 0])})
    m.A = {"max_asks": max_asks}
    m.sc = {"specialisation": spec, "reach": reach, "trust": trust}
    m.help_ok = START >= 0
    m.help_only_started = flag
    m.ties = ties
    m.soc = None
    m.T = lambda i, j: 0.5
    m.skill = lambda j, stage: 1.0
    for n in ("_candidates_R", "tie_candidates", "_candidates", "candidates"):
        setattr(m, n, getattr(AM, n).__get__(m))
    return m


def ids(c):
    return [x[0] for x in c]


def test_init_reads_flag_default_false():
    """__init__ reads alliance.help_only_if_started with a False default (absent key = published behaviour)."""
    import inspect
    src = inspect.getsource(AM.__init__)
    assert 'self.help_only_started = bool(A.get("help_only_if_started", False))' in src


def test_radius_default_keeps_unstarted():
    m = _fake(False)
    assert ids(m._candidates_R(0, "quarry")) == [1, 2, 3, 4, 5]          # current behaviour: distance order, all
    assert ids(m.candidates(0, "quarry")) == [1, 2, 3, 4, 5]


def test_radius_on_drops_unstarted():
    m = _fake(True)
    assert ids(m._candidates_R(0, "quarry")) == [2, 5]
    assert ids(m.candidates(0, "quarry")) == [2, 5]
    assert all(m.help_ok[j] for j in ids(m.candidates(0, "transport")))


def test_radius_on_equals_default_when_all_started():
    a, b = _fake(False), _fake(True)
    a.help_ok[:] = True; b.help_ok[:] = True
    assert a._candidates_R(0, "build") == b._candidates_R(0, "build")


def test_radius_on_with_quarry_filter():
    m = _fake(True)                                                    # quarry at x = 4500: only 5 is nearer than 1000
    assert ids(m._candidates_R(0, "leg1", (4500.0, 0.0), 1000.0)) == [5]
    m = _fake(False)
    assert ids(m._candidates_R(0, "leg1", (4500.0, 0.0), 1000.0)) == [4, 5]


def _ties():
    adj = [set() for _ in range(6)]
    for j in (1, 2, 3, 5):
        adj[0].add(j); adj[j].add(0)
    return {"stone": adj, "move": adj, "build": adj}


def test_ties_default_and_on():
    m = _fake(False, ties=_ties())
    assert ids(m.candidates(0, "quarry")) == [1, 2, 3]                # max_asks = 3, nearest first, unstarted kept
    m = _fake(True, ties=_ties())
    assert ids(m.candidates(0, "quarry")) == [2, 5]                   # filtered BEFORE the max_asks cut


def test_ties_trust_fallback_on():
    m = _fake(True, ties=_ties(), trust=True)
    assert ids(m.candidates(0, "build")) == [2, 5]                    # tie list + radius rest, both filtered
    m = _fake(False, ties=_ties(), trust=True)
    assert ids(m.candidates(0, "build")) == [1, 2, 3, 4, 5]                # tie cut [1, 2, 3] + radius rest [4, 5]


def test_levy_helper():
    def cz(flag):
        m = types.SimpleNamespace(Hh=6.0, B=np.full(6, 10.0), defector=np.zeros(6, bool), help_ok=START >= 0,
                                  help_only_started=flag)
        c = types.SimpleNamespace(m=m, seat=np.ones(6, bool), levy_nb={0: np.array([1, 3, 2])},
                                  levy={"days": 10, "share": 0.5}, levy_used_s=np.zeros(6))
        return census_scenarios.Census.levy_helper.__get__(c)
    assert cz(False)(0) == 1
    assert cz(True)(0) == 2


def _season_fake(flag, phase_frac=None, cohorts=None, start_order=None, start_rate=0.0):
    N = 4
    m = types.SimpleNamespace(N=N, A={"season_days": 90, "start_rate": start_rate}, sc={"start_rate": start_rate},
                              season=0, day=0, cz=None, maint=None, units=None, phase_frac=phase_frac, cohorts=cohorts,
                              cur_phase=-1, current=[None] * N, n_started=0, start_acc=0.0,
                              start_day=np.full(N, -1, np.int64), start_season=np.full(N, -1, np.int64),
                              help_ok=np.zeros(N, bool), help_only_started=flag, active_tasks=[], _order_dirty=True,
                              start_order=start_order, runner=types.SimpleNamespace(stop=lambda: None), seen={})
    m.start_tower = lambda i: m.seen.__setitem__(i, m.help_ok.copy())   # help_ok as start_tower(i) sees it
    m.season_step = AM.season_step.__get__(m)
    return m


def test_cohort_marked_before_start_tower():
    """Phased starts: the whole cohort is eligible before the first start_tower of the cohort (P100 = one cohort)."""
    m = _season_fake(True, phase_frac=0.5, cohorts=[np.array([3, 0]), np.array([1, 2])])
    m.season_step()
    assert set(m.seen) == {3, 0}
    for i in (3, 0):
        assert m.seen[i].tolist() == [True, False, False, True]
    assert (m.start_day[[0, 3]] == 0).all() and (m.start_day[[1, 2]] == -1).all()


def test_rate_batch_marked_before_start_tower():
    m = _season_fake(True, start_order=np.array([2, 0, 1, 3]), start_rate=0.5)   # 2 starts in season 1
    m.season_step()
    assert set(m.seen) == {2, 0}
    for i in (2, 0):
        assert m.seen[i].tolist() == [True, False, True, False]


def test_signature():
    """Absent key and explicit false give the published signature; true gives a new one."""
    if not os.path.exists(CFG):
        print("  (skipped: NURAGHE_TEST_CONFIG not set)")
        return
    import pandas as pd
    from nbcommon import load_config
    cfg = load_config(CFG)
    sc = alliance.scenario(cfg, "MOST_REALISTIC_P10")
    haul = pd.DataFrame({"UID": ["a"], "TWR_N": [1], "haul_flatm": [100.0], "haul_m": [100.0]})
    s0 = alliance.signature(cfg, {k: v for k, v in sc.items() if k != "tech_rules" and k != "sea_kn"}, haul)
    c1 = copy.deepcopy(cfg); c1["alliance"]["help_only_if_started"] = False
    c2 = copy.deepcopy(cfg); c2["alliance"]["help_only_if_started"] = True
    sc2 = {k: v for k, v in sc.items() if k != "tech_rules" and k != "sea_kn"}
    assert alliance.signature(c1, sc2, haul) == s0
    assert alliance.signature(c2, sc2, haul) != s0


if __name__ == "__main__":
    n = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            f()
            print("PASS", name)
            n += 1
    print(f"{n} tests passed")
