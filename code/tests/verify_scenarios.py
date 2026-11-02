"""Verification of the cooperation scenarios (run after `model.py --scenario all`).

  MPIRUN="mpirun" python tests/verify_scenarios.py config.yaml

(1) `full` reproduces the baseline exactly (all seeds, full precision, every original column).
(2) `none`: hand-check the split count of 2 sites against an independent replay of the block draw.
(3) Rank independence of `high` and `patchwork`: -n 1 vs -n 8 on 300 spatially clustered sites.
(4) Is island man-hours monotone in p_coop? (reported, not forced)
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
from nbcommon import load_config  # noqa: E402

MPIRUN = shlex.split(os.environ.get("MPIRUN", "mpirun"))
CFG_PATH = os.path.join(ROOT, "config.yaml")             # B5: replaced by the config given on the command line
BASE_COLS = ["seed", "gid", "elapsed_h", "days", "mh_total", "mh_transport", "mh_other", "mh_idle", "builders",
             "n_blocks", "stone_kg"]


def read_parts(d):
    fr = [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(d, "*.csv")))]
    return pd.concat([f for f in fr if len(f)], ignore_index=True).sort_values(["seed", "gid"]).reset_index(drop=True)


def check_full(cfg):
    runs = os.path.join(cfg["paths"]["cache_dir"], "runs")
    newest = lambda pat: max(glob.glob(pat), key=os.path.getmtime)
    import model
    class _A: sites = None; first_n = None
    h = model.load_haul(cfg, _A, os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    sig = model.run_signature(cfg, h, model.scenario_params(cfg, None))      # the hybrid baseline, not stones7
    ref_dirs = [os.path.join(runs, "baseline", sig)] if os.path.isdir(os.path.join(runs, "baseline", sig)) else []
    full_dirs = [newest(os.path.join(runs, "full", "*"))] if glob.glob(os.path.join(runs, "full", "*")) else []
    ok = True
    if ref_dirs and full_dirs:
        a = read_parts(ref_dirs[0])[BASE_COLS]
        b = read_parts(full_dirs[0])[BASE_COLS]
        eq = a.shape == b.shape and a.equals(b)
        print(f"(1) full vs baseline part files ({len(a):,d} rows, columns {', '.join(BASE_COLS[2:])}): "
              f"identical at full precision: {eq}")
        ok &= eq
    ref = os.path.join(cfg["paths"]["output_dir"], "nuraghe_manhours_runs.csv.gz")      # the current baseline
    a = pd.read_csv(ref)
    b = pd.read_csv(os.path.join(cfg["paths"]["output_dir"], "scenarios", "full", "nuraghe_manhours_runs.csv.gz"))
    cols = [c for c in a.columns]
    eq2 = a[cols].equals(b[cols])
    eqmh = bool((a.mh_total.to_numpy() == b.mh_total.to_numpy()).all()) and a.shape[0] == b.shape[0]
    print(f"    full runs.csv.gz vs baseline runs.csv.gz ({len(a):,d} rows, seeds {a.seed.min()}-{a.seed.max()}): "
          f"mh_total identical {eqmh}; all baseline columns identical {eq2}")
    assert eqmh and eq2 and ok, "full scenario does NOT reproduce the baseline"
    return True


def check_splits(cfg):
    """Replay the RNG by hand for 2 sites, seed 1, scenario none, and count the splits."""
    h = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    runs = pd.read_csv(os.path.join(cfg["paths"]["output_dir"], "scenarios", "none", "nuraghe_manhours_runs.csv.gz"))
    b, s, tp, sc = cfg["builders"], cfg["stone"], cfg["transport"], cfg["scenarios"]
    ok = True
    for uid in ["NID9067800", "NID0168700"]:
        tw = int(h.loc[h.UID == uid, "TWR_N"].iloc[0])
        rng = np.random.default_rng([1, int(uid[3:])])
        fac = rng.uniform(b["rand_min"], b["rand_max"])
        B = int(min(b["max"], max(b["min"], round(round(b["base"] + b["per_extra_tower"] * (tw - 1)) * fac))))
        target = s["tonnes_per_tower"] * 1000.0 * tw
        chunk = int(target / s["block_median_kg"]) + 16
        masses, tot = [], 0.0
        while tot < target:
            m = np.clip(rng.lognormal(math.log(s["block_median_kg"]), s["block_sigma"], chunk),
                        s["block_min_kg"], s["block_max_kg"])
            masses.extend(m.tolist()); tot += m.sum()
        blocks, cum = [], 0.0
        for m in masses:                     # plain loop: keep drawing until the total is reached
            blocks.append(m); cum += m
            if cum >= target:
                break
        hs = sc["household_size"]
        households = [min(hs, B - i) for i in range(0, B, hs)]
        cap_kg = max(households) * tp["pull_kg_per_person"]
        pieces = [math.ceil(m / cap_kg) for m in blocks]
        cuts = sum(k - 1 for k in pieces)
        hist = pd.Series(pieces).value_counts().sort_index().to_dict()
        r = runs[(runs.seed == 1) & (runs.UID == uid)].iloc[0]
        match = (cuts == r.n_splits) and (len(blocks) + cuts == r.n_blocks)
        ok &= match
        print(f"(2) {uid}: {tw} tower(s), B={B} builders -> households {households[:3]}..{households[-1]} "
              f"(largest crew {max(households)} = {cap_kg:.0f} kg); {len(blocks)} blocks drawn, "
              f"{sum(1 for m in blocks if m > cap_kg)} heavier than {cap_kg:.0f} kg; pieces per block {hist}; "
              f"hand count {cuts} splits, {len(blocks) + cuts} pieces | model n_splits {r.n_splits}, "
              f"n_blocks {r.n_blocks} -> {'MATCH' if match else 'MISMATCH'}")
    return ok


def check_ranks(cfg):
    h = pd.read_csv(os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    xy = h[["x", "y"]].to_numpy()
    c = np.median(xy, axis=0)                       # a dense block of 300 sites around the island median
    sel = h.iloc[np.argsort(np.hypot(*(xy - c).T))[:300]]
    span = np.hypot(*(sel[["x", "y"]].to_numpy() - c).T).max()
    sites = ",".join(sel.UID)
    tmp = tempfile.mkdtemp(prefix="nuraghe_scen_")
    ok = True
    try:
        for scen in ["high", "patchwork"]:
            res = {}
            for n in (1, 8):
                parts = os.path.join(tmp, f"{scen}_{n}")
                cmd = MPIRUN + ["-n", str(n), sys.executable, os.path.join(ROOT, "model.py"),
                                CFG_PATH, "--scenario", scen, "--sites", sites,
                                "--seeds", "1-8", "--out", os.path.join(tmp, f"out_{scen}_{n}"),
                                "--parts-dir", parts, "--no-shapefile", "--fresh"]
                subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
                res[n] = read_parts(glob.glob(os.path.join(parts, scen, "*"))[0])
            eq = res[1].equals(res[8])
            ok &= eq
            extra = f"; help MH {res[1].mh_help.sum():,.0f}" if scen == "high" else \
                f"; cooperating sites {int((res[1].n_coop > 0).sum())} of {len(res[1])} site-runs"
            print(f"(3) {scen}: 300 clustered sites (within {span / 1000:.1f} km of the island median), seeds 1-8, "
                  f"-n 1 vs -n 8 identical: {eq}{extra}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def check_monotone(cfg):
    comp = pd.read_csv(os.path.join(cfg["paths"]["output_dir"], "scenarios", "scenario_comparison.csv"))
    c = comp.set_index("scenario")
    order = ["none", "low", "mixed", "mostly", "full"]
    v = c.loc[order, "island_mh_mean"]
    print("(4) island mean man-hours by p_coop: " +
          ", ".join(f"{o} (p={c.loc[o, 'p_coop']:.2f}) {x:,.0f}" for o, x in v.items()))
    print(f"    monotone decreasing in p_coop: {bool(np.all(np.diff(v.to_numpy()) < 0))}; "
          f"monotone over p >= 0.25: {bool(np.all(np.diff(v.to_numpy()[1:]) < 0))}")


def main():
    global CFG_PATH
    if len(sys.argv) > 1:
        CFG_PATH = os.path.abspath(sys.argv[1])
    cfg = load_config(CFG_PATH)
    print("Verification of the cooperation scenarios")
    check_full(cfg)
    a = check_splits(cfg)
    b = check_ranks(cfg)
    check_monotone(cfg)
    print("SCENARIO VERIFICATION", "PASSED" if a and b else "FAILED")
    sys.exit(0 if a and b else 1)


if __name__ == "__main__":
    main()
