#!/usr/bin/env python3
"""Sobol run 2 analysis (10 Nov 2026): first-order S1 and total-order ST with 95% bootstrap confidence intervals
(SALib 1.6.0 sobol.analyze, calc_second_order=False, 1,000 resamples, conf 0.95, seed 1) per output, on the 3-seed
mean of each evaluation; convergence check: the same indices on the first 256 base rows (a valid N=256 Saltelli
sample: SALib rows are grouped by base row and the scrambled Sobol sequence is balanced at every power of two) vs all
512. Writes indices_sobol2.csv, indices_sobol2_N256.csv, per_eval_means.csv and SOBOL2_RESULTS.md.

Refuses to run until all 14,336 evaluations have a result (no partial results), unless --partial (then it writes
only *_PARTIAL files, never SOBOL2_RESULTS.md). Base rows with an unfinished / error evaluation are dropped whole
(lowers N; reported), as Sobol run 1 did.

  python analyse.py [--partial]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUTS = ["island_years", "island_mh", "mh_transport_share"]
OUT_LABEL = {"island_years": "island years", "island_mh": "island man-hours", "mh_transport_share": "transport share"}


def load():
    P = json.load(open(os.path.join(HERE, "problem.json")))
    D = pd.read_csv(os.path.join(HERE, "design.csv"), usecols=["eval_id", "base_row", "block"])
    fs = sorted(glob.glob(os.path.join(HERE, "evals", "*", "eval_*.csv")))
    R = pd.concat([pd.read_csv(f, float_precision="round_trip") for f in fs], ignore_index=True) if fs else \
        pd.DataFrame(columns=["eval_id", "seed", "status"] + OUTPUTS)
    oks = {int(os.path.basename(f)[5:10]) for f in glob.glob(os.path.join(HERE, "evals", "*", "eval_*.ok"))}
    return P, D, R, oks


def indices(P, Y, base_rows, N_use):
    from SALib.analyze import sobol
    k = P["problem"]["num_vars"]
    rows = []
    for c in OUTPUTS:
        y = Y[c].to_numpy(float)[: N_use * (k + 2)]
        Si = sobol.analyze(P["problem"], y, calc_second_order=False, num_resamples=1000, conf_level=0.95, seed=1)
        for i, nm in enumerate(P["problem"]["names"]):
            rows.append({"output": c, "factor": nm, "S1": Si["S1"][i], "S1_conf": Si["S1_conf"][i],
                         "ST": Si["ST"][i], "ST_conf": Si["ST_conf"][i]})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partial", action="store_true")
    a = ap.parse_args()
    P, D, R, oks = load()
    k, N = P["problem"]["num_vars"], P["N"]
    tot = len(D)
    have = set(R.eval_id.astype(int)) if len(R) else set()
    missing = sorted(set(D.eval_id) - have)
    print(f"analyse: {len(have)} of {tot} evaluations have results ({len(oks)} .ok); {len(missing)} missing")
    if missing and not a.partial:
        sys.exit(f"analyse: {len(missing)} evaluations missing: no results until the run has finished "
                 f"(use --partial for a look at the complete base rows only)")
    st = R.groupby("eval_id").status.agg(lambda s: "ok" if (s == "ok").all() else
                                         ("error" if (s == "error").any() else "unfinished"))
    M = R[R.status.eq("ok")].groupby("eval_id")[OUTPUTS].mean()
    nseed = R[R.status.eq("ok")].groupby("eval_id").seed.nunique()
    E = D.set_index("eval_id").join(st.rename("status")).join(M).join(nseed.rename("n_seeds"))
    E.to_csv(os.path.join(HERE, "per_eval_means.csv" if not a.partial else "per_eval_means_PARTIAL.csv"),
             float_format="%.17g")
    bad = E.status.ne("ok") | E[OUTPUTS].isna().any(axis=1) | E.n_seeds.ne(3)
    bad_rows = sorted(set(E.base_row[bad]))
    unf, err = int(E.status.eq("unfinished").sum()), int(E.status.eq("error").sum())
    # keep complete base rows, in order; N_eff must keep the Saltelli block structure
    K = E[~E.base_row.isin(bad_rows)].sort_index()
    n_eff = len(K) // (k + 2)
    assert len(K) == n_eff * (k + 2)
    assert (K.groupby("base_row").size() == k + 2).all()
    print(f"analyse: N = {N}, base rows used {n_eff} (dropped {len(bad_rows)}: {unf} unfinished, {err} error "
          f"evaluations, plus missing)")
    if n_eff < 2:
        sys.exit("analyse: too few complete base rows")
    I = indices(P, K, None, n_eff)
    # convergence: first 256 base rows of the design (only if all of them are complete)
    first = [j for j in range(N // 2)]
    conv = None
    if not set(first) & set(bad_rows) and not missing:
        K256 = K[K.base_row < N // 2]
        I256 = indices(P, K256, None, N // 2)
        conv = I.merge(I256, on=["output", "factor"], suffixes=("", "_256"))
    suf = "" if not a.partial else "_PARTIAL"
    I.to_csv(os.path.join(HERE, f"indices_sobol2{suf}.csv"), index=False)
    if conv is not None:
        conv[["output", "factor", "S1_256", "S1_conf_256", "ST_256", "ST_conf_256"]].to_csv(
            os.path.join(HERE, f"indices_sobol2_N256{suf}.csv"), index=False)
    print(I.pivot(index="factor", columns="output", values="ST").round(4).to_string())
    if a.partial:
        print("partial: SOBOL2_RESULTS.md not written")
        return
    write_md(P, E, I, conv, n_eff, bad_rows, unf, err)


def write_md(P, E, I, conv, n_eff, bad_rows, unf, err):
    F = pd.read_csv(os.path.join(HERE, "factors.csv"), keep_default_na=False).set_index("name")
    k, N = P["problem"]["num_vars"], P["N"]
    walls = []
    for f in glob.glob(os.path.join(HERE, "evals", "*", "eval_*.ok")):
        try:
            walls.append(json.load(open(f))["wall_s"])
        except Exception:
            pass
    L = []
    L.append("# Sobol run 2 on the headline MOST_REALISTIC_AUDITED_LIT_P10\n")
    L.append(f"Code `code_variant` (= code/, CODE_VERSION {P['code_version']}, plus "
             f"the flag `sobol.lift_learning`; default off = code/ exactly). Config "
             f"`configs/config_full_audited.yaml` read-only, factors applied in memory.\n")
    L.append("## Design\n")
    L.append(f"- Saltelli (SALib 1.6.0 sobol.sample, calc_second_order=False, scramble, seed {P['sample_seed']}): "
             f"N = {N}, k = {k}, N (k + 2) = {N * (k + 2):,} evaluations x seeds {P['seeds_per_eval']} "
             f"(common random numbers; output = 3-seed mean).")
    L.append(f"- Fixed at headline: {', '.join(P['fixed_at_headline'])}.")
    L.append(f"- Level mapping of u: {json.dumps(P['level_mapping'])}.")
    L.append(f"- Completed: {int(E.status.eq('ok').sum()):,} ok, {unf} unfinished, {err} error evaluations; base rows used "
             f"N_eff = {n_eff} (dropped {len(bad_rows)}{': ' + str(bad_rows[:20]) if bad_rows else ''}).")
    if walls:
        L.append(f"- Wall per evaluation (process): median {np.median(walls):.1f} s, max {np.max(walls):.1f} s, "
                 f"sum {np.sum(walls) / 3600:.1f} h.")
    L.append("- Indices: SALib sobol.analyze, 1,000 bootstrap resamples, 95% CI (+/- half-width shown). "
             "Output means over all used evaluations: " + ", ".join(
                 f"{OUT_LABEL[c]} {E[c].mean():.6g}" for c in OUTPUTS) + ".\n")
    for c in OUTPUTS:
        T = I[I.output.eq(c)].sort_values("ST", ascending=False)
        L.append(f"## {OUT_LABEL[c]} (`{c}`)\n")
        L.append(f"Sum S1 = {T.S1.sum():.3f}; sum ST = {T.ST.sum():.3f}.\n")
        L.append("| rank | factor | row | range / levels | ST (95% CI) | S1 (95% CI) | ST-S1 |"
                 + (" ST at N=256 |" if conv is not None else ""))
        L.append("|---|---|---|---|---|---|---|" + ("---|" if conv is not None else ""))
        for r_, (_, r) in enumerate(T.iterrows(), 1):
            f = F.loc[r.factor]
            rng = (" vs ".join(str(x) for x in json.loads(f["levels"])) if f["kind"] == "binary"
                   else f"{float(f['lo']):g}-{float(f['hi']):g}")
            line = (f"| {r_} | `{r.factor}` | {f['row']} | {rng} | {r.ST:.4f} (+/-{r.ST_conf:.4f}) | "
                    f"{r.S1:.4f} (+/-{r.S1_conf:.4f}) | {r.ST - r.S1:.4f} |")
            if conv is not None:
                cr = conv[(conv.output == c) & (conv.factor == r.factor)].iloc[0]
                line += f" {cr.ST_256:.4f} |"
            L.append(line)
        L.append("")
    if conv is not None:
        L.append("## Convergence (N = 256 vs N = 512)\n")
        L.append("| output | max abs(ST512 - ST256) | factor | max abs(S1512 - S1256) | Spearman rank corr. of ST | "
                 "same set with ST >= 0.01 | max ST CI half-width at 512 |")
        L.append("|---|---|---|---|---|---|---|")
        for c in OUTPUTS:
            C = conv[conv.output.eq(c)]
            dST = (C.ST - C.ST_256).abs()
            dS1 = (C.S1 - C.S1_256).abs()
            rho = C[["ST", "ST_256"]].rank().corr().iloc[0, 1]
            same = set(C.factor[C.ST >= 0.01]) == set(C.factor[C.ST_256 >= 0.01])
            L.append(f"| {OUT_LABEL[c]} | {dST.max():.4f} | `{C.factor[dST.idxmax()]}` | {dS1.max():.4f} | {rho:.3f} | "
                     f"{same} | {C.ST_conf.max():.4f} |")
        L.append("\nConverged where the 256-to-512 change is within the 512 confidence half-width and the ranking "
                 "is stable.\n")
    else:
        L.append("## Convergence\n\nNot computed: a base row among the first 256 was dropped (N = 256 would not be "
                 "the same design prefix).\n")
    L.append("Files: `indices_sobol2.csv` (N = 512), `indices_sobol2_N256.csv`, `per_eval_means.csv`, "
             "`design.csv`, `factors.csv`, `problem.json`, per-seed results `evals/NN/eval_NNNNN.csv`.\n")
    open(os.path.join(HERE, "SOBOL2_RESULTS.md"), "w").write("\n".join(L))
    print("-> SOBOL2_RESULTS.md")


if __name__ == "__main__":
    main()
