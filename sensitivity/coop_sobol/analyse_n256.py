#!/usr/bin/env python3
"""Cooperation-model Sobol on code/: Sobol indices from a PREFIX of the design (base rows 0..N-1), per scenario.
Written 11 Nov 2026 for the halves-first order (the project's driver script, git history): when every evaluation with base_row < 256 of a
scenario has a result, that scenario has a complete Saltelli N = 256 design.

Why a prefix is a valid design (verified 11 Nov on design.csv, SALib 1.6.0):
  - design.csv = sobol.sample(N=512, calc_second_order=False, scramble=True, seed=20261110) bit for bit, and
    sobol.sample(N=256 / N=128, same seed) == the first 256 x 13 / 128 x 13 rows of it bit for bit;
  - every base row j is self-contained (rows 13 j .. 13 j + 12 = A, AB_1..AB_11, B; AB_i = A with column i from B);
  - the A and B points of the first 256 base rows put exactly one point in each 1/256 stratum of every dimension.
SALib's estimator only needs Y in that per-base-row order, so Y of rows 0 .. 13 N - 1 sorted by eval_id is exactly
what sobol.analyze expects for N base rows. N should be a power of 2 (128, 256) to keep the Sobol balance.

Indices: SALib 1.6.0 sobol.analyze, calc_second_order=False, 1,000 bootstrap resamples, conf 0.95, seed 1 (as
analyse.py). Base rows with an unfinished / error evaluation are dropped whole (reported; lowers N as analyse.py).
A scenario with a missing evaluation among base rows < N is skipped (reported), unless --complete-only, which then
uses the largest power-of-2 prefix that is complete (for a look while running).

  python analyse_n256.py [--n 256] [--scenarios none mixed full] [--complete-only] [--out FILE]
  default output: indices_coopsobol_prefixN<N>.csv (scenario, output, N_used, factor, S1, S1_conf, ST, ST_conf)
Reads only design.csv, problem.json and evals/<scenario>/*/eval_*.csv; light (seconds, < 1 GB).
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

from analyse import MAIN, EXTRA, indices   # same output lists and the same SALib call as analyse.py

HERE = os.path.dirname(os.path.abspath(__file__))


def load_scen(scen):
    fs = sorted(glob.glob(os.path.join(HERE, "evals", scen, "*", "eval_*.csv")))
    if not fs:
        return None
    return pd.concat([pd.read_csv(f, float_precision="round_trip") for f in fs], ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--scenarios", nargs="+", default=None)
    ap.add_argument("--complete-only", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    P = json.load(open(os.path.join(HERE, "problem.json")))
    k, NB = P["problem"]["num_vars"], P["N"]
    assert 2 <= a.n <= NB, a.n
    if a.n & (a.n - 1):
        print(f"warning: N = {a.n} is not a power of 2 (Sobol balance not guaranteed)")
    D = pd.read_csv(os.path.join(HERE, "design.csv"), usecols=["eval_id", "base_row", "block", "seed"])
    assert (D.base_row == D.eval_id // (k + 2)).all()
    out_rows = []
    for scen in a.scenarios or P["scenarios"]:
        R = load_scen(scen)
        if R is None:
            print(f"{scen}: no results; skipped")
            continue
        E = D.set_index("eval_id").join(R.set_index("eval_id").drop(columns=["base_row", "block", "seed"]),
                                        how="left")
        n = a.n
        have = E.status.notna()
        miss_rows = sorted(set(E.base_row[~have & (E.base_row < n)]))
        if miss_rows:
            if not a.complete_only:
                print(f"{scen}: {len(miss_rows)} base rows < {n} incomplete (first {miss_rows[0]}); skipped "
                      f"(--complete-only to use the largest complete power-of-2 prefix)")
                continue
            first = miss_rows[0]
            n = 1 << (first.bit_length() - 1) if first >= 2 else 0
            if n < 2:
                print(f"{scen}: no complete prefix of >= 2 base rows; skipped")
                continue
            print(f"{scen}: base rows < {first} complete -> using prefix N = {n}")
        E = E[E.base_row < n].sort_index()                       # eval_id order = SALib order A, AB_1..AB_k, B
        bad = E.status.ne("ok") | E[MAIN].isna().any(axis=1)
        bad_rows = sorted(set(E.base_row[bad]))
        Kp = E[~E.base_row.isin(bad_rows)]
        n_eff = len(Kp) // (k + 2)
        assert len(Kp) == n_eff * (k + 2) and (Kp.groupby("base_row").size() == k + 2).all()
        assert (Kp.groupby("base_row").block.apply(list).map(lambda b: b[0] == "A" and b[-1] == "B")).all()
        print(f"{scen}: prefix N = {n}, {len(E)} evaluations; dropped {len(bad_rows)} base rows "
              f"(unfinished {int(E.status.eq('unfinished').sum())}, error {int(E.status.eq('error').sum())}); "
              f"N_used {n_eff}")
        outs = [c for c in MAIN + EXTRA if c in Kp]
        I = indices(P, Kp, outs)
        I.insert(0, "N_used", n_eff)
        I.insert(0, "scenario", scen)
        out_rows.append(I)
        T = I[I.output.isin(["island_total_mh", "island_days_max"])]
        for o, G in T.groupby("output", sort=False):
            print(f"\n{scen} {o} (N {n_eff}):")
            print(G[["factor", "S1", "S1_conf", "ST", "ST_conf"]].round(4).to_string(index=False))
    if not out_rows:
        sys.exit("analyse_n256: nothing analysed")
    I = pd.concat(out_rows, ignore_index=True)
    out = a.out or os.path.join(HERE, f"indices_coopsobol_prefixN{a.n}.csv")
    I.to_csv(out, index=False)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
