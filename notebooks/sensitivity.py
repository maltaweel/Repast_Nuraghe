"""Sensitivity analysis of the headline scenario MOST_REALISTIC_AUDITED_LIT_P10 (notebooks/06_sensitivity.ipynb).

Two global designs on the model (code/) and the model's configuration
(config/scenarios/config_full_audited.yaml, copied by 02 to WORK_DIR/config.yaml):

1. Morris screening (elementary effects; Morris 1991): 32 factors (the parameters that the parameter audit lists as
   the authors' assumptions, with a value range each), SALib morris.sample, p = 4 levels, delta = 2/3.
   Full design: r = 10 trajectories, sample seed 20261109, r (k + 1) = 330 evaluations x seeds 1-3.
2. Sobol indices (Saltelli 2010 design; first-order S1 and total ST): the 24 factors kept after the Morris screen,
   plus R_m (help radius, 5-15 km) and lift_learning (see below). SALib sobol.sample(N, calc_second_order=False,
   scramble=True). Full design: N = 512, sample seed 20261110, k = 26, N (k + 2) = 14,336 evaluations x seeds 1-3.
   Fixed at the headline values: the other 8 Morris factors and alliance.alliance_threshold.

One evaluation = one design row x the seeds (common random numbers: every evaluation runs the same seeds); each seed
is one run of the season engine in a single process (alliance.Static + alliance.AllianceModel, the code's own
classes); the evaluation's value is the mean over the seeds of
    island years       = (max finish_day + 1) / alliance.season_days (the run's own season length)
    island man-hours   = sum of mh_total over the sites
    transport share    = sum of mh_transport / sum of mh_total
Every factor value is applied to an in-memory deep copy of the configuration and the scenario (apply()); no file of
code/ or config/ is changed.

Level mapping of the unit sample u: unif lo + u (hi - lo); binary u < 0.5 -> level 0 (the headline), else level 1;
int: Morris round(lo + u (hi - lo)) (u is on the 4-level grid), Sobol equal-probability bins
lo + floor(u (hi - lo + 1)).

lift_learning (Sobol only): level 0 = lift undiscounted (the model's rule, spec addendum k: the learning factor and skill
act on quarrying, dressing and building only, never on lift); level 1 = lift discounted with the build stage (an
earlier rule). Level 1 needs a code switch (config key sobol.lift_learning) that is NOT in the published code/: the
full Sobol run used a copy of code/ with that one switch added (sensitivity/sobol2/code_variant.patch; default off =
code/ exactly). With the
published code the factor is therefore left out of the demo (demo_names("sobol")); the full design is still
regenerated with it (sobol_design(SOBOL_NAMES, 512)) so that it can be compared with the design file of the results
package.

stone_rule (both designs): level 1 (stones7) needs the alternative derived-input cache built with the stones7 rule
(the queue's cache_alt_stones7, data/derived/README.md, 'Own caches of the queue'). Without it (stones7_cache=None)
the factor is left out of a demo and fixed at hybrid.

Command line (what the notebook calls; run from WORK_DIR/code so that the model code is imported from there):
    python sensitivity.py evaluate --config CFG --design DESIGN.csv --out RESULTS.csv --seeds 1-3 [--first-n 30]
                                   [--sites UID,UID] [--stones7-cache DIR]
Results are appended per evaluation and finished evaluations are skipped (resume after a disconnect).
"""
import argparse
import copy
import csv
import json
import math
import os
import sys
import time
import types

HEADLINE = "MOST_REALISTIC_AUDITED_LIT_P10"
CODE_VERSION = "2026-11-09-v17"
OUTPUTS = ["island_years", "island_mh", "mh_transport_share"]
RES_COLS = ["eval_id", "seed", "island_years", "island_mh", "mh_transport_share", "seasons", "status", "error",
            "wall_s", "static_s"]

MORRIS_FULL = {"r": 10, "num_levels": 4, "seed": 20261109, "seeds": [1, 2, 3], "n_evals": 330}
SOBOL_FULL = {"N": 512, "seed": 20261110, "seeds": [1, 2, 3], "k": 26, "n_evals": 14336,
              "calc_second_order": False, "scramble": True}

