#!/usr/bin/env python3
"""Export the sensitivity results of the final model (code v17) into outputs/sensitivity/.

Reads the run folders of the project (read-only; nothing is written there) and writes small, island-level tables:
designs, one row per evaluation / run, and Sobol / Morris indices with 95% confidence intervals. Raw per-site outputs
are never exported.

  python export.py [--project DIR] [--only SET ...] [--dry-run] [--scratch DIR] [--coop-prefix 256]

  --project DIR     the project folder that holds runs/ (default: $NURAGHE_PROJECT)
  --only SET ...    a5 sobol2 coop_sobol morris feasibility (default: all)
  --dry-run         compute everything and report; write nothing. Sets whose run has not finished are analysed on
                    their complete base rows only and labelled PARTIAL (a look, never exported).
  --scratch DIR     with --dry-run: write what would be exported (and the PARTIAL tables) into DIR instead (must be
                    outside outputs/sensitivity/)
  --scrub FILE      local wording table applied to the free-text files (factors, problem): one rule per line,
                    "regex<TAB>replacement"; a line "!regex" is a pattern that must not remain in any exported text
                    (stop on a hit). Default: $NURAGHE_SENS_SCRUB. Not part of the repository.
  --coop-prefix N   cooperation Sobol: if the full N = 512 design is not complete, export the complete prefix of N base
                    rows (N = 256 runs first, the halves-first order) as the result, labelled N = 256. Off by default.

Rules: a set's results are written only when its run is complete (every evaluation present; base rows with an error
evaluation are dropped whole and reported, as in the run's own analysis). Inputs (design, factors, problem) are
written whenever they exist. Every written text is checked for absolute paths and site identifiers (stop on a hit).
MANIFEST.csv lists every exported file with size, rows, SHA-256 and its source in the run folder.

Indices: SALib 1.6.0 sobol.analyze(calc_second_order=False, num_resamples=1000, conf_level=0.95, seed=1), as the
runs' own analyse.py; *_conf is the half-width of the 95% bootstrap confidence interval, *_lo / *_hi = value -/+ conf.
Morris: mu* with a 95% bootstrap interval of the mean |EE| (1,000 resamples, numpy default_rng(0)).
Needs Python 3.10+, numpy, pandas, scipy, SALib 1.6.
"""
import argparse
import csv
import datetime
import glob
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# run folders, relative to the project folder
FA = "runs/2026-11-02-v12-census/full_audited"
A5_ROOT = FA + "/v17/outputs/scenarios_alliance"
A5_LOGS = FA + "/v17/outputs/logs"
CODE_V17 = FA + "/code_v17"
SOBOL2 = "runs/2026-11-10-sobol2-v17"
COOP = "runs/2026-11-10-coopsobol-v17"
MORRIS32 = FA + "/v17/harness/morris32"
MORRIS_PHYS = FA + "/v17/harness/morris_phys"
FEAS = FA + "/v17/harness/feas"

SALIB_KW = dict(calc_second_order=False, num_resamples=1000, conf_level=0.95, seed=1)
SOBOL2_OUT = ["island_years", "island_mh", "mh_transport_share"]
COOP_MAIN = (["island_total_mh", "island_transport_mh", "island_days_max"]
             + [f"median_site_total_mh_TWR{t}" for t in range(1, 8)])
COOP_EXTRA = ["island_days_p95"] + [f"median_site_days_TWR{t}" for t in range(1, 8)]
COOP_KEEP = ["scenario", "eval_id", "gid", "base_row", "block", "seed", "status"] + COOP_MAIN + COOP_EXTRA + \
    ["n_splits", "n_blocks"]
# never exported (process / host details, error text that may hold paths)
DROP_COLS = {"pid", "error", "wall_s", "static_s", "t_import_s", "t_setup_s", "t_run_s", "peak_rss_mb", "host",
             "cmd", "log", "cfg", "path", "part", "parts"}

