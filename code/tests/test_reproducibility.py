"""Verification (d): seed reproducibility and rank-count independence.

  MPIRUN="mpirun" python tests/test_reproducibility.py config.yaml [--full]

1. 3 sites, seeds 1-3, with -n 1 and with -n 4: full-precision results must be identical.
2. The -n 4 run repeated from scratch (--fresh): identical again.
With --full: all sites, seeds 1-5, -n 8 vs -n 3 (identical), and compared with output/ if present.
Scratch files go to a temporary folder that is deleted afterwards.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MPIRUN = shlex.split(os.environ.get("MPIRUN", "mpirun"))
PY = sys.executable


def run(n, args, tmp, tag):
    out, parts = os.path.join(tmp, "out_" + tag), os.path.join(tmp, "parts_" + tag)
    cmd = MPIRUN + ["-n", str(n), PY, os.path.join(ROOT, "model.py")] + args + \
        ["--out", out, "--parts-dir", parts, "--no-shapefile", "--fresh"]
    subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
    # full-precision rows from the part files (the .csv.gz is rounded to 4 decimals)
    import glob
    d = glob.glob(os.path.join(parts, "baseline", "*"))[0]     # parts live in <parts-dir>/baseline/<signature>/
    frames = [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(d, "*.csv")))]
    df = pd.concat([f for f in frames if len(f)], ignore_index=True)   # ranks without sites write empty parts
    return df.sort_values(["seed", "gid"]).reset_index(drop=True), out


def same(a, b):
    return a.shape == b.shape and a.equals(b)


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(ROOT, "config.yaml")
    cfg = os.path.abspath(cfg)
    full = "--full" in sys.argv
    tmp = tempfile.mkdtemp(prefix="nuraghe_repro_")
    try:
        sites = "NID9067800,NID0168700,NID1697100"
        a1, _ = run(1, [cfg, "--sites", sites, "--seeds", "1-3"], tmp, "n1")
        a4, _ = run(4, [cfg, "--sites", sites, "--seeds", "1-3"], tmp, "n4")
        b4, _ = run(4, [cfg, "--sites", sites, "--seeds", "1-3"], tmp, "n4b")
        print(f"Verification (d): 3 sites x seeds 1-3 ({len(a1)} rows)")
        print("  -n 1 vs -n 4 identical (full precision):", same(a1, a4))
        print("  -n 4 rerun identical:", same(a4, b4))
        print("  seeds differ from each other:", a1.groupby("seed").mh_total.sum().nunique() == 3)
        print(a1[["seed", "gid", "mh_total", "mh_transport", "days", "builders", "n_blocks"]].to_string(index=False))
        ok = same(a1, a4) and same(a4, b4)
        if full:
            f8, o8 = run(8, [cfg, "--seeds", "1-5"], tmp, "f8")
            f3, _ = run(3, [cfg, "--seeds", "1-5"], tmp, "f3")
            print(f"  ALL sites x seeds 1-5 ({len(f8)} rows): -n 8 vs -n 3 identical:", same(f8, f3))
            ok &= same(f8, f3)
            sys.path.insert(0, ROOT)
            from nbcommon import load_config
            main_runs = os.path.join(load_config(cfg)["paths"]["output_dir"], "nuraghe_manhours_runs.csv.gz")   # B5
            if os.path.exists(main_runs):
                m = pd.read_csv(main_runs)
                m = m[m.seed <= 5].reset_index(drop=True)
                n = pd.read_csv(os.path.join(o8, "nuraghe_manhours_runs.csv.gz"))[list(m.columns)]
                eq = m.equals(n)
                print("  seeds 1-5 rerun vs output/nuraghe_manhours_runs.csv.gz identical:", eq)
                ok &= eq
        print("REPRODUCIBILITY", "PASSED" if ok else "FAILED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
