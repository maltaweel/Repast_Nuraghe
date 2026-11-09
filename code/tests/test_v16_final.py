"""code_v16_final tests (5 Nov 2026): D3 (no dress work = no dress task traffic), D6 (join parties priced at their own
skill), D11 (the site's stone = the class of its gated face 0), run signature (CODE_VERSION + add4 settings).
Unit tests use fake models (no kbest / raster loading); test_D11_tables reads the real headline cache tables (kbest
meta + outcrop_code.tif + haul csvs, < 300 MB). The run-level checks (test_D3_parts) read the part files of the
headline seeds 1-3 check run when V16F_PARTS (a parts dir with seed_NNNN.* files) is set, else they are skipped.

  cd code_v16_final && PYTHONDONTWRITEBYTECODE=1 python tests/test_v16_final.py
  V16F_PARTS=<run dir> python tests/test_v16_final.py        (adds the run-level D3 checks)
"""
import copy
import glob
import inspect
import os
import sys
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import alliance  # noqa: E402
import lit  # noqa: E402
import model  # noqa: E402
from nbcommon import load_config  # noqa: E402

FA = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "runs/2026-11-02-v12-census/full_audited")
CFG = FA + "/v15c_norelayfilter/configs/config_full_audited.yaml"
AM = alliance.AllianceModel