# stop on any of these in an exported text: absolute paths, home folders, site identifiers (per-site data), e-mails
FORBIDDEN = re.compile(r"(?:^|[\s\"'=(,])/(?:root|home|mnt|tmp|Users|data)/|[A-Za-z]:\\\\|\bNID\d{5,}\b|"
                       r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
TIME_OF_DAY = re.compile(r"(\d{1,2} (?:Oct|Nov)) \d{1,2}:\d{2}(?:-\d{1,2}:\d{2})?")


class Exporter:
    def __init__(self, project, dry, scratch, scrub=None):
        self.P, self.dry, self.scratch = project, dry, scratch
        self.rules, self.banned = [], []
        if scrub:
            for ln in open(scrub, encoding="utf-8"):
                ln = ln.rstrip("\n")
                if not ln.strip() or ln.startswith("#"):
                    continue
                if ln.startswith("!"):
                    self.banned.append(re.compile(ln[1:]))
                else:
                    a, b = ln.split("\t", 1)
                    self.rules.append((re.compile(a), b))
        self.manifest, self.status = [], {}
        self.today = datetime.date.today().isoformat()

    def src(self, rel):
        return os.path.join(self.P, rel)

    def dest(self, rel):
        base = self.scratch if self.scratch else HERE
        return os.path.join(base, rel)

    # ---- writing --------------------------------------------------------------------------------------------------
    def put(self, rel, data, source, rows=None, partial=False):
        """rel: path under outputs/sensitivity/; data: bytes (csv text, json, or gz of csv text)."""
        text = gzip.decompress(data) if rel.endswith(".gz") else data
        m = FORBIDDEN.search(text.decode("utf-8", "replace"))
        for b in self.banned:
            m = m or b.search(text.decode("utf-8", "replace"))
        if m:
            raise SystemExit(f"export: forbidden pattern in {rel}: ...{text[max(0, m.start() - 60):m.end() + 60]!r}")
        if partial and not self.dry:
            raise SystemExit(f"export: refusing to export PARTIAL {rel} (only with --dry-run)")
        self.manifest.append({"file": rel, "bytes": len(data), "rows": rows if rows is not None else "",
                              "sha256": hashlib.sha256(data).hexdigest(), "source": source,
                              "exported": self.today})
        tag = "PARTIAL " if partial else ""
        print(f"  {'(dry) ' if self.dry and not self.scratch else ''}{tag}{rel}: {len(data):,} B"
              + (f", {rows:,} rows" if rows is not None else ""))
        if self.dry and not self.scratch:
            return
        p = self.dest(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)

    @staticmethod
    def csv_bytes(df, gz=False, float_format="%.17g"):
        s = df.to_csv(index=False, float_format=float_format, lineterminator="\n").encode("utf-8")
        if not gz:
            return s
        buf = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as g:
            g.write(s)
        return buf.getvalue()

    def put_df(self, rel, df, source, gz=False, partial=False, float_format="%.17g"):
        self.put(rel, self.csv_bytes(df, gz=gz, float_format=float_format), source, rows=len(df), partial=partial)

    def put_file(self, rel, srcrel, transform=None, gz=False):
        with open(self.src(srcrel), "rb") as f:
            data = f.read()
        if transform:
            data = transform(data)
        if self.rules and not gz:
            t = data.decode("utf-8")
            for a, b in self.rules:
                t = a.sub(b, t)
            data = t.encode("utf-8")
        rows = data.count(b"\n") - 1 if srcrel.endswith(".csv") else None
        if gz:
            buf = io.BytesIO()
            with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as g:
                g.write(data)
            data = buf.getvalue()
        self.put(rel, data, srcrel, rows=rows)

    # ---- helpers ----------------------------------------------------------------------------------------------------
    @staticmethod
    def no_times(data):
        """drop times of day after dates in free text ('10 Nov 13:47' -> '10 Nov'), as the repository's other texts."""
        return TIME_OF_DAY.sub(r"\1", data.decode("utf-8")).encode("utf-8")

    @staticmethod
    def problem_public(data, code, config):
        P = json.loads(data)
        P["code"], P["config"] = code, config
        for k, v in P.items():
            if isinstance(v, str) and v.startswith("/"):
                raise SystemExit(f"export: problem.json key {k} holds a local path")
        return (json.dumps(P, indent=1) + "\n").encode("utf-8")

    @staticmethod
    def read_csvs(pattern, usecols=None):
        """many small CSVs -> one DataFrame (streaming, csv module; floats parsed by pandas once at the end)."""
        fs = sorted(glob.glob(pattern))
        rows, header = [], None
        for f in fs:
            with open(f, newline="") as fh:
                r = csv.reader(fh)
                h = next(r, None)
                if h is None:
                    continue
                if header is None:
                    header = h
                elif h != header:
                    raise SystemExit(f"export: header differs in {f}")
                rows.extend(r)
        if header is None:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=header)
        if usecols:
            df = df[[c for c in usecols if c in df.columns]]
        for c in df.columns:
            if c not in ("status", "error", "block", "scenario"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    @staticmethod
    def sobol_indices(problem, Y, outputs, n_base, extra=None):
        from SALib.analyze import sobol
        rows = []
        for c in outputs:
            y = Y[c].to_numpy(float)
            if not np.isfinite(y).all() or np.var(y) == 0:
                continue
            Si = sobol.analyze(problem, y, **SALIB_KW)
            for i, nm in enumerate(problem["names"]):
                r = dict(extra or {})
                r.update({"output": c, "N": n_base, "factor": nm,
                          "S1": Si["S1"][i], "S1_conf": Si["S1_conf"][i],
                          "S1_lo": Si["S1"][i] - Si["S1_conf"][i], "S1_hi": Si["S1"][i] + Si["S1_conf"][i],
                          "ST": Si["ST"][i], "ST_conf": Si["ST_conf"][i],
                          "ST_lo": Si["ST"][i] - Si["ST_conf"][i], "ST_hi": Si["ST"][i] + Si["ST_conf"][i]})
                rows.append(r)
        return pd.DataFrame(rows)

    def crosscheck(self, mine, theirs_rel, keys):
        p = self.src(theirs_rel)
        if not os.path.exists(p):
            return
        T = pd.read_csv(p)
        M = mine.merge(T, on=keys, suffixes=("", "_run"))
        d = max(float((M[c] - M[c + "_run"]).abs().max()) for c in ("S1", "S1_conf", "ST", "ST_conf"))
        print(f"  cross-check with the run's own {os.path.basename(theirs_rel)}: {len(M)} rows, max abs diff {d:.3g}")
        if len(M) != len(T) or d > 1e-9:
            raise SystemExit("export: indices differ from the run's own analysis")

    # ================================================================================================================
    def a5(self):
        """A5 alliance sensitivity: 27 cells (R_m x b x track cost) on A5_full + the A0_alone reference, seeds 1-100."""
        print("[a5] alliance sensitivity grid (A5_full, 27 cells + A0_alone)")
        ok = self.src(A5_LOGS + "/q_A5_SENSITIVITY_27cells.ok")
        cells = sorted(os.path.basename(d) for d in glob.glob(self.src(A5_ROOT + "/sensitivity/SENS_*")))
        if not os.path.exists(ok) or len(cells) != 27:
            self.status["a5"] = f"pending ({len(cells)} cells, ok marker {os.path.exists(ok)})"
            print("  " + self.status["a5"])
            return
        names = ["A0_alone"] + cells
        dirs = {n: (A5_ROOT + "/A0_alone" if n == "A0_alone" else f"{A5_ROOT}/sensitivity/{n}") for n in names}
        design, stats, seeds, strat = [], [], [], []
        for n in names:
            st = json.load(open(self.src(dirs[n] + "/stats.json")))
            if st.get("seeds_run") != 100:
                raise SystemExit(f"export: {n} has {st.get('seeds_run')} seeds, expected 100")
            if n == "A0_alone":
                design.append({"scenario": n, "base": "A0_alone", "R_m": "", "b": "", "track_cost_mh_per_m": "",
                               "seeds": "1-100"})
            else:
                R, b, t = n[5:].split("_")
                design.append({"scenario": n, "base": "A5_full", "R_m": int(R[1:]), "b": float(b[1:]),
                               "track_cost_mh_per_m": float(t[1:]), "seeds": "1-100"})
            row = {"scenario": n}
            row.update({k: v for k, v in st.items() if k != "scenario" and isinstance(v, (int, float))})
            S = pd.read_csv(self.src(dirs[n] + "/island_by_seed.csv"))
            if len(S) != 100 or sorted(S.seed) != list(range(1, 101)):
                raise SystemExit(f"export: {n}/island_by_seed.csv is not seeds 1-100")
            from scipy import stats as sst
            tq = float(sst.t.ppf(0.975, len(S) - 1))
            for c in ("island_mh", "island_seasons"):
                m, sd = float(S[c].mean()), float(S[c].std(ddof=1))
                row[f"{c}_mean_ci95_lo"] = m - tq * sd / math.sqrt(len(S))
                row[f"{c}_mean_ci95_hi"] = m + tq * sd / math.sqrt(len(S))
            stats.append(row)
            S.insert(0, "scenario", n)
            seeds.append(S)
            G = pd.read_csv(self.src(dirs[n] + "/strategy_by_season.csv"))
            G.insert(0, "scenario", n)
            strat.append(G)
        a0 = stats[0]["island_mh_mean"]
        for r in stats:
            r["pct_vs_A0"] = 100.0 * (r["island_mh_mean"] / a0 - 1.0)
        D = pd.DataFrame(design)
        C = pd.DataFrame(stats)
        C = C[["scenario"] + [c for c in C.columns if c != "scenario"]]
        self.put_df("a5_alliance/design.csv", D, f"{A5_ROOT}/sensitivity/SENS_* (cell names; config alliance.sensitivity)")
        self.put_file("a5_alliance/sensitivity.csv", A5_ROOT + "/sensitivity/sensitivity.csv")
        self.put_df("a5_alliance/cells.csv", C, f"{A5_ROOT}/<cell>/stats.json + island_by_seed.csv")
        self.put_df("a5_alliance/island_by_seed.csv", pd.concat(seeds, ignore_index=True),
                    f"{A5_ROOT}/<cell>/island_by_seed.csv")
        self.put_df("a5_alliance/strategy_by_season.csv", pd.concat(strat, ignore_index=True),
                    f"{A5_ROOT}/<cell>/strategy_by_season.csv")
        self.status["a5"] = "exported (28 scenarios x 100 seeds)"

    # ================================================================================================================
    def sobol2(self, coop_prefix=None):
        print("[sobol2] Sobol run 2 on the v17 headline (26 factors, N = 512)")
        R0 = SOBOL2
        if not os.path.exists(self.src(R0 + "/problem.json")):
            self.status["sobol2"] = "run folder missing"
            return
        P = json.load(open(self.src(R0 + "/problem.json")))
        k, N = P["problem"]["num_vars"], P["N"]
        self.put_file("sobol2/design.csv.gz", R0 + "/design.csv", gz=True)
        self.put_file("sobol2/factors.csv", R0 + "/factors.csv", transform=self.no_times)
        self.put_file("sobol2/problem.json", R0 + "/problem.json", transform=lambda d: self.problem_public(
            d, "code/ (CODE_VERSION 2026-11-09-v17) + the config flag sobol.lift_learning (code variant code_v17s; "
               "flag off = code v17 exactly)", "config/v16_final/config_full_audited.yaml"))
        D = pd.read_csv(self.src(R0 + "/design.csv"), usecols=["eval_id", "base_row", "block"])
        R = self.read_csvs(self.src(R0 + "/evals/*/eval_*.csv"))
        R = R[[c for c in R.columns if c not in DROP_COLS]]
        if len(R):
            R = R[R.eval_id.isin(D.eval_id)]
        have = set(R.eval_id.astype(int)) if len(R) else set()
        missing = sorted(set(D.eval_id) - have)
        print(f"  {len(have):,} of {len(D):,} evaluations have results; {len(missing):,} missing")
        complete = not missing
        partial = not complete
        if partial and not self.dry:
            self.status["sobol2"] = f"inputs exported; results pending ({len(have):,}/{len(D):,} evaluations)"
            return
        st = R.groupby("eval_id").status.agg(lambda s: "ok" if (s == "ok").all() else
                                             ("error" if (s == "error").any() else "unfinished"))
        okR = R[R.status.eq("ok")]
        M = okR.groupby("eval_id")[SOBOL2_OUT].mean()
        ns = okR.groupby("eval_id").seed.nunique()
        E = D.set_index("eval_id").join(st.rename("status")).join(M).join(ns.rename("n_seeds")).reset_index()
        bad = E.status.ne("ok") | E[SOBOL2_OUT].isna().any(axis=1) | E.n_seeds.ne(3)
        bad_rows = sorted(set(E.base_row[bad]))
        K = E[~E.base_row.isin(bad_rows)].sort_values("eval_id")
        n_eff = len(K) // (k + 2)
        assert len(K) == n_eff * (k + 2) and (K.groupby("base_row").size() == k + 2).all()
        print(f"  base rows used N_eff = {n_eff} (dropped {len(bad_rows)})")
        sfx = "_PARTIAL" if partial else ""
        Rs = R.sort_values(["eval_id", "seed"])
        self.put_df(f"sobol2/runs{sfx}.csv.gz", Rs, R0 + "/evals/NN/eval_NNNNN.csv", gz=True, partial=partial)
        self.put_df(f"sobol2/per_eval{sfx}.csv.gz", E, R0 + "/evals (3-seed means)", gz=True, partial=partial)
        if n_eff < 2:
            self.status["sobol2"] = "too few complete base rows"
            return
        I = self.sobol_indices(P["problem"], K, SOBOL2_OUT, n_eff)
        self.put_df(f"sobol2/indices{sfx}.csv", I, "computed from per_eval (SALib sobol.analyze)", partial=partial)
        if not partial:
            self.crosscheck(I.drop(columns=["N"]), R0 + "/indices_sobol2.csv", ["output", "factor"])
            if not bad_rows:
                I2 = self.sobol_indices(P["problem"], K[K.base_row < N // 2], SOBOL2_OUT, N // 2)
                self.put_df(f"sobol2/indices_N{N // 2}.csv", I2, f"computed from per_eval, base rows 0-{N // 2 - 1}")
        self.status["sobol2"] = ("PARTIAL look only (dry run)" if partial else
                                 f"exported (N_eff {n_eff}, dropped {len(bad_rows)} base rows)")

    # ================================================================================================================
    def coop_sobol(self, coop_prefix=None):
        print("[coop_sobol] cooperation-model Sobol (11 factors x scenarios none, mixed, full; N = 512)")
        R0 = COOP
        if not os.path.exists(self.src(R0 + "/problem.json")):
            self.status["coop_sobol"] = "run folder missing"
            return
        P = json.load(open(self.src(R0 + "/problem.json")))
        k, N = P["problem"]["num_vars"], P["N"]
        self.put_file("coop_sobol/design.csv.gz", R0 + "/design.csv", gz=True)
        self.put_file("coop_sobol/factors.csv", R0 + "/factors.csv", transform=self.no_times)
        self.put_file("coop_sobol/problem.json", R0 + "/problem.json", transform=lambda d: self.problem_public(
            d, "code/ (CODE_VERSION 2026-11-09-v17)", "config/v16_final/config_full_audited.yaml"))
        D = pd.read_csv(self.src(R0 + "/design.csv"), usecols=["eval_id", "base_row", "block", "seed"])
        assert (D.base_row == D.eval_id // (k + 2)).all()
        loaded, notes = {}, {}
        for scen in P["scenarios"]:                            # load + completeness of every scenario first
            R = self.read_csvs(self.src(f"{R0}/evals/{scen}/*/eval_*.csv"))
            if len(R):
                R = R[[c for c in COOP_KEEP if c in R.columns]]
                R = R[R.eval_id.isin(D.eval_id)]
            have = set(R.eval_id.astype(int)) if len(R) else set()
            missing = sorted(set(D.eval_id) - have)
            miss_rows = sorted(set(D.base_row[D.eval_id.isin(missing)]))
            print(f"  {scen}: {len(have):,} of {len(D):,} evaluations; first incomplete base row "
                  f"{miss_rows[0] if miss_rows else '-'}")
            loaded[scen], notes[scen] = (R, missing, miss_rows), len(have)
        # one N for all scenarios: the full design, else (--coop-prefix) the complete prefix, else nothing / a look
        if all(not m for _, m, _ in loaded.values()):
            mode, n_use = "full", N
        elif coop_prefix and all(not mr or mr[0] >= coop_prefix for _, _, mr in loaded.values()):
            mode, n_use = "prefix", coop_prefix
        else:
            mode, n_use = "partial", None
        if mode == "partial" and not self.dry:
            self.status["coop_sobol"] = ("inputs exported; results pending (" + ", ".join(
                f"{s} {n:,}/{len(D):,}" for s, n in notes.items()) + ")")
            print("  " + self.status["coop_sobol"])
            return
        partial = mode == "partial"
        allE, allI, allI2 = [], [], []
        for scen, (R, missing, miss_rows) in loaded.items():
            if not len(R):
                print(f"  {scen}: no evaluations yet")
                continue
            E = D.set_index("eval_id").join(R.drop(columns=["base_row", "block", "seed"], errors="ignore")
                                            .set_index("eval_id"), how="left").reset_index()
            E["scenario"] = scen
            E_use = E[~E.base_row.isin(miss_rows)] if partial else E[E.base_row < n_use]
            bad = E_use.status.ne("ok") | E_use[COOP_MAIN].isna().any(axis=1)
            bad_rows = sorted(set(E_use.base_row[bad]))
            K = E_use[~E_use.base_row.isin(bad_rows)].sort_values("eval_id")
            n_eff = len(K) // (k + 2)
            assert len(K) == n_eff * (k + 2) and (K.groupby("base_row").size() == k + 2).all()
            allE.append(E_use)
            if n_eff >= 2:
                allI.append(self.sobol_indices(P["problem"], K, COOP_MAIN + COOP_EXTRA, n_eff,
                                               extra={"scenario": scen}))
                if mode == "full" and not bad_rows:
                    allI2.append(self.sobol_indices(P["problem"], K[K.base_row < N // 2], COOP_MAIN + COOP_EXTRA,
                                                    N // 2, extra={"scenario": scen}))
            print(f"  {scen}: N_eff {n_eff} ({'PARTIAL: complete base rows only' if partial else f'N = {n_use}'}; "
                  f"dropped {len(bad_rows)})")
        sfx = {"partial": "_PARTIAL", "full": "", "prefix": f"_N{coop_prefix}"}[mode]
        Eall = pd.concat(allE, ignore_index=True)
        Eall = Eall[[c for c in COOP_KEEP if c in Eall.columns]]
        self.put_df(f"coop_sobol/per_eval{sfx}.csv.gz", Eall, R0 + "/evals/<scenario>/NN/eval_RRRRR.csv", gz=True,
                    partial=partial)
        if allI:
            I = pd.concat(allI, ignore_index=True)
            I = I[["scenario"] + [c for c in I.columns if c != "scenario"]]
            self.put_df(f"coop_sobol/indices{sfx}.csv", I, "computed from per_eval (SALib sobol.analyze)",
                        partial=partial)
            if mode == "full":
                self.crosscheck(I.drop(columns=["N"]), R0 + "/indices_coopsobol.csv", ["scenario", "output", "factor"])
        if allI2:
            I2 = pd.concat(allI2, ignore_index=True)
            self.put_df(f"coop_sobol/indices_N{N // 2}.csv",
                        I2[["scenario"] + [c for c in I2.columns if c != "scenario"]],
                        f"computed from per_eval, base rows 0-{N // 2 - 1}")
        self.status["coop_sobol"] = {"partial": "PARTIAL look only (dry run)", "full": f"exported (N = {N})",
                                     "prefix": f"exported as the complete N = {coop_prefix} prefix"}[mode]

    # ================================================================================================================
    def morris(self):
        print("[morris] 32-factor Morris screen (morris32) and physical Morris (morris_phys) on v17")
        done_any = False
        m32 = MORRIS32
        if os.path.exists(self.src(m32 + "/MORRIS_RESULTS.md")) and os.path.exists(self.src(m32 + "/morris_indices.csv")):
            R = pd.read_csv(self.src(m32 + "/results_per_seed.csv"))
            n_ev = pd.read_csv(self.src(m32 + "/design.csv"), usecols=["eval_id"]).eval_id.nunique()
            okn = R[R.status.eq("ok")].groupby("eval_id").seed.nunique()
            if int((okn == 3).sum()) < n_ev and not self.dry:
                print(f"  morris32: {int((okn == 3).sum())}/{n_ev} evaluations complete: pending")
            else:
                self.put_file("morris/morris32_design.csv", m32 + "/design.csv")
                self.put_file("morris/morris32_factors.csv", m32 + "/factors.csv", transform=self.no_times)
                self.put_file("morris/morris32_problem.json", m32 + "/problem.json", transform=lambda d:
                              self.problem_public(d, "code/ (CODE_VERSION 2026-11-09-v17)",
                                                  "config/v16_final/config_full_audited.yaml"))
                self.put_df("morris/morris32_runs.csv", R[[c for c in R.columns if c not in DROP_COLS]],
                            m32 + "/results_per_seed.csv")
                self.put_file("morris/morris32_ee.csv", m32 + "/morris_ee.csv")
                self.put_file("morris/morris32_indices.csv", m32 + "/morris_indices.csv")
                done_any = True
        else:
            print("  morris32: no results yet")
        mp = MORRIS_PHYS
        if os.path.exists(self.src(mp + "/analyse.ok")):
            D = pd.read_csv(self.src(mp + "/design_outputs.csv"))
            self.put_df("morris/morris_phys_runs.csv", D[[c for c in D.columns if c not in DROP_COLS]],
                        mp + "/design_outputs.csv")
            I = pd.read_csv(self.src(mp + "/morris_phys.csv"))
            names = [c[2:] for c in D.columns if c.startswith("u_")]
            rng = np.random.default_rng(0)
            conf = []
            for r in I.itertuples():                            # bootstrap 95% CI of mu* (as morris32/analyse.py)
                ee = []
                for _, g in D.groupby("traj"):
                    g = g.sort_values("step")
                    U = g[[f"u_{n}" for n in names]].to_numpy()
                    y = g[r.output].to_numpy(dtype=float)
                    for s in range(1, len(g)):
                        j = int(np.flatnonzero(np.abs(U[s] - U[s - 1]) > 1e-12)[0])
                        if names[j] == r.factor:
                            ee.append((y[s] - y[s - 1]) / (U[s, j] - U[s - 1, j]))
                e = np.array(ee, float)
                e = e[np.isfinite(e)]
                conf.append(float(1.96 * np.std([np.mean(np.abs(rng.choice(e, e.size))) for _ in range(1000)], ddof=1))
                            if e.size > 1 else np.nan)
            I["mu_star_conf"] = conf
            I["mu_star_lo"], I["mu_star_hi"] = I.mu_star - I.mu_star_conf, I.mu_star + I.mu_star_conf
            self.put_df("morris/morris_phys_indices.csv", I, mp + "/morris_phys.csv + bootstrap CI")
            done_any = True
        else:
            print("  morris_phys: no results yet")
        self.status["morris"] = "exported" if done_any else "pending (no Morris run on v17 has finished)"

    # ================================================================================================================
    def feasibility(self):
        print("[feasibility] feasibility grid on the sourced range (v17)")
        f = FEAS
        if not os.path.exists(self.src(f + "/grid.ok")):
            self.status["feasibility"] = "pending (grid not finished)"
            print("  " + self.status["feasibility"])
            return
        for n in ("grid", "boundary_seeds"):
            p = self.src(f"{f}/{n}.csv")
            if os.path.exists(p):
                G = pd.read_csv(p)
                self.put_df(f"feasibility/{n}.csv", G[[c for c in G.columns if c not in DROP_COLS]], f"{f}/{n}.csv")
        self.status["feasibility"] = "exported"

    def write_manifest(self):
        if not self.manifest:
            return
        man = pd.DataFrame(self.manifest)
        old = os.path.join(self.scratch or HERE, "MANIFEST.csv")
        if os.path.exists(old):                                  # keep the rows of sets not exported this time
            O = pd.read_csv(old, keep_default_na=False)
            man = pd.concat([O[~O.file.isin(man.file)], man], ignore_index=True)
        man = man.sort_values("file")
        data = man.to_csv(index=False, lineterminator="\n").encode("utf-8")
        if self.dry and not self.scratch:
            print(f"  (dry) MANIFEST.csv: {len(man)} files")
            return
        with open(old + ".tmp", "wb") as fh:
            fh.write(data)
        os.replace(old + ".tmp", old)
        print(f"  MANIFEST.csv: {len(man)} files")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("NURAGHE_PROJECT"))
    ap.add_argument("--only", nargs="+", choices=["a5", "sobol2", "coop_sobol", "morris", "feasibility"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scratch")
    ap.add_argument("--scrub", default=os.environ.get("NURAGHE_SENS_SCRUB"))
    ap.add_argument("--coop-prefix", type=int, choices=[128, 256])
    a = ap.parse_args()
    if not a.project or not os.path.isdir(os.path.join(a.project, "runs")):
        sys.exit("export: set --project (or NURAGHE_PROJECT) to the project folder that holds runs/")
    if a.scratch:
        if not a.dry_run:
            sys.exit("export: --scratch only with --dry-run")
        s = os.path.abspath(a.scratch)
        if s == HERE or s.startswith(HERE + os.sep) or s.startswith(os.path.abspath(a.project) + os.sep + "runs"):
            sys.exit("export: --scratch must be outside outputs/sensitivity/ and runs/")
    if not a.dry_run and not a.scrub:
        sys.exit("export: --scrub FILE (or NURAGHE_SENS_SCRUB) is required to write the exported files")
    X = Exporter(os.path.abspath(a.project), a.dry_run, a.scratch, a.scrub)
    for s in a.only or ["a5", "sobol2", "coop_sobol", "morris", "feasibility"]:
        if s == "coop_sobol":
            X.coop_sobol(a.coop_prefix)
        else:
            getattr(X, s)()
    X.write_manifest()
    print("status:")
    for k, v in X.status.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