# --------------------------------------------------------------------------------------------- factors
# row = row of param_audit/PARAM_AUDIT.md; headline = the value in the model's configuration; key = what apply() sets.
FACTORS = [
    dict(name="n_phases", row="T1", kind="int", lo=5, hi=15, headline=10,
         key="sc.phase_frac = 1 / n_phases", why="+/-50% of 10 cohorts (P10); 5 cohorts = the P20 variant"),
    dict(name="season_days", row="T3", kind="unif", lo=40.0, hi=120.0, headline=90.0, key="cfg.alliance.season_days",
         why="communal-labour alternatives: 40 (Erasmus via Webster 1991: 853) to 120 (Turner 2020: 80)"),
    dict(name="block_min_kg", row="B4", kind="unif", lo=30.0, hi=143.0, headline=60.0, key="cfg.stone.block_min_kg",
         why="lower -50%; upper 143 kg = Webster 1991: 852 '< 0.06 m3' x 2,386 kg/m3"),
    dict(name="rho_limestone", row="B9", kind="unif", lo=2420.0, hi=2711.0, headline=2600.0,
         key="cfg.lit_scenarios.density_kg_m3.limestone/marble",
         why="textbook limestone 2,420 to Turner 2020 marble 2,711"),
    dict(name="hardness_hard", row="B11", kind="unif", lo=1.0, hi=3.0, headline=2.0,
         key="cfg.lit_scenarios.hardness.basalt = .granite", why="+/-50% of 2.0; 1.0 = no hard-stone penalty"),
    dict(name="bedrock_everywhere", row="Q3", kind="binary", levels=[True, False], headline=True,
         key="cfg.add4.bedrock_everywhere", why="rule L2 on (headline) vs off (off-outcrop sites collect scree)"),
    dict(name="dress_rule", row="Q4", kind="binary", levels=["by_towers", "webster_all"], headline="by_towers",
         key="cfg.lit_scenarios.list.REALISTIC.mixed.dress_none_max_towers / dress_fine_min_towers",
         why="rule (none 1 tower, Webster 2, fine >= 3) vs Webster dressing at every site"),
    dict(name="lift_share_of_build", row="G6", kind="unif", lo=0.25, hi=0.75, headline=0.5,
         key="cfg.lit_scenarios.lift_share_of_build", why="+/-50% of 0.5 (no source)"),
    dict(name="stair_lever_last_m", row="G7", kind="unif", lo=0.5, hi=1.5, headline=1.0,
         key="cfg.lit_scenarios.stair_lever_last_m", why="+/-50% of 1.0 m (Laner 1999 gives no time)"),
    dict(name="lift_rule", row="G8", kind="binary", levels=["by_type", "stair_all"], headline="by_type",
         key="cfg.lit_scenarios.list.REALISTIC.mixed.lift_by_type",
         why="lever for corridor nuraghi, stair otherwise vs stair everywhere"),
    dict(name="learning_rate", row="G9", kind="unif", lo=0.075, hi=0.225, headline=0.15,
         key="cfg.lit_scenarios.learning_rate", why="+/-50% of 0.15 (no archaeological rate)"),
    dict(name="min_haul_flatm", row="H6", kind="unif", lo=10.0, hi=20.0, headline=15.0, key="cfg.transport.min_haul_flatm",
         why="the authors' stated 10-20 m (15 = midpoint); land/sea choice stays as cached"),
    dict(name="long_min_haul_m", row="H9", kind="unif", lo=500.0, hi=1500.0, headline=1000.0,
         key="cfg.lit_scenarios.list.REALISTIC.mixed.long_min_haul_m", why="+/-50% of 1,000 m (no source)"),
    dict(name="relay_min_flatm", row="H12", kind="unif", lo=150.0, hi=450.0, headline=300.0,
         key="cfg.alliance.relay_min_flatm", why="+/-50% of 300 flat-m (no source)"),
    dict(name="relay_fractions", row="H12", kind="binary", levels=["0.25/0.5/0.75", "0.5"], headline="0.25/0.5/0.75",
         key="cfg.alliance.relay_fractions", why="3 hand-off points (headline) vs the single midpoint hand-off"),
    dict(name="split_cost_mh", row="H13", kind="unif", lo=0.0, hi=2.0, headline=1.0, key="cfg.scenarios.split_cost_mh",
         why="0 = the alt_split0 row; 2 = symmetric"),
    dict(name="stone_rule", row="K1", kind="binary", levels=["hybrid", "stones7"], headline="hybrid",
         key="cfg.stone_rule + cfg.paths.cache_dir (the stones7 cache)",
         why="hybrid (recorded stone, else nearest of 7) vs stones7 (nearest of 7 only)"),
    dict(name="setup_mh", row="K3", kind="unif", lo=100.0, hi=300.0, headline=200.0, key="cfg.alliance.setup_mh",
         why="+/-50% of 200 ph"),
    dict(name="near_site_fixed_face_m", row="K4", kind="unif", lo=500.0, hi=1500.0, headline=1000.0,
         key="cfg.quarry.near_site_fixed_face_m", why="+/-50% of 1,000 m (no source)"),
    dict(name="max_asks", row="A2", kind="int", lo=1, hi=5, headline=3, key="cfg.alliance.max_asks",
         why="+/-50% of 3, rounded outward"),
    dict(name="trust0", row="A3", kind="unif", lo=0.25, hi=0.75, headline=0.5, key="cfg.alliance.trust0", why="+/-50%"),
    dict(name="delta_up", row="A3", kind="unif", lo=0.05, hi=0.15, headline=0.1, key="cfg.alliance.delta_up", why="+/-50%"),
    dict(name="delta_down", row="A3", kind="unif", lo=0.1, hi=0.3, headline=0.2, key="cfg.alliance.delta_down", why="+/-50%"),
    dict(name="beta0", row="A4", kind="unif", lo=-1.0, hi=1.0, headline=0.0, key="cfg.alliance.beta0",
         why="value 0: +/-1 logit unit"),
    dict(name="beta1", row="A4", kind="unif", lo=1.0, hi=3.0, headline=2.0, key="cfg.alliance.beta1", why="+/-50%"),
    dict(name="beta2", row="A4", kind="unif", lo=0.025, hi=0.075, headline=0.05, key="cfg.alliance.beta2", why="+/-50%"),
    dict(name="beta3", row="A4", kind="unif", lo=0.1, hi=0.3, headline=0.2, key="cfg.alliance.beta3", why="+/-50%"),
    dict(name="alpha", row="A7", kind="unif", lo=0.25, hi=0.75, headline=0.5, key="cfg.alliance.alpha", why="+/-50%"),
    dict(name="p_imit", row="A8", kind="unif", lo=0.15, hi=0.45, headline=0.3, key="cfg.alliance.p_imit", why="+/-50%"),
    dict(name="help_mode", row="A9", kind="binary", levels=["join", "handover"], headline="join", key="sc.help_mode",
         why="join (headline) vs handover (the helper takes the task over)"),
    dict(name="specialisation", row="A9", kind="binary", levels=[True, False], headline=True, key="sc.specialisation",
         why="skill specialisation on (headline) vs off"),
    dict(name="transfer_h", row="S4", kind="unif", lo=0.125, hi=0.375, headline=0.25, key="cfg.sea.transfer_h",
         why="+/-50% of 0.25 h; land/sea choice stays as cached"),
]
MORRIS_NAMES = [f["name"] for f in FACTORS]                    # the order of the full Morris design
# kept for the Sobol run after the Morris screen (in the order of the full Sobol design)
SOBOL_MORRIS = ["season_days", "n_phases", "stone_rule", "hardness_hard", "dress_rule", "help_mode", "max_asks",
                "long_min_haul_m", "specialisation", "bedrock_everywhere", "beta0", "lift_share_of_build",
                "split_cost_mh", "p_imit", "beta3", "trust0", "lift_rule", "beta1", "beta2", "stair_lever_last_m",
                "rho_limestone", "learning_rate", "near_site_fixed_face_m", "min_haul_flatm"]
