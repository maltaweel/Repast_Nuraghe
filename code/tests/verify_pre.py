"""Pre-existing networks: P_none (empty tie sets) == A0_alone per site, every seed, every column (exact).

  python tests/verify_pre.py config.yaml
"""
import glob
import gzip
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "config.yaml"))
runs = os.path.join(cfg["paths"]["cache_dir"], "runs")             # B5: the config's cache, not ROOT/cache
newest = lambda pat: max(glob.glob(pat), key=os.path.getmtime)
a = newest(os.path.join(runs, "alliance_P_none", "*")); b = newest(os.path.join(runs, "alliance_A0_alone", "*"))
files = sorted(glob.glob(os.path.join(a, "seed_*.sites.csv.gz")))
assert files, f"no P_none part files in {a}"
same = sum(gzip.open(f).read() == gzip.open(os.path.join(b, os.path.basename(f))).read() for f in files)
print(f"P_none vs A0_alone: {same} of {len(files)} per-seed site files byte-identical (decompressed) -> "
      f"{'EXACT' if same == len(files) else 'DIFFERENT'}")
sys.exit(0 if same == len(files) else 1)
