"""Verification of the alliance scenarios.

  MPIRUN="mpirun" python tests/verify_alliance.py config.yaml [--no-mpi]

(1) A0_verify (no requests, b = 1, no tracks, setup 0, cheapest face) == `webster` per-site man-hours, all seeds.
(2) Trust update rules on a 3-community toy.
(3) Relay additivity: leg 1 + leg 2 == the single route (drag cost exactly; trip time and labour to float precision).
(4) Rank independence: -n 1 vs -n 8 on a 300-site spatial cluster (A5_full_freerider, seeds 1-4).
"""
import glob
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import alliance  # noqa: E402
from nbcommon import load_config  # noqa: E402

MPIRUN = shlex.split(os.environ.get("MPIRUN", "mpirun"))
CFG_PATH = os.path.join(ROOT, "config.yaml")             # B5: replaced by the config given on the command line


def check_a0(cfg):
    runs = os.path.join(cfg["paths"]["cache_dir"], "runs")
    newest = lambda pat: max(glob.glob(pat), key=os.path.getmtime)        # the current (hybrid) runs
    w = pd.concat([pd.read_csv(f) for f in glob.glob(os.path.join(newest(os.path.join(runs, "lit_webster", "*")), "seed_*.rank*.csv"))])
    a = pd.concat([pd.read_csv(f) for f in glob.glob(os.path.join(newest(os.path.join(runs, "alliance_A0_verify", "*")), "seed_*.sites.csv.gz"))])
    seeds = sorted(set(a.seed))
    w = w[w.seed.isin(seeds)].sort_values(["seed", "gid"]).reset_index(drop=True)
    a = a.sort_values(["seed", "gid"]).reset_index(drop=True)
    assert len(a) == len(w)
    d = np.abs(a.mh_total.to_numpy() - w.mh_total.to_numpy())
    dt = np.abs(a.mh_transport.to_numpy() - w.mh_transport.to_numpy())
    pool = (a.mh_quarry + a.mh_dress + a.mh_build + a.mh_lift + a.mh_setup).to_numpy()
    dp = np.abs(pool - w.mh_other.to_numpy())
    rel = d / w.mh_total.to_numpy()
    print(f"(1) A0_verify vs webster: {len(a):,d} site-runs (seeds {seeds[0]}-{seeds[-1]}); bitwise equal {int((d == 0).sum()):,d}; "
          f"max |difference| {d.max():.3g} man-hours (max relative {rel.max():.3g}); stage pool difference max {dp.max():.3g}; "
          f"transport max {dt.max():.3g}. The only differences are floating-point summation order: webster's "
          f"mh_total = builders x elapsed hours from the daily kernel, A0's = sum of stage labour (idle = 0 in both).")
    ok = d.max() < 1e-6
    assert ok
    return ok


class _Rng:
    def __init__(self, seq):
        self.seq = list(seq)

    def random(self):
        return self.seq.pop(0)


def check_trust(cfg):
    """3 communities 0, 1, 2. Draws are scripted so each answer is known."""
    m = object.__new__(alliance.AllianceModel)
    A = dict(cfg["alliance"])
    m.A = A
    m.sc = {"trust": True}
    m.trust, m.received_from = {}, set()
    m.defector = np.array([False, False, True])
    m.backlog_days = lambda j: 0.0
    m.asks, m.asks_stage, m.allied_season, m.tie_refusals = {}, {}, {}, {}
    m.ties, m.season, m._broker, m.P_tie = None, 0, None, 0.9
    t0, du, dd = A["trust0"], A["delta_up"], A["delta_down"]
    out = []
    # a) 0 asks 1, 1 accepts (draw 0.0 < p): 0's trust in 1 rises by delta_up; 0 has received help from 1
    m.rng = [_Rng([]), _Rng([0.0]), _Rng([])]
    h = m.request(0, "quarry", (0, 0), [(1, 1000.0, "R", 0, ())])
    out.append(h == 1 and abs(m.T(0, 1) - (t0 + du)) < 1e-12 and (0, 1) in m.received_from)
    # b) 1 asks 0, 0 refuses (draw 1.0): 0 had received help from 1 -> 1's trust in 0 falls by delta_down
    m.rng = [_Rng([1.0]), _Rng([]), _Rng([])]
    h = m.request(1, "quarry", (0, 0), [(0, 1000.0, "R", 0, ())])
    out.append(h == -1 and abs(m.T(1, 0) - (t0 - dd)) < 1e-12)
    # c) 2 (a defector) asks 1: 1 accepts; then 1 asks 2: the defector refuses after having received help -> trust falls
    m.rng = [_Rng([]), _Rng([0.0]), _Rng([])]
    m.request(2, "dress", (0, 0), [(1, 1000.0, "R", 0, ())])
    m.rng = [_Rng([]), _Rng([]), _Rng([])]
    h = m.request(1, "dress", (0, 0), [(2, 1000.0, "R", 0, ())])
    out.append(h == -1 and abs(m.T(1, 2) - (t0 - dd)) < 1e-12)
    # d) refusal without prior help: no change (2 asks 0, 0 refuses; 2 never helped 0)
    m.rng = [_Rng([1.0]), _Rng([]), _Rng([])]
    m.request(2, "build", (0, 0), [(0, 1000.0, "R", 0, ())])
    out.append(abs(m.T(2, 0) - t0) < 1e-12)
    # e) acceptance probability: sigma(beta0 + beta1 T - beta2 backlog - beta3 km) at trust0, 5 km
    p = alliance.sigmoid(A["beta0"] + A["beta1"] * t0 - A["beta3"] * 5.0)
    out.append(abs(p - 1 / (1 + math.exp(-(A["beta0"] + A["beta1"] * t0 - A["beta3"] * 5.0)))) < 1e-15)
    # f) alliance = mutual trust >= threshold
    m.trust = {(0, 1): 0.8, (1, 0): 0.75, (0, 2): 0.9, (2, 0): 0.2}
    out.append(m.allied(0, 1) and not m.allied(0, 2))
    names = ["accept raises trust", "refusal after help lowers trust", "defector refusing after help loses trust", "no penalty w/o debt",
             "acceptance logistic", "alliance = mutual threshold"]
    print("(2) trust toy (3 communities): " + "; ".join(f"{n}: {'OK' if o else 'FAIL'}" for n, o in zip(names, out))
          + f"  [trust0 {t0}, +{du}, -{dd}, accept p at trust0 and 5 km = {p:.3f}]")
    return all(out)


