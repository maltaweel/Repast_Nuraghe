"""Shared helpers for the phase / workforce / centrality tools: scenario discovery and lean, streamed run loading.

Scenario families under an output root (default: the delivered v5 outputs, REF/output):
  baseline  output/nuraghe_manhours_runs.csv.gz
  coop      output/scenarios/<name>/            (none low mixed mostly full high patchwork)
  lit       output/scenarios_lit/<name>/        (webster + S1a..S8 + LOW/HIGH bounds = 22)
  alliance  output/scenarios_alliance/<name>/   (A0..A5, freerider, A0_verify)
  pre       output/scenarios_pre/<name>/        (P_* pre-existing networks)
Only the needed columns are read (usecols, small dtypes): one scenario is ~25-45 MB in memory.
"""
import glob
import os

import numpy as np
import pandas as pd

REF_ROOT = os.path.join(os.environ.get("NURAGHE_PROJECT", "."), "output")
SEASON_DAYS = 90
COOP = ["none", "low", "mixed", "mostly", "full", "high", "patchwork",
        "S9_sea_2kn", "S9_sea_4kn", "S9_sea_5kn", "S9_sea_6kn", "high_sea"]                       # merged: S9
LIT_ORDER = ["webster", "S1a_scree", "S1b_joints_low", "S1b_joints_high", "S2a_unworked", "S2b_fine",
             "S3a_rails_tallow", "S3b_rails_grease", "S3c_dry_ground", "S3d_rough", "S3e_oxen", "S4a_lever",
             "S4b_ramp", "S4c_internal_stair", "S5a_onsite", "S5b_any_buildstone", "S5c_complex_far", "S6_density",
             "S7_webster_classes", "S8_learning", "LOW", "HIGH", "REALISTIC", "REALISTIC_oxen"]   # merged: REALISTIC
ALLIANCE = ["A0_alone", "A1_ask", "A2_trust", "A3_trust_learning", "A4_trust_track", "A5_full", "A5_full_freerider",
            "A0_verify"]
# scenarios whose sites never interact (model.py: no inter_site_help) -> per-site days can be re-arranged post hoc
INDEPENDENT_FAMILIES = {"baseline", "lit"}
INDEPENDENT_COOP = {"none", "low", "mixed", "mostly", "full", "patchwork",
                    "S9_sea_2kn", "S9_sea_4kn", "S9_sea_5kn", "S9_sea_6kn"}   # merged: S9 sea (no inter-site help)


def scenarios(root=REF_ROOT):
    """[(family, name, runs_csv_gz)] for every scenario present under root."""
    out = []
    f = os.path.join(root, "nuraghe_manhours_runs.csv.gz")
    if os.path.exists(f):
        out.append(("baseline", "baseline", f))
    for n in COOP:
        f = os.path.join(root, "scenarios", n, "nuraghe_manhours_runs.csv.gz")
        if os.path.exists(f):
            out.append(("coop", n, f))
    for n in LIT_ORDER:
        f = os.path.join(root, "scenarios_lit", n, "nuraghe_manhours_runs.csv.gz")
        if os.path.exists(f):
            out.append(("lit", n, f))
    for n in ALLIANCE:
        f = os.path.join(root, "scenarios_alliance", n, "nuraghe_manhours_runs.csv.gz")
        if os.path.exists(f):
            out.append(("alliance", n, f))
    for f in sorted(glob.glob(os.path.join(root, "scenarios_alliance", "*", "nuraghe_manhours_runs.csv.gz"))):
        n = os.path.basename(os.path.dirname(f))                 # merged: _sea / _P10 / _P20 / MOST_REALISTIC variants
        if n not in ALLIANCE:
            out.append(("alliance", n, f))
    for f in sorted(glob.glob(os.path.join(root, "scenarios_pre", "P_*", "nuraghe_manhours_runs.csv.gz"))):
        out.append(("pre", os.path.basename(os.path.dirname(f)), f))
    return out


def independent(family, name):
    return family in INDEPENDENT_FAMILIES or (family == "coop" and name in INDEPENDENT_COOP)


def load_runs(path, family):
    """Lean per-(seed, site) table in file order (= seed, gid order). Alliance/pre also carry start/finish seasons."""
    cols = {"seed": np.int16, "TWR_N": np.int8, "days": np.int32, "builders": np.int16, "mh_total": np.float64}
    if family in ("alliance", "pre"):
        cols.update({"start_season": np.int32, "finish_season": np.int32})
    df = pd.read_csv(path, usecols=list(cols), dtype=cols)
    s = df.seed.to_numpy()
    assert (np.diff(s) >= 0).all(), f"{path}: rows not sorted by seed"
    return df


def by_seed(df):
    """Yield (seed, slice-view) per seed, keeping file (gid) order."""
    s = df.seed.to_numpy()
    cut = np.flatnonzero(np.diff(s)) + 1
    starts = np.concatenate([[0], cut]); ends = np.concatenate([cut, [len(s)]])
    for a, b in zip(starts, ends):
        yield int(s[a]), df.iloc[a:b]


def rss_mb():
    try:
        return int(open("/proc/self/status").read().split("VmHWM:")[1].split()[0]) // 1024
    except Exception:
        return -1


def oom_kill():
    try:
        return int(dict(l.split() for l in open("/sys/fs/cgroup/memory.events"))["oom_kill"])
    except Exception:
        return -1
