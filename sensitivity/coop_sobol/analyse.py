#!/usr/bin/env python3
"""Cooperation-model Sobol on code/: analysis. Per scenario (none, mixed, full) and per output: first-order S1 and
total-order ST with 95% bootstrap confidence intervals (SALib 1.6.0 sobol.analyze, calc_second_order=False,
1,000 resamples, conf 0.95, seed 1), on the single-seed value of each evaluation. Convergence: the same indices on the
first 256 base rows (a valid N = 256 Saltelli prefix) vs all 512. Comparison with the 28 Oct GPU indices
(output/sensitivity/hybrid/stage2/indices2_<scenario>.csv, N 4,096; different code and two changed ranges, see
README) for the outputs both runs have.

Writes indices_coopsobol.csv (scenario, output, factor, S1, S1_conf, ST, ST_conf), indices_coopsobol_N256.csv,
per_eval.csv and COOPSOBOL_RESULTS.md. Refuses to run until all 19,968 evaluations have a result, unless --partial
(then only *_PARTIAL files, per scenario only where every base row is complete or with the complete base rows only).
Base rows with an unfinished / error evaluation are dropped whole in that scenario (lowers N; reported).

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
OLD = "@PROJECT@/output/sensitivity/hybrid/stage2/indices2_{}.csv"
MAIN = ["island_total_mh", "island_transport_mh", "island_days_max"] + [f"median_site_total_mh_TWR{t}" for t in range(1, 8)]
EXTRA = ["island_days_p95"] + [f"median_site_days_TWR{t}" for t in range(1, 8)]


def load():
    P = json.load(open(os.path.join(HERE, "problem.json")))
    D = pd.read_csv(os.path.join(HERE, "design.csv"), usecols=["eval_id", "base_row", "block", "seed"])
    fs = sorted(glob.glob(os.path.join(HERE, "evals", "*", "*", "eval_*.csv")))
    R = pd.concat([pd.read_csv(f, float_precision="round_trip") for f in fs], ignore_index=True) if fs else None
    return P, D, R


def indices(P, Y, outs):
    from SALib.analyze import sobol
    rows = []
    for c in outs:
        y = Y[c].to_numpy(float)
        if not np.isfinite(y).all() or np.var(y) == 0:
            continue
        Si = sobol.analyze(P["problem"], y, calc_second_order=False, num_resamples=1000, conf_level=0.95, seed=1)
        for i, nm in enumerate(P["problem"]["names"]):
            rows.append({"output": c, "factor": nm, "S1": Si["S1"][i], "S1_conf": Si["S1_conf"][i],
                         "ST": Si["ST"][i], "ST_conf": Si["ST_conf"][i]})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partial", action="store_true")
    a = ap.parse_args()
    P, D, R = load()
    k, N = P["problem"]["num_vars"], P["N"]
    if R is None:
        sys.exit("analyse: no results yet")
    suf = "_PARTIAL" if a.partial else ""
    all_I, all_C, notes, E_all = [], [], {}, []
    for scen in P["scenarios"]:
        Rs = R[R.scenario.eq(scen)].set_index("eval_id")
        missing = sorted(set(D.eval_id) - set(Rs.index))
        print(f"{scen}: {len(Rs)} of {len(D)} evaluations have results; {len(missing)} missing")
        if missing and not a.partial:
            sys.exit(f"analyse: {scen}: {len(missing)} evaluations missing (use --partial for a look)")
        E = D.set_index("eval_id").join(Rs.drop(columns=["base_row", "block", "seed"]), how="left")
        E["scenario"] = scen
        E_all.append(E.reset_index())
        outs = [c for c in MAIN + EXTRA if c in E]
        bad = E.status.ne("ok") | E[MAIN].isna().any(axis=1)
        bad_rows = sorted(set(E.base_row[bad]))
        Kp = E[~E.base_row.isin(bad_rows)].sort_index()
        n_eff = len(Kp) // (k + 2)
        assert len(Kp) == n_eff * (k + 2) and (Kp.groupby("base_row").size() == k + 2).all()
        notes[scen] = dict(n_eff=n_eff, dropped=len(bad_rows), unfinished=int(E.status.eq("unfinished").sum()),
                           error=int(E.status.eq("error").sum()), missing=len(missing),
                           wall_med=float(E.wall_s.median()) if E.wall_s.notna().any() else float("nan"),
                           wall_sum_h=float(E.wall_s.sum()) / 3600)
        print(f"{scen}: N_eff {n_eff} (dropped {len(bad_rows)} base rows)")
        if n_eff < 2:
            continue
        I = indices(P, Kp, outs)
        I.insert(0, "scenario", scen)
        all_I.append(I)
        if not bad_rows and not missing:
            I2 = indices(P, Kp[Kp.base_row < N // 2], outs)
            I2.insert(0, "scenario", scen)
            all_C.append(I.merge(I2, on=["scenario", "output", "factor"], suffixes=("", "_256")))
    if not all_I:
        sys.exit("analyse: too few complete base rows")
    I = pd.concat(all_I, ignore_index=True)
    C = pd.concat(all_C, ignore_index=True) if all_C else None
    I.to_csv(os.path.join(HERE, f"indices_coopsobol{suf}.csv"), index=False)
    pd.concat(E_all, ignore_index=True).to_csv(os.path.join(HERE, f"per_eval{suf}.csv"), index=False,
                                               float_format="%.17g")
    if C is not None:
        C[["scenario", "output", "factor", "S1_256", "S1_conf_256", "ST_256", "ST_conf_256"]].to_csv(
            os.path.join(HERE, f"indices_coopsobol_N256{suf}.csv"), index=False)
    print(I[I.output.eq("island_total_mh")].pivot(index="factor", columns="scenario", values="ST").round(4).to_string())
    if a.partial:
        print("partial: COOPSOBOL_RESULTS.md not written")
        return
    write_md(P, I, C, notes)


def write_md(P, I, C, notes):
    F = pd.read_csv(os.path.join(HERE, "factors.csv"), keep_default_na=False).set_index("name")
    k, N = P["problem"]["num_vars"], P["N"]
    L = ["# Cooperation-model Sobol on code/ (none, mixed, full)\n",
         f"Code `code/` (CODE_VERSION {P['code_version']}), "
         f"engine B (model.py), config `configs/config_full_audited.yaml` read-only, factors applied in memory.\n",
         "## Design\n",
         f"- Saltelli (SALib 1.6.0 sobol.sample, calc_second_order=False, scramble, seed {P['sample_seed']}): N = {N}, "
         f"k = {k}, N (k + 2) = {P['rows']:,} rows per scenario x {len(P['scenarios'])} scenarios = "
         f"{P['n_evals']:,} evaluations; {P['seed_rule']}.",
         f"- Level mapping: {json.dumps(P['level_mapping'])}.",
         "- Indices: SALib sobol.analyze, 1,000 bootstrap resamples, 95% CI (+/- half-width).\n",
         "| scenario | N_eff | base rows dropped | unfinished | error | median wall (s) | sum wall (h) |",
         "|---|---|---|---|---|---|---|"]
    for s, n in notes.items():
        L.append(f"| {s} | {n['n_eff']} | {n['dropped']} | {n['unfinished']} | {n['error']} | {n['wall_med']:.1f} | "
                 f"{n['wall_sum_h']:.1f} |")
    L.append("\n## Factors\n")
    L.append("| factor | range (now) | 28 Oct range | changed |")
    L.append("|---|---|---|---|")
    for n, f in F.iterrows():
        L.append(f"| `{n}` | {float(f['lo']):g}-{float(f['hi']):g} ({f['kind']}) | {f['old']} | {f['changed']} |")
    for out in MAIN:
        T = I[I.output.eq(out)]
        if not len(T):
            continue
        L.append(f"\n## {out}\n")
        L.append("| factor | " + " | ".join(f"{s} ST (95% CI) | {s} S1" for s in P["scenarios"]) + " | 28 Oct ST range |")
        L.append("|---|" + "---|---|" * len(P["scenarios"]) + "---|")
        old = {}
        for s in P["scenarios"]:
            try:
                O = pd.read_csv(OLD.format(s))
                old[s] = O[O.output.eq(out)].set_index("factor").ST
            except Exception:
                pass
        order = T.groupby("factor").ST.max().sort_values(ascending=False).index
        for fac in order:
            cells = []
            for s in P["scenarios"]:
                r = T[(T.scenario == s) & (T.factor == fac)]
                cells.append(f"{r.ST.iloc[0]:.3f} (+/-{r.ST_conf.iloc[0]:.3f}) | {r.S1.iloc[0]:.3f}" if len(r) else "- | -")
            ov = [old[s].get(fac) for s in old if fac in old[s].index]
            L.append(f"| `{fac}` | " + " | ".join(cells) + " | " +
                     (f"{min(ov):.2f}-{max(ov):.2f}" if ov else "-") + " |")
    if C is not None:
        L.append("\n## Convergence (N = 256 vs N = 512)\n")
        L.append("| scenario | output | max abs dST | factor | max ST CI half-width at 512 |")
        L.append("|---|---|---|---|---|")
        for (s, out), G in C[C.output.isin(MAIN)].groupby(["scenario", "output"], sort=False):
            d = (G.ST - G.ST_256).abs()
            L.append(f"| {s} | {out} | {d.max():.4f} | `{G.factor[d.idxmax()]}` | {G.ST_conf.max():.4f} |")
    L.append("\nFiles: `indices_coopsobol.csv`, `indices_coopsobol_N256.csv`, `per_eval.csv`, `design.csv`, "
             "`factors.csv`, `problem.json`, per-evaluation results `evals/<scenario>/NN/eval_RRRRR.csv`. "
             "Extra outputs (island_days_p95, median_site_days_TWR1..7) are in indices_coopsobol.csv only.\n")
    open(os.path.join(HERE, "COOPSOBOL_RESULTS.md"), "w").write("\n".join(L))
    print("-> COOPSOBOL_RESULTS.md")


if __name__ == "__main__":
    main()