SOBOL_FIXED = sorted(set(MORRIS_NAMES) - set(SOBOL_MORRIS))     # + alliance.alliance_threshold
FACTORS += [
    dict(name="R_m", row="A1", kind="unif", lo=5000.0, hi=15000.0, headline=10000.0,
         key="sc.R_m (help radius of the scenario; alliance.R_m unchanged)", why="5-15 km (no help-distance source)"),
    dict(name="lift_learning", row="-", kind="binary", levels=[False, True], headline=False,
         key="cfg.sobol.lift_learning (code switch, not in the published code)",
         why="lift undiscounted (headline) vs discounted with the build stage (earlier rule)"),
]
SOBOL_NAMES = SOBOL_MORRIS + ["R_m", "lift_learning"]
FBY = {f["name"]: f for f in FACTORS}
assert len(MORRIS_NAMES) == 32 and len(SOBOL_NAMES) == 26 and len(SOBOL_FIXED) == 8


def factor_table(names):
    """The factors of a design as a table (name, audit row, kind, range or levels, headline value, what is set)."""
    import pandas as pd
    return pd.DataFrame([{"factor": n, "row": FBY[n]["row"], "kind": FBY[n]["kind"],
                          "range / levels": (FBY[n]["levels"] if FBY[n]["kind"] == "binary" else [FBY[n]["lo"], FBY[n]["hi"]]),
                          "headline": FBY[n]["headline"], "sets": FBY[n]["key"], "why": FBY[n]["why"]} for n in names])


