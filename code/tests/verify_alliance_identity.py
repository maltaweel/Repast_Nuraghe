"""Bit-identity of the alliance rerun with per-stage pair columns against the saved reference (cache/alliance_ref/).

  python tests/verify_alliance_identity.py config.yaml

For each of the 7 scenarios x 100 seeds: the sites, strategy, spec, handoffs and tracks part files must be
byte-identical after decompression; the pair files must be identical in every original column (the new per-stage
columns are appended); the merged outputs (runs csv.gz, summary, stats.json, strategy_by_season, specialisation)
must be byte-identical. a Nurnet collaborator's ask/refusal counters add rows for pairs known only from asks: they are appended after
the original rows (ask_only = 1) with no help and no alliance; the original rows must be identical in order and value.
must be byte-identical. The new stage columns must sum to the old help_ab / help_ba.
"""
import filecmp
import glob
import gzip
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from nbcommon import load_config  # noqa: E402

cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "config.yaml"))
CACHE, OUTPUT = cfg["paths"]["cache_dir"], cfg["paths"]["output_dir"]           # B5: honour the config
REF = os.environ.get("ALLIANCE_REF", os.path.join(CACHE, "alliance_ref"))
if not os.path.isdir(REF):     # optional saved reference: reported as SKIPPED (not PASSED)
    print(f"ALLIANCE BIT-IDENTITY SKIPPED: no reference at {REF} (set ALLIANCE_REF)")
    sys.exit(0)
NAMES = ["A0_alone", "A1_ask", "A2_trust", "A3_trust_learning", "A4_trust_track", "A5_full", "A5_full_freerider"]
STAGES = ["quarry", "dress", "transport", "build", "track"]
allok = True
for n in NAMES:
    new = max(glob.glob(os.path.join(CACHE, "runs", f"alliance_{n}", "*")), key=os.path.getmtime)
    ref = os.path.join(REF, f"parts_{n}")
    seeds = sorted({os.path.basename(f)[5:9] for f in glob.glob(os.path.join(ref, "seed_*.sites.csv.gz"))})
    bad, nfiles, pair_bad, stage_bad, n_extra = [], 0, 0, 0, 0
    for s in seeds:
        for k in ("sites", "strategy", "spec", "handoffs", "tracks"):
            a = gzip.open(os.path.join(new, f"seed_{s}.{k}.csv.gz")).read()
            b = gzip.open(os.path.join(ref, f"seed_{s}.{k}.csv.gz")).read()
            nfiles += 1
            if a != b:
                bad.append(f"{s}.{k}")
        pall = pd.read_csv(os.path.join(new, f"seed_{s}.pairs.csv.gz"))
        pr = pd.read_csv(os.path.join(ref, f"seed_{s}.pairs.csv.gz"))
        if len(pall) and "ask_only" in pall.columns:          # a Nurnet collaborator's counters: ask-only rows are appended after
            extra = pall[pall.ask_only == 1]
            n_extra += len(extra)
            if len(extra) and (extra[["help_ab", "help_ba"]].to_numpy().max() > 0 or extra.allied.max() > 0):
                stage_bad += 1
            for d in ("ab", "ba"):
                if len(pall) and not (pall[[f"asks_{d}_{x}" for x in ("quarry", "dress", "transport", "build")]]
                                      .sum(axis=1) == pall[f"asks_{d}"]).all():
                    stage_bad += 1
            pn = pall[pall.ask_only == 0].reset_index(drop=True)
        else:
            pn = pall
        nfiles += 1
        if len(pr) and not pn[list(pr.columns)].equals(pr) or (len(pn) != len(pr)):
            pair_bad += 1
        for d in ("ab", "ba") if len(pn) else ():
            ssum = pn[[f"help_{d}_{x}" for x in STAGES]].sum(axis=1).to_numpy()
            if not np.allclose(ssum, pn[f"help_{d}"].to_numpy(), rtol=1e-12, atol=1e-9):
                stage_bad += 1
    outs = ["nuraghe_manhours_runs.csv.gz", "nuraghe_manhours_summary.csv", "stats.json", "strategy_by_season.csv",
            "specialisation.csv"]
    obad = [o for o in outs if not filecmp.cmp(os.path.join(REF, f"out_{n}", o),
                                               os.path.join(OUTPUT, "scenarios_alliance", n, o), shallow=False)]
    ok = not bad and pair_bad == 0 and stage_bad == 0 and not obad
    allok &= ok
    print(f"{n}: {len(seeds)} seeds, {nfiles} part files compared: differing {len(bad)} "
          f"{bad[:3] if bad else ''}; pair files with a differing original row/column {pair_bad}; ask-only rows appended "
          f"{n_extra:,}; stage/ask sums or ask-only rows inconsistent "
          f"{stage_bad}; merged outputs differing {obad if obad else 'none'} -> {'IDENTICAL' if ok else 'DIFFERENT'}")
a = filecmp.cmp(os.path.join(REF, "alliance_comparison.csv"),
                os.path.join(OUTPUT, "scenarios_alliance", "alliance_comparison.csv"), shallow=False)
print(f"alliance_comparison.csv byte-identical: {a}")
print("ALLIANCE BIT-IDENTITY", "PASSED" if allok and a else "FAILED")
sys.exit(0 if allok and a else 1)