def approx(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


# --------------------------------------------------------------------------- fake model for the task layer
def _fake(f=0.3, sk=None, s8_rate=0.15, tech=True):
    m = types.SimpleNamespace()
    m.tasks, m.charges = [], []
    m.cum = np.zeros((3, len(alliance.SKILL_STAGES)))
    m.trust = {}
    m.B = np.array([40.0, 60.0, 20.0])
    m.tp = {"return_walk_ms": 1.4}
    m.sc = {"specialisation": True}
    m.S = types.SimpleNamespace(tech={} if tech else None)
    m.s8_rate = s8_rate
    m.join_part = {}
    sk = sk or {0: 0.9, 1: 0.6, 2: 1.0}
    m.skill = lambda j, stage: sk[j]
    m._join_split = lambda i, h, stage, nblk: f
    m.wdist = lambda p, loc, tgt=None: 1400.0                     # 1,400 m -> walk = B x 1/3600 h... per person
    m.request = lambda *a, **k: (_ for _ in ()).throw(AssertionError("request must not be called"))

    def add_task(perf, total, stage, up=-1, final=False):
        m.tasks.append((perf, total, stage, up, final))
        return len(m.tasks) - 1

    def charge(owner, perf, mh, stage, walk=0.0, lift=None):     # code_v17: lift kwarg (build stage)
        m.charges.append((owner, perf, mh, stage, walk))
    m.add_task, m.charge = add_task, charge
    for n in ("_owner_skill", "_join_task", "_perform_join", "_no_work_task"):
        setattr(m, n, getattr(AM, n).__get__(m))
    return m


# --------------------------------------------------------------------------- D3
def test_D3_no_work_task():
    m = _fake()
    t = m._no_work_task(0, "dress", 7, False)
    assert m.tasks == [(0, 0.0, "dress", 7, False)]               # the owner's 0-MH task keeps the chain order
    assert t == 0 and m.charges == [] and m.trust == {} and not m.cum.any()   # no charge, credit, trust


def test_D3_perform_routes_zero_work_first():
    """perform(): the zero-work test comes before the levy and before any request (so no ask, draw or trust)."""
    src = inspect.getsource(AM.start_tower)
    body = src[src.index("def perform("):]
    z = body.index("return self._no_work_task(i, stage, up, final)")
    assert "base is not None and base <= 0.0 and extra <= 0.0" in body[:z]
    assert z < body.index("levy_helper") and z < body.index("self.request(") and z < body.index("self.cum[p")


def _sites_of(parts, s):
    return pd.read_csv(f"{parts}/seed_{s:04d}.sites.csv.gz")


def test_D3_parts():
    """Run level (headline seeds of the check run): no dress ask, help or helper walk for 1-tower owners, and the
    dress credits equal the towers that have dressing work (TWR_N >= 2; one credit per dressed tower)."""
    parts = os.environ.get("V16F_PARTS")
    if not parts:
        print("   (skipped: V16F_PARTS not set)")
        return
    seeds = sorted(int(os.path.basename(p)[5:9]) for p in glob.glob(f"{parts}/seed_*.done"))
    assert seeds
    for s in seeds:
        st = _sites_of(parts, s)
        tw = st.set_index("gid").TWR_N
        pr = pd.read_csv(f"{parts}/seed_{s:04d}.pairs.csv.gz")
        own_a, own_b = tw.reindex(pr.a).to_numpy(), tw.reindex(pr.b).to_numpy()
        # n_ab_dress: tasks a did for b (owner b); n_ba_dress: b for a (owner a). asks_ab_*: a asked b (owner a)
        one = ((own_b == 1) & ((pr.n_ab_dress > 0) | (pr.help_ab_dress > 0))) | \
              ((own_a == 1) & ((pr.n_ba_dress > 0) | (pr.help_ba_dress > 0)))
        asks = ((own_a == 1) & (pr.asks_ab_dress > 0)) | ((own_b == 1) & (pr.asks_ba_dress > 0))
        assert not one.any(), f"seed {s}: {int(one.sum())} pairs with dress help on 1-tower owners"
        assert not asks.any(), f"seed {s}: {int(asks.sum())} pairs with dress asks by 1-tower owners"
        assert (st.loc[st.TWR_N == 1, "mh_dress"] == 0).all()
        sp = pd.read_csv(f"{parts}/seed_{s:04d}.spec.csv.gz")
        assert sp.cum_dress.sum() == st.loc[st.TWR_N >= 2, "TWR_N"].sum(), (s, sp.cum_dress.sum())
        print(f"   seed {s}: dress credits {int(sp.cum_dress.sum())} = towers with dressing; 0 dress asks/help on 1-tower")


# --------------------------------------------------------------------------- D6
def test_D6_join_each_party_own_skill():
    f, base, extra, t_i = 0.3, 1000.0, 50.0, 2
    m = _fake(f=f)
    cur = {}
    m._perform_join(0, 1, "dress", (0.0, 0.0), -1, False, base, extra, t_i, 100, cur)
    sk_o = min(0.9, (1 - 0.15) ** t_i)                          # owner: larger discount of A3 skill and S8
    mo = base * (1 - f) * sk_o + extra * (1 - f)
    walk = 60.0 * 1400.0 / 1.4 / 3600.0
    mh_h = base * f * 0.6 + extra * f                            # helper: its own A3 skill (0.6)
    (po, to, *_), (ph, th, *_) = m.tasks
    assert po == 0 and approx(to, mo) and ph == 1 and approx(th, mh_h + walk)
    assert approx(m.charges[0][2], mo) and approx(m.charges[1][2], mh_h + walk) and approx(m.charges[1][4], walk)
    # old rule (main performer = owner since f <= 0.5): the whole stage at the owner's factor
    old_h = (base * sk_o + extra) * f
    assert not approx(th - walk, old_h)
    # credit unchanged: the main performer (owner here) gets one dress credit
    k = alliance.SKILL_STAGES.index("dress")
    assert m.cum[0, k] == 1 and m.cum[1, k] == 0 and cur["join_share"]["dress"] == f


def test_D6_helper_main_performer():
    f, base = 0.8, 1000.0
    m = _fake(f=f)
    m._perform_join(0, 1, "quarry", (0.0, 0.0), -1, False, base, 0.0, 0, 100, {})
    (_, to, *_), (_, th, *_) = m.tasks
    walk = 60.0 * 1400.0 / 1.4 / 3600.0
    assert approx(to, base * 0.2 * min(0.9, 1.0)) and approx(th - walk, base * 0.8 * 0.6)
    assert m.cum[1, alliance.SKILL_STAGES.index("quarry")] == 1  # helper is main performer -> credit (specialisation)


def test_D6_no_tech_owner_skill_only():
    m = _fake(f=0.4, tech=False)
    m._perform_join(0, 2, "build", (0.0, 0.0), -1, True, 500.0, 0.0, 3, 100, {})
    (_, to, *_), (_, th, *_) = m.tasks
    walk = 20.0 * 1400.0 / 1.4 / 3600.0
    assert approx(to, 500.0 * 0.6 * 0.9) and approx(th - walk, 500.0 * 0.4 * 1.0)


def test_D6_relay_leg1_unchanged():
    """relay leg 1 (no skill) still splits the given man-hours by f (parts=None path)."""
    m = _fake(f=0.25)
    m._join_task(0, 1, "leg1", 400.0, (0.0, 0.0), -1, False, 10)
    (_, to, *_), (_, th, *_) = m.tasks
    walk = 60.0 * 1400.0 / 1.4 / 3600.0
    assert approx(to, 300.0) and approx(th, 100.0 + walk)


# --------------------------------------------------------------------------- D11
def test_D11_face0_stone_alignment():
    ns = types.SimpleNamespace(haul=pd.DataFrame({"UID": ["a", "b", "c"], "quarry_stone": ["granite", "basalt", "x"]}))
    tab = pd.DataFrame({"UID": ["c", "a", "b"], "quarry_stone": ["basalt", "basalt", "basalt"]})
    assert list(alliance.Static._face0_stone(ns, tab)) == ["x", "granite", "basalt"]
    src = inspect.getsource(alliance.Static._init_tech)
    assert 'mh["quarry_stone"] = self._face0_stone(mh)' in src
    assert src.index('mh["quarry_stone"] = self._face0_stone(mh)') < src.index('"stone": mh.quarry_stone.to_numpy()')


def d11_tables(cfg):
    """Face-0 class (kbest face 0 cell on the cache outcrop raster) vs sites_haul.csv quarry_stone, and the sites
    whose stone the reference (mixed-table) rule changed. Returns (n_sites, n_face0_equal, diff DataFrame)."""
    import rasterio
    C = cfg["paths"]["cache_dir"]
    base = pd.read_csv(os.path.join(C, "sites_haul.csv"))
    with rasterio.open(os.path.join(C, "outcrop_code.tif")) as r:
        code = r.read(1)
        cm = {int(k): v for k, v in (t.split("=") for t in r.tags()["codes"].split(";"))}
    kb = np.load(os.path.join(C, "alliance", "kbest.npz"))
    meta = pd.DataFrame(kb["meta"])
    f0 = meta[meta.q == 0].set_index("gid").reindex(np.arange(len(base)))
    has = f0.qrow.notna().to_numpy()
    cls = np.array([cm.get(int(code[int(a), int(b)]), "none") if h else s
                    for a, b, h, s in zip(f0.qrow.fillna(0), f0.qcol.fillna(0), has, base.quarry_stone)])
    L = lit.scenario(cfg, "REALISTIC")
    load = lambda p: pd.read_csv(p).set_index("UID").reindex(base.UID).reset_index()   # noqa: E731
    mh = lit.mixed_haul(cfg, L, load)
    ref, new = mh.quarry_stone.to_numpy(), base.quarry_stone.to_numpy()
    Ls = cfg["lit_scenarios"]
    den, wd, hd = Ls["density_kg_m3"], Ls["webster_density_kg_m3"], Ls["hardness"]
    d = pd.DataFrame({"UID": base.UID, "TWR_N": base.TWR_N, "rule": mh.lit_haul_rule, "stone_mixed": ref,
                      "stone_face0": new,
                      "mass_factor_mixed": [den.get(s, wd) / wd for s in ref],
                      "mass_factor_face0": [den.get(s, wd) / wd for s in new],
                      "hardness_mixed": [hd.get(s, 1.0) for s in ref], "hardness_face0": [hd.get(s, 1.0) for s in new]})
    d = d[d.stone_mixed != d.stone_face0]
    return len(base), int((cls == new).sum()), d


def test_D11_tables():
    """No table rebuild: the gated face-0 class is already the quarry_stone of the cache's sites_haul.csv."""
    cfg = load_config(CFG)
    n, eq, d = d11_tables(cfg)
    assert eq == n == 7167, (eq, n)
    nt = int((d.mass_factor_mixed != d.mass_factor_face0).sum())
    nh = int((d.hardness_mixed != d.hardness_face0).sum())
    print(f"   face0 class == sites_haul.quarry_stone at {eq}/{n}; stone changes at {len(d)} UIDs "
          f"({int((d.rule == 'long').sum())} rails row, {int((d.rule == 'short').sum())} dry row): tonnes {nt}, hardness {nh}")
    assert nt == 27


# --------------------------------------------------------------------------- signature
def test_signature_code_version_and_add4():
    cfg = load_config(CFG)
    sc = alliance.scenario(cfg, "MOST_REALISTIC_AUDITED_LIT_P10")
    sc = {k: v for k, v in sc.items() if k != "sea_kn"}        # no sea table read in this unit test
    haul = pd.DataFrame({"UID": ["a"], "TWR_N": [1], "haul_flatm": [1.0], "haul_m": [1.0]})
    assert alliance.CODE_VERSION == lit.CODE_VERSION == "2026-11-09-v17"     # code_v17 (was 2026-11-05-v16_final)
    s0 = alliance.signature(cfg, sc, haul)
    old = alliance.CODE_VERSION
    try:
        alliance.CODE_VERSION = "other"
        assert alliance.signature(cfg, sc, haul) != s0         # code version is hashed
    finally:
        alliance.CODE_VERSION = old
    c2 = copy.deepcopy(cfg); c2["add4"] = {"load_per_tonne": False}
    assert alliance.signature(c2, sc, haul) != s0              # any add4 value is hashed (also switching one off)
    c3 = copy.deepcopy(cfg); c3["add4"] = {"load_ph_per_t": 1.2}
    assert alliance.signature(c3, sc, haul) == s0              # effective settings: explicit default = same
    # model.py run_signature (coop / lit / tost / baseline rows)
    hl = haul.assign(quarry_stone=["basalt"])
    scm = model.scenario_params(cfg, None)
    m0 = model.run_signature(cfg, hl, scm)
    assert model.run_signature(c2, hl, scm) != m0
    oldl = lit.CODE_VERSION
    try:
        lit.CODE_VERSION = "other"
        assert model.run_signature(cfg, hl, scm) != m0
    finally:
        lit.CODE_VERSION = oldl


if __name__ == "__main__":
    n_ok = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        fn()
        n_ok += 1
        print(f"PASS {name}")
    print(f"{n_ok} tests passed")