def to_value(f, u, design):
    """Unit sample u -> factor value (design 'morris' or 'sobol'; they differ for int factors only)."""
    u = float(u)
    if f["kind"] == "unif":
        return float(f["lo"] + u * (f["hi"] - f["lo"]))
    if f["kind"] == "int":
        if design == "morris":
            return int(round(f["lo"] + u * (f["hi"] - f["lo"])))
        n = int(f["hi"]) - int(f["lo"]) + 1
        return int(f["lo"]) + min(int(math.floor(u * n)), n - 1)
    return f["levels"][0 if u < 0.5 else 1]


def problem(names):
    return {"num_vars": len(names), "names": list(names), "bounds": [[0.0, 1.0]] * len(names)}


def demo_names(design, stones7_cache=None, include_lift_learning=False):
    """Factor list of a demo: the full list without the factors whose alternative level needs an input or a code
    switch that is not at hand (stone_rule without the stones7 cache; lift_learning with the published code)."""
    names = list(MORRIS_NAMES if design == "morris" else SOBOL_NAMES)
    dropped = []
    if not stones7_cache:
        dropped.append(("stone_rule", "fixed at hybrid: no stones7 derived-input cache (STONES7_CACHE)"))
    if design == "sobol" and not include_lift_learning:
        dropped.append(("lift_learning", "fixed at undiscounted (headline): the switch for level 1 is not in the published code"))
    for n, why in dropped:
        names.remove(n)
        print(f"  {n}: {why}")
    return names


# --------------------------------------------------------------------------------------------- designs
def _frame(U, names, design, block_of):
    import pandas as pd
    rows = []
    for e, u in enumerate(U):
        r = {"eval_id": e, **block_of(e)}
        r.update({f"u_{n}": float(u[i]) for i, n in enumerate(names)})
        r.update({n: to_value(FBY[n], u[i], design) for i, n in enumerate(names)})
        rows.append(r)
    return pd.DataFrame(rows)