def check_relay(cfg):
    h = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    h["uid_int"] = h.UID.str[3:].astype(np.int64)
    S = alliance.Static(cfg, h)
    m = object.__new__(alliance.AllianceModel)
    m.S, m.A, m.tp, m.track_owner = S, cfg["alliance"], cfg["transport"], {}
    n = cmax = tmax = mmax = 0
    for i, faces in enumerate(S.faces):
        for f in faces:
            if f["route"] < 0:
                continue
            for fr, nmv in f["handoff"].items():
                a, b, hcut = f["a"], f["b"], f["a"] + nmv
                C1, C2 = S.mv_c03[a:hcut].sum(), S.mv_c03[hcut:b].sum()
                L1, L2 = S.mv_len[a:hcut].sum(), S.mv_len[hcut:b].sum()
                Cr, Lr = S.mv_c03[a:b].sum(), S.mv_len[a:b].sum()
                cmax = max(cmax, abs(C1 + C2 - Cr))
                single = Cr / m.tp["drag_speed_ms"] / 3600 + Lr / m.tp["return_walk_ms"] / 3600 + m.tp["load_unload_h"]
                tmax = max(tmax, abs(m.trip(C1, L1, "leg") + m.trip(C2, L2, "leg") - single))
                S03 = 2500
                m1, _ = m.leg_mh(i, f, a, hcut, S03, 900, "leg"); m2, _ = m.leg_mh(i, f, hcut, b, S03, 900, "leg")
                mmax = max(mmax, abs(m1 + m2 - S03 * single))
                n += 1
    ok = cmax == 0 and tmax < 1e-9 and mmax < 1e-6
    print(f"(3) relay additivity over {n:,d} (route, fraction) pairs: |C1 + C2 - C| max {cmax:g} (exact integers); "
          f"|trip1 + trip2 - trip| max {tmax:.3g} h; |labour leg1 + leg2 - single| max {mmax:.3g} man-hours "
          f"(2,500 crew-units) -> {'OK' if ok else 'FAIL'}")
    return ok


def check_ranks(cfg):
    h = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    xy = h[["x", "y"]].to_numpy()
    c = np.median(xy, axis=0)
    sel = h.iloc[np.argsort(np.hypot(*(xy - c).T))[:300]]
    tmp = tempfile.mkdtemp(prefix="nuraghe_all_")
    res = {}
    try:
        for n in (1, 8):
            parts = os.path.join(tmp, f"p{n}")
            cmd = MPIRUN + ["-n", str(n), sys.executable, os.path.join(ROOT, "model.py"), CFG_PATH,
                            "--alliance", "A5_full_freerider", "--sites", ",".join(sel.UID), "--seeds", "1-4",
                            "--out", os.path.join(tmp, f"o{n}"), "--parts-dir", parts, "--no-shapefile", "--fresh"]
            subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
            d = glob.glob(os.path.join(parts, "alliance_A5_full_freerider", "*"))[0]
            res[n] = {k: pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(d, f"*.{k}.csv.gz")))])
                      .reset_index(drop=True) for k in ("sites", "pairs", "strategy")}
        eq = all(res[1][k].equals(res[8][k]) for k in res[1])
        s = res[1]["sites"]
        print(f"(4) rank independence, A5_full_freerider, 300 clustered sites x seeds 1-4: -n 1 vs -n 8 identical "
              f"(sites, pairs, strategies; full precision): {eq}; help received {s.mh_received.sum():,.0f} man-hours, "
              f"{int(res[1]['pairs'].allied.sum())} allied pairs")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return eq


def main():
    global CFG_PATH
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        CFG_PATH = os.path.abspath(sys.argv[1])
    cfg = load_config(CFG_PATH)
    print("Verification of the alliance scenarios")
    a = check_a0(cfg)
    b = check_trust(cfg)
    c = check_relay(cfg)
    d = check_ranks(cfg) if "--no-mpi" not in sys.argv else True
    ok = a and b and c and d
    print("ALLIANCE VERIFICATION", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
