"""Verification of the literature (chaîne opératoire) scenarios. Run after `model.py --lit all`.

  MPIRUN="mpirun" python tests/verify_lit.py config.yaml

(1) `webster` == `full` (= baseline): every result column, all seeds, full precision; stages sum to the pool.
(2) Rebuilt cost raster at mu = 0.3 == the delivered int raster (all 8 bands, every cell).
(3) Ramp formula against Boswinkel's 3 m example (971-1,208 ph) and his 6 m / 9 m ramp volumes.
(4) Calibration: a single tower with a ~200 m haul under `webster` vs Webster's 3,600 man-days.
(5) Rank independence: -n 1 vs -n 8 on 300 spatially clustered sites for S3e_oxen, S6_density and HIGH.
"""
import glob
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
import lit  # noqa: E402
from nbcommon import load_config  # noqa: E402

MPIRUN = shlex.split(os.environ.get("MPIRUN", "mpirun"))
CFG_PATH = os.path.join(ROOT, "config.yaml")             # B5: replaced by the config given on the command line
COLS = ["seed", "gid", "elapsed_h", "days", "mh_total", "mh_transport", "mh_other", "mh_idle", "builders",
        "n_blocks", "stone_kg", "n_coop", "n_splits", "mh_help", "n_helpers"]


def read_parts(d):
    fr = [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(d, "*.csv")))]
    return pd.concat([f for f in fr if len(f)], ignore_index=True).sort_values(["seed", "gid"]).reset_index(drop=True)


def check_webster(cfg):
    runs = os.path.join(cfg["paths"]["cache_dir"], "runs")
    newest = lambda pat: max(glob.glob(pat), key=os.path.getmtime)        # the current (hybrid) runs
    w = read_parts(newest(os.path.join(runs, "lit_webster", "*")))
    f = read_parts(newest(os.path.join(runs, "full", "*")))
    eq = w[COLS].equals(f[COLS])
    d = float(np.max(np.abs(w.mh_total.to_numpy() - f.mh_total.to_numpy())))
    pool = w.mh_quarry + w.mh_dress + w.mh_build + w.mh_lift
    pool_ok = bool(np.all(pool.to_numpy() == w.mh_other.to_numpy()))
    tw = w.groupby("seed").mh_total.sum(); tf = f.groupby("seed").mh_total.sum()
    print(f"(1) webster vs full: {len(w):,d} site-runs; all {len(COLS)} shared columns identical at full precision: "
          f"{eq}; max |mh_total difference| {d:.3g} h; island totals identical for all {tw.size} seeds: "
          f"{bool((tw == tf).all())}; quarry+dress+build+lift == pool in every row: {pool_ok}")
    s = w[w.seed == 1].iloc[0]
    print(f"    stage split of one 1-tower site-run (seed 1, {s.gid}): quarry {s.mh_quarry:.0f}, dress {s.mh_dress:.0f}, "
          f"build {s.mh_build:.0f}, lift {s.mh_lift:.0f} = {s.mh_other:.0f} ph (Webster 500/1,300/350/350 md x 8 h)")
    assert eq and pool_ok
    return True


def check_raster(cfg):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_cost_mu.py"),
                        CFG_PATH, "0.3", "--check"], capture_output=True, text=True)
    line = [x for x in r.stdout.splitlines() if x.startswith("CHECK")][0]
    print("(2) " + line)
    return r.returncode == 0


def check_ramp(cfg):
    L = cfg["lit_scenarios"]
    b = L["ramp"]["check_boswinkel"]
    w6 = b["vol_6m_m3"] / (0.5 * (6 / L["ramp"]["slope"]) * 6)
    w9 = b["vol_9m_m3"] / (0.5 * (9 / L["ramp"]["slope"]) * 9)
    v3, p3 = lit.ramp_ph_per_tower(L, height=b["height_m"])
    v3b, p3b = lit.ramp_ph_per_tower(L, height=b["height_m"], width=w6)
    vt, pt = lit.ramp_ph_per_tower(L)
    lo, hi = b["range_ph"]
    print(f"(3) ramp: Boswinkel's 6 m and 9 m ramp volumes ({b['vol_6m_m3']}, {b['vol_9m_m3']} m3) imply a width of "
          f"{w6:.2f} / {w9:.2f} m at a 20% slope. A 3 m ramp: {v3:.1f} m3 -> {p3:.0f} ph at our 3.0 m width; "
          f"{v3b:.1f} m3 -> {p3b:.0f} ph at his implied width; Boswinkel {lo:,}-{hi:,} ph -> "
          f"{'IN RANGE' if lo <= p3b <= hi else 'OUT OF RANGE'} (3.0 m width: {'in' if lo <= p3 <= hi else 'below'} range). "
          f"Tower ramp to 15 m: {vt:.1f} m3, {pt:,.0f} ph per tower.")
    return lo <= p3b <= hi


def check_calibration(cfg):
    H = cfg["hours_per_day"]
    s = pd.read_csv(os.path.join(cfg["paths"]["output_dir"], "scenarios_lit", "webster", "nuraghe_manhours_summary.csv"))
    c = s[(s.TWR_N == 1) & (s.haul_flag == "ok")]
    site = c.iloc[(c.haul_m - 200).abs().argsort().iloc[0]]
    print(f"(4) calibration, {site.UID} (1 tower, haul {site.haul_m:.0f} m): total {site.mh_mean / H:,.0f} man-days "
          f"(Webster 3,600; ratio {site.mh_mean / H / 3600:.2f}); quarry {site.mh_qua_mean / H:.0f}, transport "
          f"{site.tr_mean / H:.0f}, dressing {site.mh_dre_mean / H:.0f}, walling {site.mh_bld_mean / H:.0f}, "
          f"lifting {site.mh_lift_mean / H:.0f} man-days (Webster 500 / 1,100 / 1,300 / 700 incl. lifting)")


def check_ranks(cfg):
    h = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    xy = h[["x", "y"]].to_numpy()
    c = np.median(xy, axis=0)
    sel = h.iloc[np.argsort(np.hypot(*(xy - c).T))[:300]]
    tmp = tempfile.mkdtemp(prefix="nuraghe_lit_")
    ok = True
    try:
        for scen in ["S3e_oxen", "S6_density", "HIGH"]:
            res = {}
            for n in (1, 8):
                parts = os.path.join(tmp, f"{scen}_{n}")
                cmd = MPIRUN + ["-n", str(n), sys.executable, os.path.join(ROOT, "model.py"), CFG_PATH,
                                "--lit", scen, "--sites", ",".join(sel.UID), "--seeds", "1-4", "--out",
                                os.path.join(tmp, f"out_{scen}_{n}"), "--parts-dir", parts, "--no-shapefile", "--fresh"]
                subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
                res[n] = read_parts(glob.glob(os.path.join(parts, "lit_" + scen, "*"))[0])
            eq = res[1].equals(res[8])
            ok &= eq
            print(f"(5) {scen}: 300 clustered sites x seeds 1-4, -n 1 vs -n 8 identical (all columns, full precision): {eq}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def main():
    global CFG_PATH
    if len(sys.argv) > 1:
        CFG_PATH = os.path.abspath(sys.argv[1])
    cfg = load_config(CFG_PATH)
    print("Verification of the literature scenarios")
    a = check_webster(cfg)
    b = check_raster(cfg)
    c = check_ramp(cfg)
    check_calibration(cfg)
    d = check_ranks(cfg)
    ok = a and b and c and d
    print("LIT VERIFICATION", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