def morris_design(names, r, seed=MORRIS_FULL["seed"], num_levels=MORRIS_FULL["num_levels"]):
    """SALib morris.sample (r trajectories, p levels): one row per evaluation (eval_id, traj, step, u_*, values)."""
    from SALib.sample import morris as ms
    k = len(names)
    U = ms.sample(problem(names), N=r, num_levels=num_levels, optimal_trajectories=None, seed=seed)
    assert U.shape == (r * (k + 1), k)
    return _frame(U, names, "morris", lambda e: {"traj": e // (k + 1), "step": e % (k + 1)})


def sobol_design(names, N, seed=SOBOL_FULL["seed"]):
    """SALib sobol.sample (Saltelli, scrambled Sobol sequence, no second order): N (k + 2) rows in SALib order
    (per base row j: A, AB_1 .. AB_k, B)."""
    from SALib.sample import sobol
    k = len(names)
    U = sobol.sample(problem(names), N, calc_second_order=False, scramble=True, seed=seed)
    assert U.shape == (N * (k + 2), k)

    def blk(e):
        j, c = divmod(e, k + 2)
        return {"base_row": j, "block": "A" if c == 0 else ("B" if c == k + 1 else f"AB_{names[c - 1]}")}
    return _frame(U, names, "sobol", blk)


def compare_design(regenerated, path, names):
    """True if the unit samples and values of a design file (e.g. the full design of the results package) equal the
    regenerated design (unit samples to 1e-12; values as text)."""
    import numpy as np
    import pandas as pd
    D = pd.read_csv(path, float_precision="round_trip", keep_default_na=False)
    if len(D) != len(regenerated):
        print(f"{path}: {len(D)} rows, regenerated {len(regenerated)}")
        return False
    a = D[[f"u_{n}" for n in names]].to_numpy(float)
    b = regenerated[[f"u_{n}" for n in names]].to_numpy(float)
    du = float(np.max(np.abs(a - b)))
    vals = all((D[n].astype(str).str.lower() == regenerated[n].astype(str).str.lower()).all() or
               np.allclose(pd.to_numeric(D[n]), pd.to_numeric(regenerated[n]), rtol=1e-12, atol=0)
               for n in names if FBY[n]["kind"] != "binary") and \
        all((D[n].astype(str).str.lower() == regenerated[n].astype(str).str.lower()).all()
            for n in names if FBY[n]["kind"] == "binary")
    print(f"{path}: {len(D)} rows; max |u difference| {du:.1e}; values equal: {vals}")
    return du < 1e-12 and vals


# --------------------------------------------------------------------------------------------- model side
def apply(cfg0, sc0, values, stones7_cache=None):
    """Deep copies of the headline config / scenario with the factor values set (only the factor keys change)."""
    cfg, sc = copy.deepcopy(cfg0), copy.deepcopy(sc0)
    mixed = cfg["lit_scenarios"]["list"]["REALISTIC"]["mixed"]
    for k, x in values.items():
        f = FBY[k]
        if k == "n_phases":
            sc["phase_frac"] = 1.0 / int(x)
        elif k == "season_days":
            cfg["alliance"]["season_days"] = float(x)
        elif k == "block_min_kg":
            cfg["stone"]["block_min_kg"] = float(x)
        elif k == "rho_limestone":
            cfg["lit_scenarios"]["density_kg_m3"]["limestone/marble"] = float(x)
        elif k == "hardness_hard":
            cfg["lit_scenarios"]["hardness"]["basalt"] = float(x)
            cfg["lit_scenarios"]["hardness"]["granite"] = float(x)
        elif k == "bedrock_everywhere":
            if x != f["headline"]:
                cfg["add4"] = {"bedrock_everywhere": bool(x)}
        elif k == "dress_rule":
            if x == "webster_all":
                mixed["dress_none_max_towers"] = 0
                mixed["dress_fine_min_towers"] = 99
        elif k == "lift_share_of_build":
            cfg["lit_scenarios"]["lift_share_of_build"] = float(x)
        elif k == "stair_lever_last_m":
            cfg["lit_scenarios"]["stair_lever_last_m"] = float(x)
        elif k == "lift_rule":
            if x == "stair_all":
                mixed["lift_by_type"] = {}
        elif k == "learning_rate":
            cfg["lit_scenarios"]["learning_rate"] = float(x)
        elif k == "min_haul_flatm":
            cfg["transport"]["min_haul_flatm"] = float(x)
        elif k == "long_min_haul_m":
            mixed["long_min_haul_m"] = float(x)
        elif k == "relay_min_flatm":
            cfg["alliance"]["relay_min_flatm"] = float(x)
        elif k == "relay_fractions":
            if x == "0.5":
                cfg["alliance"]["relay_fractions"] = [0.5]
        elif k == "split_cost_mh":
            cfg["scenarios"]["split_cost_mh"] = float(x)
        elif k == "stone_rule":
            if x == "stones7":
                if not stones7_cache:
                    raise ValueError("stone_rule = stones7 needs the stones7 derived-input cache (--stones7-cache)")
                cfg["stone_rule"] = "stones7"
                cfg["paths"]["cache_dir"] = stones7_cache
        elif k == "setup_mh":
            cfg["alliance"]["setup_mh"] = float(x)
        elif k == "near_site_fixed_face_m":
            cfg["quarry"]["near_site_fixed_face_m"] = float(x)
        elif k == "max_asks":
            cfg["alliance"][k] = int(x)
        elif k in ("trust0", "delta_up", "delta_down", "beta0", "beta1", "beta2", "beta3", "alpha", "p_imit"):
            cfg["alliance"][k] = float(x)
        elif k == "help_mode":
            if x == "handover":
                sc.pop("help_mode", None)
                sc.pop("join_hands_per_block", None)
        elif k == "specialisation":
            sc["specialisation"] = bool(x)
        elif k == "transfer_h":
            cfg["sea"]["transfer_h"] = float(x)
        elif k == "R_m":                                   # the headline value leaves the scenario untouched
            if float(x) != float(cfg["alliance"]["R_m"]):
                sc["R_m"] = float(x)
        elif k == "lift_learning":
            if bool(x):
                import lit
                if not hasattr(lit, "lift_learning"):
                    raise ValueError("lift_learning = True needs the code switch sobol.lift_learning, which is not in "
                                     "the published code (see the module docstring)")
                cfg["sobol"] = {"lift_learning": True}
        else:
            raise KeyError(k)
    return cfg, sc


def decode(n, v):
    f = FBY[n]
    if f["kind"] == "int":
        return int(float(v))
    if f["kind"] == "unif":
        return float(v)
    for lv in f["levels"]:
        if str(lv).lower() == str(v).lower():
            return lv
    raise ValueError((n, v))


class Unfinished(Exception):
    pass


def _evaluate(a):
    import numpy as np  # noqa: F401  (imported by the model anyway)
    import pandas as pd
    import alliance
    import lit
    import model
    from nbcommon import load_config
    assert lit.CODE_VERSION == CODE_VERSION, f"code version {lit.CODE_VERSION}, expected {CODE_VERSION}"
    cfg0 = load_config(a.config)
    sc0 = copy.deepcopy(alliance.scenario(cfg0, HEADLINE))
    D = pd.read_csv(a.design, float_precision="round_trip", keep_default_na=False)
    names = [c[2:] for c in D.columns if c.startswith("u_")]
    seeds = [s for part in a.seeds.split(",") for s in range(int(part.partition("-")[0]),
                                                              int(part.partition("-")[2] or part.partition("-")[0]) + 1)]
    done = set()
    if os.path.isfile(a.out):
        R = pd.read_csv(a.out)
        ok = R[R.status.isin(["ok", "unfinished"])]
        done = {e for e, g in ok.groupby("eval_id") if set(g.seed) >= set(seeds)}
    else:
        with open(a.out, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=RES_COLS).writeheader()
    hauls = {}
    todo = [int(e) for e in D.eval_id if int(e) not in done]
    print(f"{len(D)} evaluations in {os.path.basename(a.design)}, {len(done)} done, {len(todo)} to run; seeds {seeds}; "
          f"sites: {'first ' + str(a.first_n) if a.first_n else (a.sites or 'all')}", flush=True)
    t00 = time.time()
    for n_done, e in enumerate(todo):
        r = D.loc[D.eval_id == e].iloc[0]
        vals = {n: decode(n, r[n]) for n in names}
        cfg, sc = apply(cfg0, sc0, vals, a.stones7_cache)
        p = os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv")
        if p not in hauls:
            hauls[p] = model.load_haul(cfg, types.SimpleNamespace(sites=a.sites, first_n=a.first_n), p)
        ts = time.time()
        S = alliance.Static(cfg, hauls[p], float(sc.get("R_m", cfg["alliance"]["R_m"])),
                            sea_kn=float(sc["sea_kn"]) if sc.get("sea_kn") else None, tech=sc.get("tech_rules"))
        static_s = time.time() - ts
        rows = []
        for seed in seeds:
            t1 = time.time()
            row = {"eval_id": e, "seed": seed, "static_s": round(static_s, 2)}
            try:
                m = alliance.AllianceModel(S, sc, int(seed))
                try:
                    m.run()
                except AssertionError as err:
                    if "unfinished towers at max_seasons" not in str(err):
                        raise
                    raise Unfinished(int(m.season))
                s = m.results()[0]
                T = float(s.mh_total.sum())
                row.update(island_years=(float(s.finish_day.max()) + 1.0) / float(cfg["alliance"]["season_days"]),
                           island_mh=T, mh_transport_share=float(s.mh_transport.sum()) / T, seasons=int(m.season),
                           status="ok", error="")
                del m, s
            except Unfinished as err:
                row.update({o: float("nan") for o in OUTPUTS}, seasons=err.args[0], status="unfinished",
                           error="unfinished at max_seasons")
            except Exception as err:          # recorded; a rerun retries it
                row.update({o: float("nan") for o in OUTPUTS}, seasons=-1, status="error",
                           error=f"{type(err).__name__}: {err}"[:300])
            row["wall_s"] = round(time.time() - t1, 2)
            rows.append(row)
        del S
        with open(a.out, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=RES_COLS)
            for row in rows:
                w.writerow({k: (repr(row[k]) if isinstance(row.get(k), float) else row.get(k, "")) for k in RES_COLS})
        if n_done % 10 == 0 or n_done == len(todo) - 1:
            el = time.time() - t00
            print(f"  eval {e}: {[x['status'] for x in rows]}; {n_done + 1}/{len(todo)} in {el:.0f} s "
                  f"(about {el / (n_done + 1) * (len(todo) - n_done - 1):.0f} s left)", flush=True)


# --------------------------------------------------------------------------------------------- notebook side
def run_design(work_dir, design, design_csv, results_csv, seeds="1", first_n=None, sites=None, stones7_cache=None,
               lock=None, python=sys.executable):
    """Write the design to DESIGN_CSV and evaluate it in one process from WORK_DIR/code (resumable)."""
    import repro
    os.makedirs(os.path.dirname(os.path.abspath(design_csv)), exist_ok=True)
    design.to_csv(design_csv, index=False, float_format="%.17g")
    args = [python, os.path.abspath(__file__), "evaluate", "--config", os.path.join(work_dir, "config.yaml"),
            "--design", design_csv, "--out", results_csv, "--seeds", str(seeds)]
    if first_n:
        args += ["--first-n", str(int(first_n))]
    if sites:
        args += ["--sites", sites]
    if stones7_cache:
        args += ["--stones7-cache", stones7_cache]
    # one process, no MPI peers: the shared-memory transport is not needed (small /dev/shm on some machines)
    os.environ.setdefault("OMPI_MCA_btl", "self")
    repro.sh(args, cwd=os.path.join(work_dir, "code"), lock=lock)
    return results_csv


def per_eval(results_csv, design):
    """Mean over the seeds per evaluation (NaN unless every seed finished), in design order."""
    import pandas as pd
    R = pd.read_csv(results_csv).drop_duplicates(["eval_id", "seed"], keep="last")
    ok = R[R.status == "ok"].groupby("eval_id")[OUTPUTS].mean()
    bad = set(R[R.status != "ok"].eval_id)
    Y = ok.reindex(design.eval_id)
    Y.loc[Y.index.isin(bad)] = float("nan")
    return Y


def morris_indices(design, Y, names, num_levels=MORRIS_FULL["num_levels"]):
    """SALib morris.analyze per output: mu* (with its 95% bootstrap interval), mu, sigma, mu* relative to the mean."""
    import pandas as pd
    from SALib.analyze import morris as ma
    X = design[[f"u_{n}" for n in names]].to_numpy(float)
    rows = []
    for o in OUTPUTS:
        y = Y[o].to_numpy(float)
        if not (y == y).all():
            raise ValueError(f"{o}: {int((y != y).sum())} evaluations without a value; rerun them first")
        Si = ma.analyze(problem(names), X, y, num_levels=num_levels, print_to_console=False, seed=1)
        for i, n in enumerate(names):
            rows.append({"output": o, "factor": n, "mu_star": Si["mu_star"][i], "mu_star_conf": Si["mu_star_conf"][i],
                         "mu": Si["mu"][i], "sigma": Si["sigma"][i], "mu_star_rel": Si["mu_star"][i] / y.mean()})
    t = pd.DataFrame(rows)
    t["rank"] = t.groupby("output").mu_star.rank(ascending=False, method="min").astype(int)
    return t.sort_values(["output", "rank"]).reset_index(drop=True)


def sobol_indices(Y, names, num_resamples=1000):
    """SALib sobol.analyze per output (no second order): S1, ST and their 95% bootstrap half-widths."""
    import pandas as pd
    from SALib.analyze import sobol
    rows = []
    for o in OUTPUTS:
        y = Y[o].to_numpy(float)
        if not (y == y).all():
            raise ValueError(f"{o}: {int((y != y).sum())} evaluations without a value; rerun them first")
        Si = sobol.analyze(problem(names), y, calc_second_order=False, num_resamples=num_resamples, conf_level=0.95,
                           print_to_console=False, seed=1)
        for i, n in enumerate(names):
            rows.append({"output": o, "factor": n, "S1": Si["S1"][i], "S1_conf": Si["S1_conf"][i], "ST": Si["ST"][i],
                         "ST_conf": Si["ST_conf"][i]})
    t = pd.DataFrame(rows)
    return t.sort_values(["output", "ST"], ascending=[True, False]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("evaluate")
    e.add_argument("--config", required=True)
    e.add_argument("--design", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--seeds", default="1,2,3")
    e.add_argument("--first-n", type=int, default=None)
    e.add_argument("--sites", default=None)
    e.add_argument("--stones7-cache", default=None)
    a = ap.parse_args()
    if a.cmd == "evaluate":
        sys.path.insert(0, os.getcwd())                   # the model code (run from WORK_DIR/code)
        _evaluate(a)


if __name__ == "__main__":
    main()
