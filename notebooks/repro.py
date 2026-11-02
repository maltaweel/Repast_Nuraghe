"""Helpers shared by the nuraghe-build-abm notebooks (01-05) in this repository.

Everything a notebook does that is longer than a few lines lives here, so the notebooks stay readable.
Standard library + pandas only. Adapted from the 31 Oct 2026 (code v8) reproducibility package to the repository
layout; the folders are set once by set_layout() (the notebooks' config cell does it):

    REPO_DIR/
        code/                    the model code (frozen snapshot of the full audited run; see CODE_PROVENANCE.md)
        config/                  config_full_audited.yaml (+ variants, queues)
        data/                    raw inputs, in the layout the configs expect under data_dir (data/README.md)
            sites/, stone/           copies of Nurnet's data from data/nurnet/ (made by fetch_data.py)
        data/nurnet/             Nurnet's data, included: site list + per-site building stone (data/nurnet/README.txt)
        data/derived/cache/      cached derived inputs (haul tables, k-best quarry routes, sea routes, ...;
                                 data/derived/README.md), downloaded from the results package or rebuilt
        outputs/                 everything the notebooks write (work copy, runs, optional reference/)
        notebooks/               01_setup ... 05_audit, repro.py, fetch_data.py, requirements-colab.txt, inputs_manifest.csv
    WORK_DIR/                    fast local disk: code copy, cache copy, config.yaml, outputs (default REPO_DIR/outputs/work)
"""
import csv
import glob
import gzip
import hashlib
import io
import os
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from fetch_data import NURNET_NOTE  # noqa: E402  (the note on how to request the Nurnet files)

# --------------------------------------------------------------------------- folder layout (set_layout)
LAYOUT = {
    "data": os.path.join(REPO, "data"),                                   # raw inputs (= data_dir of the config)
    "cache": os.path.join(REPO, "data", "derived", "cache"),             # cached derived inputs (prebuilt cache)
    "config": os.path.join(REPO, "config", "config_full_audited.yaml"),  # base configuration
    "reference": os.path.join(REPO, "outputs", "reference"),             # optional reference result (not in the repo)
}


def set_layout(repo=None, data=None, cache=None, config=None, reference=None):
    """Point the helpers at the repository folders. None or "auto" keeps the default under the repository."""
    global REPO
    if repo not in (None, "auto"):
        REPO = os.path.abspath(repo)
    defaults = {"data": os.path.join(REPO, "data"), "cache": os.path.join(REPO, "data", "derived", "cache"),
                "config": os.path.join(REPO, "config", "config_full_audited.yaml"),
                "reference": os.path.join(REPO, "outputs", "reference")}
    for k, v in (("data", data), ("cache", cache), ("config", config), ("reference", reference)):
        LAYOUT[k] = os.path.abspath(v) if v not in (None, "auto") else defaults[k]
    return dict(LAYOUT)


def resolve(path):
    """A manifest path (data/..., derived/..., reference/..., code/...) -> the file on disk under the layout."""
    head, _, rest = path.partition("/")
    if head == "data":
        return os.path.join(LAYOUT["data"], rest)
    if head == "derived":
        return os.path.join(LAYOUT["cache"], rest)
    if head == "reference":
        return os.path.join(LAYOUT["reference"], rest)
    return os.path.join(REPO, path)

# --------------------------------------------------------------------------- stone rule
# Default stone rule: hybrid, the rule of the full audited run (recorded building stone per site where known, else the
# nearest outcrop of the 7 permitted classes). The per-site file it needs is Nurnet's data (site building stone),
# included as data/nurnet/nurnet_site_building_stone.csv and copied to SA_REL by fetch_data.py. 'stones7' (every site
# the nearest outcrop of the 7 classes) is the fallback without that file; results then differ.
SHIPPED_STONE_RULE = "hybrid"
SA_REL = "data/stone/nid_materiale_prod.csv"
SA_COLUMNS = ["codice", "sa_materiale"]          # codice = Nurnet UID (e.g. NID0052900); sa_materiale = recorded stone

# --------------------------------------------------------------------------- the reference subset
# 300 sites (code/sites300_real.txt), seeds 1-3, 4 scenarios. A reference fingerprint (reference_sha256.csv) must be
# made with the SAME code and cache (write_fingerprint); none is shipped in the repository (see notebooks/README.md).
REF_SEEDS = "1-3"
REF_SITES_FILE = "sites300_real.txt"
REF_RUNS = [  # (name, model.py arguments after config.yaml)
    ("baseline", []),
    ("webster", ["--lit", "webster"]),
    ("A5_full", ["--alliance", "A5_full"]),
    ("MOST_REALISTIC_P10", ["--alliance", "MOST_REALISTIC_P10"]),
]


class PreflightError(RuntimeError):
    pass


# --------------------------------------------------------------------------- hashing
def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- manifest + preflight
def read_manifest(package_dir=None):
    with open(os.path.join(HERE, "inputs_manifest.csv"), newline="") as f:
        return list(csv.DictReader(f))


def preflight(package_dir, need="reference", check_hash=True, extra_groups=()):
    """Check that every file needed for `need` is present and has the expected SHA-256.

    need: 'reference' (prebuilt cache, 300-site check), 'run' (any scenario from the prebuilt cache),
          'rebuild' (rebuild the cache from raw inputs). Rows whose needed_for column contains `need` are checked.
    Raises PreflightError with a list of what is missing / wrong and how to fix it. Returns the checked rows.
    """
    rows = [r for r in read_manifest(package_dir) if any(n.startswith(need) for n in r["needed_for"].split(";"))
            or r["group"] in extra_groups]
    prov = fetch_provenance()
    missing, wrong, rebuilt, ok = [], [], [], 0
    t0 = time.time()
    for r in rows:
        if r["group"] == "user_supplied":
            continue                                    # handled by materiale_status(): optional
        p = resolve(r["path"])
        if not os.path.isfile(p):
            missing.append(r["path"])
            continue
        if check_hash and r["sha256"]:
            got = sha256(p)
            if got != r["sha256"]:
                rel = r["path"].split("/", 1)[1]
                pv = prov.get(rel) or {}
                if str(pv.get("status", "")).startswith("rebuilt") and pv.get("sha256") == got:
                    rebuilt.append((r["path"], pv.get("note", "")))   # rebuilt from the official source by fetch_data.py
                else:
                    wrong.append((r["path"], f"SHA-256 differs from inputs_manifest.csv (size {os.path.getsize(p):,} B, "
                                             f"run copy {int(r['bytes'] or 0):,} B)"))
                continue
        elif r["bytes"] and int(r["bytes"]) != os.path.getsize(p):
            wrong.append((r["path"], f"size {os.path.getsize(p):,} B, expected {int(r['bytes']):,} B"))
            continue
        ok += 1
    n = len([r for r in rows if r["group"] != "user_supplied"])
    print(f"preflight '{need}': {ok} of {n} files identical to the run's copies, {len(rebuilt)} rebuilt from the official "
          f"source (not byte-comparable), {len(missing)} missing, {len(wrong)} wrong "
          f"({'size + SHA-256' if check_hash else 'size only'}, {time.time() - t0:.0f} s); data {LAYOUT['data']}")
    for p, why in rebuilt:
        print(f"  REBUILT  {p}: {why[:160]}")
    if missing or wrong:
        msg = [f"PREFLIGHT FAILED for '{need}': {len(missing)} missing, {len(wrong)} wrong."]
        for p in missing[:40]:
            msg.append(f"  MISSING  {p}")
        if len(missing) > 40:
            msg.append(f"  ... and {len(missing) - 40} more missing")
        for p, why in wrong[:40]:
            msg.append(f"  WRONG    {p}: {why}")
        msg += ["How to fix (step by step: notebooks/HOW_TO_USE.md):",
                "  * REPO_DIR must point at the cloned repository; DATA_DIR / DERIVED_DIR at the input folders",
                "    (defaults: REPO_DIR/data and REPO_DIR/data/derived/cache).",
                "  * Missing public raw input: run notebooks/fetch_data.py (02_inputs.ipynb, section 0) or link it by hand",
                "    (HOW_TO_USE.md, 'Linking the data yourself'), keeping the file name and folder."]
        if any(p.startswith("data/sites/") for p in missing):
            msg += ["  * Missing Nurnet site list (REQUIRED): run fetch_data.py (it copies data/nurnet/ to DATA_DIR/sites/). " + NURNET_NOTE]
        msg += ["  * Missing derived input: download the derived-input pack (DERIVED_URL, when public) or rebuild it",
                "    (fetch_data.py --rebuild-derived; data/derived/README.md).",
                "  * Wrong SHA-256: the file is truncated or a different version. Download it again."]
        raise PreflightError("\n".join(msg))
    return rows


def fetch_provenance():
    """DATA_DIR/fetch_provenance.json written by notebooks/fetch_data.py: {relative path: {status, sha256, note}}."""
    p = os.path.join(LAYOUT["data"], "fetch_provenance.json")
    if not os.path.isfile(p):
        return {}
    import json
    with open(p) as f:
        return json.load(f).get("files", {})


def materiale_status(package_dir, want=SHIPPED_STONE_RULE):
    """Which stone rule a cache REBUILD in this session uses.

    want: 'hybrid' (default, the rule of the full audited run: Nurnet's data (site building stone) at SA_REL, copied
    from data/nurnet/ by fetch_data.py: recorded stone where known, else stones7) | 'stones7' (every site uses the
    nearest outcrop of the 7 permitted classes; no per-site input) | 'auto' (hybrid if that file is present, else stones7).
    'hybrid' without the file raises. Only preprocess.py (rebuilding the cache) reads that file; model runs never do.
    """
    if want not in ("stones7", "hybrid", "auto"):
        raise ValueError(f"STONE_RULE must be 'stones7', 'hybrid' or 'auto', not {want!r}")
    p = resolve(SA_REL)
    present = os.path.isfile(p)
    if want == "stones7":
        print(f"STONE RULE = stones7 (nearest outcrop of the 7 permitted classes for every site; not the rule of the "
              "full audited run).\nNo per-site building-stone file is used.")
        return "stones7"
    if present:
        with open(p, newline="", encoding="utf-8") as f:
            head = next(csv.reader(f))
        miss = [c for c in SA_COLUMNS if c not in head]
        if miss:
            raise PreflightError(f"{SA_REL} is present but lacks column(s) {miss}; it needs {SA_COLUMNS} "
                                 f"(codice = Nurnet UID, sa_materiale = recorded building stone). Found: {head[:10]}")
    if want == "hybrid" and not present:
        raise PreflightError(f"STONE_RULE = 'hybrid' needs {SA_REL} (columns {SA_COLUMNS}): Nurnet's data (site "
                             "building stone), included as data/nurnet/nurnet_site_building_stone.csv: run "
                             "fetch_data.py (02_inputs, section 0) to copy it there, or use STONE_RULE = 'stones7'.")
    rule = "hybrid" if present else "stones7"
    print("*" * 100)
    if rule == "hybrid":
        print(f"STONE RULE = hybrid (per-site building-stone file found: {p}, columns OK).\n"
              "A cache rebuilt with it differs from a stones7 cache by design.")
    else:
        print(f"STONE RULE = stones7. No per-site building-stone file at {SA_REL}.")
    print("*" * 100)
    return rule


# --------------------------------------------------------------------------- work folder + config
def _check_code(package_dir):
    """The code must be byte-identical to the repository's code/ (manifest group 'code')."""
    bad = [r["path"] for r in read_manifest() if r["group"] == "code" and
           (not os.path.isfile(resolve(r["path"])) or sha256(resolve(r["path"])) != r["sha256"])]
    if bad:
        raise PreflightError("code/ differs from the repository version (notebooks/inputs_manifest.csv, group 'code'): "
                             + ", ".join(bad[:10]) + ("..." if len(bad) > 10 else "") +
                             ". Check out code/ again; do not edit it (copy it elsewhere to experiment).")


def make_workdir(package_dir, work_dir, stone_rule=SHIPPED_STONE_RULE, cache="prebuilt", fresh_code=True,
                 check_code=True):
    """Copy code/ (verified) and the prebuilt cache to WORK_DIR, write WORK_DIR/config.yaml. Returns its path.

    cache: 'prebuilt' (copy the derived-input cache LAYOUT['cache'], without cost_mu/) or 'empty' (rebuild in 02).
    The config is LAYOUT['config'] (default config/config_full_audited.yaml) with only four lines changed:
    data_dir, cache_dir, output_dir, stone_rule
    (materiale.file stays relative to data_dir). No model parameter is touched. It is written to WORK_DIR/config.yaml
    and over the work copy WORK_DIR/code/config.yaml (never over the repository's code/).
    check_code=False is for the maintainer only (building the cache before the manifest exists).
    """
    if check_code:
        _check_code(package_dir)
    os.makedirs(work_dir, exist_ok=True)
    code = os.path.join(work_dir, "code")
    if fresh_code and os.path.isdir(code):
        shutil.rmtree(code)
    if not os.path.isdir(code):
        shutil.copytree(os.path.join(package_dir, "code"), code)
    cdir = os.path.join(work_dir, "cache")
    if cache == "prebuilt":
        src = LAYOUT["cache"]
        for dp, dn, fn in os.walk(src):
            rel = os.path.relpath(dp, src)
            if rel.split(os.sep)[0] == "cost_mu":         # 657 MB, only for rebuilding: linked, not copied
                continue
            os.makedirs(os.path.join(cdir, rel), exist_ok=True)
            for f in fn:
                d = os.path.join(cdir, rel, f)
                if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(os.path.join(dp, f)):
                    shutil.copy2(os.path.join(dp, f), d)
        if os.path.isdir(os.path.join(src, "cost_mu")) and not os.path.exists(os.path.join(cdir, "cost_mu")):
            os.symlink(os.path.join(src, "cost_mu"), os.path.join(cdir, "cost_mu"))
    os.makedirs(cdir, exist_ok=True)
    out = os.path.join(work_dir, "output")
    os.makedirs(out, exist_ok=True)
    inputs = os.path.abspath(LAYOUT["data"])
    lines, seen = [], set()
    with open(LAYOUT["config"]) as f:
        for ln in f:
            if ln.startswith("data_dir:") and "data_dir" not in seen:
                ln = f"data_dir: {inputs}\n"; seen.add("data_dir")
            elif ln.startswith("  cache_dir:") and "cache_dir" not in seen:
                ln = f"  cache_dir: {os.path.abspath(cdir)}\n"; seen.add("cache_dir")
            elif ln.startswith("  output_dir:") and "output_dir" not in seen:
                ln = f"  output_dir: {os.path.abspath(out)}\n"; seen.add("output_dir")
            elif ln.startswith("stone_rule:") and "stone_rule" not in seen:
                ln = f"stone_rule: {stone_rule}            # set by the notebook config cell\n"; seen.add("stone_rule")
            lines.append(ln)
    assert seen == {"data_dir", "cache_dir", "output_dir", "stone_rule"}, f"config rewrite failed: {seen}"
    cfg = os.path.join(work_dir, "config.yaml")
    # also as WORK_DIR/code/config.yaml: some analysis tools read the config next to the code (tools/centrality.py)
    for p in (cfg, os.path.join(code, "config.yaml")):
        with open(p, "w") as f:
            f.writelines(lines)
    print(f"work folder ready: {work_dir}\n  config {cfg}\n  data_dir {inputs}\n  cache {cdir} ({cache})\n"
          f"  stone_rule {stone_rule}")
    return cfg


# --------------------------------------------------------------------------- running
def _env():
    e = dict(os.environ)
    e.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    e.setdefault("OMPI_MCA_rmaps_base_oversubscribe", "1")
    return e


def sh(cmd, cwd, log=None, lock=None):
    """Run a command list, stream its output, raise on failure. lock: optional flock file (shared machines)."""
    if lock:
        cmd = ["flock", lock] + cmd
    print("$", " ".join(shlex.quote(c) for c in cmd), flush=True)
    t0 = time.time()
    with subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env()) as p:
        if log:
            os.makedirs(os.path.dirname(os.path.abspath(log)), exist_ok=True)
        lf = open(log, "a") if log else None
        for line in p.stdout:
            sys.stdout.write(line)
            if lf:
                lf.write(line)
        rc = p.wait()
        if lf:
            lf.close()
    print(f"[exit {rc}, {time.time() - t0:.0f} s]", flush=True)
    if rc != 0:
        raise RuntimeError(f"command failed (exit {rc}): {' '.join(cmd)}")


def mpirun(work_dir, ranks, args, log=None, lock=None, python=sys.executable):
    """mpirun -n RANKS python model.py WORK_DIR/config.yaml ARGS (from WORK_DIR/code)."""
    cmd = ["mpirun", "--allow-run-as-root", "--oversubscribe", "-n", str(ranks), python, "model.py",
           os.path.join(work_dir, "config.yaml")] + list(args)
    sh(cmd, cwd=os.path.join(work_dir, "code"), log=log, lock=lock)


def py(work_dir, script_args, log=None, lock=None, python=sys.executable):
    """python SCRIPT ARGS from WORK_DIR/code ('{cfg}' in ARGS is replaced by WORK_DIR/config.yaml)."""
    cfg = os.path.join(work_dir, "config.yaml")
    sh([python] + [a.replace("{cfg}", cfg) for a in script_args], cwd=os.path.join(work_dir, "code"), log=log, lock=lock)


def sites(work_dir, which):
    """Site selection -> list of model.py arguments. which: 'all', a file in code/ (e.g. sites300_real.txt), an int N
    (first N sites of the haul table), or a comma list of UIDs."""
    if which in (None, "all"):
        return []
    if isinstance(which, int):
        return ["--first-n", str(which)]
    p = os.path.join(work_dir, "code", which)
    if os.path.isfile(p):
        return ["--sites", open(p).read().strip()]
    return ["--sites", which]


def run_reference(work_dir, dest, ranks=2, lock=None, fresh=True):
    """Run the reference subset into DEST/{out,parts}. Same command lines as the maintainer used."""
    out, parts = os.path.join(dest, "out"), os.path.join(dest, "parts")
    if fresh:
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    S = sites(work_dir, REF_SITES_FILE)
    for name, a in REF_RUNS:
        # alliance runs take --out as a ROOT and write ROOT/<name>/; model.py runs write into --out itself
        o = out if "--alliance" in a else os.path.join(out, name)
        mpirun(work_dir, ranks, S + ["--seeds", REF_SEEDS, "--no-shapefile", "--fresh",
                                    "--out", o, "--parts-dir", parts] + a,
               log=os.path.join(dest, "run.log"), lock=lock)
    return dest


# --------------------------------------------------------------------------- fingerprints + comparison
def _rows_digest(paths):
    """Order-independent digest of CSV rows spread over several files (one header): sorted data lines."""
    header, lines = None, []
    for p in paths:
        with open(p, newline="") as f:
            txt = f.read().splitlines()
        if not txt:
            continue
        if header is None:
            header = txt[0]
        assert txt[0] == header, f"header differs in {p}"
        lines += txt[1:]
    lines.sort()
    return sha256_bytes(("\n".join([header or ""] + lines) + "\n").encode()), len(lines)


def fingerprint(dest):
    """One row per comparable item of a reference run folder (DEST/out, DEST/parts).

    kind 'bytes'      : the file, byte for byte.
    kind 'gz_content' : a .gz file's decompressed bytes (gzip headers carry a timestamp / file name).
    kind 'rows'       : model.py part files seed_NNNN.rankRRRofKKK.csv: their names depend on the number of MPI
                        ranks, so all ranks of one seed are pooled and compared as the sorted set of CSV rows
                        (full precision, as written). Signature folder names (hash of all parameters + sites) are
                        part of the key, so a parameter change shows up as a missing/extra item.
    .done markers and logs are skipped.
    """
    rows = []
    for sub in ("out", "parts"):
        root = os.path.join(dest, sub)
        groups = {}
        for dp, dn, fn in os.walk(root):
            dn.sort()
            for f in sorted(fn):
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, dest).replace(os.sep, "/")
                if f.endswith(".done") or f.endswith(".log"):
                    continue
                if ".rank" in f and f.endswith(".csv"):
                    key = rel.split(".rank")[0] + ".rank*.csv"
                    groups.setdefault(key, []).append(p)
                elif f.endswith(".gz"):
                    with gzip.open(p, "rb") as g:
                        b = g.read()
                    rows.append({"item": rel, "kind": "gz_content", "sha256": sha256_bytes(b), "n": len(b)})
                else:
                    rows.append({"item": rel, "kind": "bytes", "sha256": sha256(p), "n": os.path.getsize(p)})
        for key, ps in sorted(groups.items()):
            d, n = _rows_digest(sorted(ps))
            rows.append({"item": key, "kind": "rows", "sha256": d, "n": n})
    return sorted(rows, key=lambda r: r["item"])


def write_fingerprint(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "kind", "sha256", "n"])
        w.writeheader()
        w.writerows(rows)


def compare_reference(new_dest, ref_csv):
    """Exact comparison of a fresh reference run with a reference_sha256.csv. Returns True only if every
    item matches and none is missing or extra. Prints a table of differences."""
    with open(ref_csv, newline="") as f:
        ref = {r["item"]: r for r in csv.DictReader(f)}
    new = {r["item"]: r for r in fingerprint(new_dest)}
    bad = []
    for k in sorted(set(ref) | set(new)):
        if k not in new:
            bad.append((k, "MISSING in new run"))
        elif k not in ref:
            bad.append((k, "EXTRA (not in reference)"))
        elif new[k]["sha256"] != ref[k]["sha256"] or str(new[k]["n"]) != str(ref[k]["n"]):
            bad.append((k, f"DIFFERS ({ref[k]['kind']}: ref n={ref[k]['n']}, new n={new[k]['n']})"))
    kinds = {}
    for r in ref.values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"reference items: {len(ref)} ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}); "
          f"new run items: {len(new)}; mismatches: {len(bad)}")
    for k, why in bad[:50]:
        print(f"  {why}: {k}")
    return not bad


def diff_hint(new_dest, ref_dir, item):
    """For a failing 'bytes'/'gz_content' item: first differing line between the new file and the reference copy."""
    a, b = os.path.join(new_dest, item), os.path.join(ref_dir, item)
    op = gzip.open if item.endswith(".gz") else open
    with op(a, "rt") as fa, op(b, "rt") as fb:
        for i, (x, y) in enumerate(zip(fa, fb)):
            if x != y:
                return f"line {i + 1}:\n  new: {x.rstrip()[:200]}\n  ref: {y.rstrip()[:200]}"
    return "no differing line in the common part (length differs)"


# --------------------------------------------------------------------------- environment report
PINNED = os.path.join(HERE, "requirements-colab.txt")


def check_versions(path=PINNED):
    """Compare installed package versions with the pins. Returns the list of mismatches."""
    from importlib import metadata
    bad = []
    for ln in open(path):
        ln = ln.split("#")[0].strip()
        if not ln or "==" not in ln:
            continue
        name, ver = ln.split("==")
        try:
            got = metadata.version(name)
        except metadata.PackageNotFoundError:
            got = None
        if got != ver:
            bad.append((name, ver, got))
    print(f"pinned packages: {sum(1 for l in open(path) if '==' in l.split('#')[0])}; mismatches: {len(bad)}")
    for n, v, g in bad:
        print(f"  {n}: pinned {v}, installed {g}")
    return bad


# --------------------------------------------------------------------------- installing (01, and the first cell of 02-04)
def in_colab():
    return "google.colab" in sys.modules or os.path.isdir("/content") and os.environ.get("COLAB_RELEASE_TAG")


def ensure_env(install=True, req=PINNED):
    """Make this Python match requirements-colab.txt. Installs OpenMPI (apt, Colab/Debian as root) and the pinned
    packages (pip) when something is missing or at another version. Returns 'ok' or 'restart' (packages changed
    while an old copy was already imported: restart the kernel / Colab session, then run the notebook again)."""
    bad = check_versions(req)
    if not shutil.which("mpirun") or not shutil.which("mpicc"):
        if not install:
            raise PreflightError("OpenMPI not found (mpirun / mpicc). Install it: apt-get install openmpi-bin libopenmpi-dev")
        if shutil.which("apt-get") and os.geteuid() == 0:
            sh(["apt-get", "-qq", "update"], cwd="/")
            sh(["apt-get", "-qq", "install", "-y", "openmpi-bin", "libopenmpi-dev"], cwd="/")
        else:
            raise PreflightError("OpenMPI (mpirun, mpicc) is missing and cannot be installed here: install it with your "
                                 "system package manager (Debian/Ubuntu: openmpi-bin libopenmpi-dev; macOS: brew install "
                                 "open-mpi; conda: conda install -c conda-forge openmpi mpi4py), then rerun.")
    if not bad:
        return "ok"
    if not install:
        raise PreflightError(f"{len(bad)} package(s) differ from requirements-colab.txt; set INSTALL = True or run 01_setup.")
    stale = sorted({n for n, _, _ in bad if n.replace("-", "_").lower() in {m.split(".")[0].lower() for m in sys.modules}})
    env = dict(os.environ, CC="mpicc", CXX="mpicxx", PIP_DISABLE_PIP_VERSION_CHECK="1")
    cmd = [sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir", "-r", req]
    print("$ CC=mpicc CXX=mpicxx", " ".join(cmd), flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(r.stdout[-4000:])
    print(f"[pip exit {r.returncode}, {time.time() - t0:.0f} s]")
    if r.returncode:
        raise RuntimeError("pip install failed (see above). On Colab: Runtime > Disconnect and delete runtime, then retry.")
    bad = check_versions(req)
    if bad:
        raise RuntimeError("after pip install some versions still differ (see above)")
    if stale:
        print(f"RESTART NEEDED: {', '.join(stale)} was already imported in this kernel at another version.\n"
              "Colab: Runtime > Restart session.  Jupyter: Kernel > Restart.  Then run this notebook again from the top.")
        return "restart"
    return "ok"


def mpi_report():
    out = subprocess.run(["mpirun", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    line = out.strip().splitlines()[0] if out.strip() else "?"
    if "Open MPI) 4." in line or "Open MPI) 3." in line:     # Docker/Colab: no CMA single-copy (avoids errno 1 noise)
        os.environ.setdefault("OMPI_MCA_btl_vader_single_copy_mechanism", "none")
    return line


# --------------------------------------------------------------------------- scenarios (03)
FAMILY_FLAG = {"coop": "--scenario", "lit": "--lit", "alliance": "--alliance", "pre": "--pre"}
FAMILY_DIR = {"coop": "scenarios", "lit": "scenarios_lit", "alliance": "scenarios_alliance", "pre": "scenarios_pre"}


def parse_scenario(spec):
    """'baseline' | 'coop:full' | 'lit:webster' | 'alliance:A5_full' | 'pre:P_G50_hub' -> (family, name)."""
    if spec == "baseline":
        return "baseline", None
    fam, _, name = spec.partition(":")
    if fam not in FAMILY_FLAG or not name:
        raise ValueError(f"bad scenario '{spec}': use baseline, coop:NAME, lit:NAME, alliance:NAME or pre:NAME")
    return fam, name


def list_scenarios(work_dir):
    """Names defined in config.yaml, per family (phased _P10/_P20/_P100 and _sea variants are built from these)."""
    import yaml
    cfg = yaml.safe_load(open(os.path.join(work_dir, "config.yaml")))
    return {"coop": list(cfg["scenarios"]["list"]), "lit": list(cfg["lit_scenarios"]["list"]),
            "alliance": list(cfg["alliance"]["list"]) + list(cfg.get("alliance_extra") or {}),
            "pre": "see code/pre_networks.py (P_none, P_G50_hub, P_G20_system_hub, ...; 'pre:all' = 56-cell grid)"}


def run_dirs(results_dir, label):
    """Per run label: <results>/<label>/runs (part files: resume) and the output folders, in the code's layout."""
    base = os.path.join(results_dir, label)
    return base, os.path.join(base, "runs")


def run_scenario(work_dir, results_dir, label, spec, sites_sel, seeds, ranks=2, resume=True, lock=None, extra=()):
    fam, name = parse_scenario(spec)
    base, parts = run_dirs(results_dir, label)
    out = os.path.join(base, "baseline") if fam == "baseline" else os.path.join(base, FAMILY_DIR[fam], name)
    # alliance / pre runs take --out as a ROOT and write ROOT/<name>/; model.py runs write into --out itself
    o = os.path.dirname(out) if fam in ("alliance", "pre") else out
    args = sites(work_dir, sites_sel) + ["--seeds", seeds, "--no-shapefile", "--out", o, "--parts-dir", parts]
    if fam != "baseline":
        args += [FAMILY_FLAG[fam], name]
    if not resume:
        args.append("--fresh")
    mpirun(work_dir, ranks, args + list(extra), log=os.path.join(base, "run.log"), lock=lock)
    return out


# --------------------------------------------------------------------------- analysis (04)
def island_table(base):
    """Island totals per scenario folder under BASE (any family): mean / min / max over seeds of the summed MH, and
    the median site build time (days)."""
    import pandas as pd
    rows = []
    for f in sorted(glob.glob(os.path.join(base, "**", "nuraghe_manhours_runs.csv.gz"), recursive=True)):
        d = pd.read_csv(f)
        isl = d.groupby("seed").mh_total.sum()
        name = os.path.relpath(os.path.dirname(f), base)
        rows.append({"scenario": name, "sites": d.UID.nunique(), "seeds": d.seed.nunique(),
                     "island_MH_mean": isl.mean(), "island_MH_min": isl.min(), "island_MH_max": isl.max(),
                     "site_MH_median": d.groupby("UID").mh_total.mean().median(),
                     "site_days_median": d.groupby("UID").days.mean().median() if "days" in d else float("nan")})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- audit (05_audit.ipynb)
AUDIT_SCENARIO = "MOST_REALISTIC_AUDITED_LIT_P10"      # the headline scenario of the full audited run
AUDIT_SITES_FILE = "sites300_real.txt"                  # 300 sites (code/sites300_real.txt)
AUDIT_SEEDS = "1-3"
AUDIT_REF = "reference_audit_sha256.csv"                # under OUTPUTS_DIR/reference/ (shipped with the results)


def _provenance_lists(repo):
    """From CODE_PROVENANCE.md: files expected to FAIL the run checksums (scrubbed, 'In CODE_SHA256SUMS' = yes) and
    the excluded items (expected to be missing)."""
    import re
    txt = open(os.path.join(repo, "CODE_PROVENANCE.md"), encoding="utf-8").read()
    changed, excluded = set(), []
    part = txt.split("## Changed files", 1)[-1].split("\n## ", 1)[0]
    for ln in part.splitlines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*(yes|no)\s*\|", ln)
        if m and m.group(2) == "yes":
            changed.add(m.group(1))
    part = txt.split("## Excluded from the repository", 1)[-1].split("\n## ", 1)[0]
    for ln in part.splitlines():
        if ln.startswith("|") and not ln.startswith("|---") and not ln.startswith("| Item"):
            item = ln.split("|")[1]
            excluded += [x for x in re.findall(r"`([^`]+)`", item) if "/" in x or x.endswith((".py", ".patch"))]
    return changed, excluded


def code_audit(repo):
    """Step (a): code/ against CODE_SHA256SUMS (the checksums of the run's frozen snapshot) and CODE_PROVENANCE.md.

    Every file listed in CODE_SHA256SUMS must be either byte-identical (OK), or scrubbed and listed as changed in
    CODE_PROVENANCE.md (FAILED, expected), or excluded and listed there (missing, expected). Anything else is an
    unexplained difference. Returns (table, unexplained)."""
    import pandas as pd
    changed, excluded = _provenance_lists(repo)
    rows = []
    for ln in open(os.path.join(repo, "CODE_SHA256SUMS")):
        ln = ln.strip()
        if not ln:
            continue
        h, rel = ln.split(None, 1)
        rel = rel.lstrip("*").removeprefix("./")
        p = os.path.join(repo, "code", rel)
        if not os.path.isfile(p):
            res = "missing"
            exp = any(rel == e or rel.startswith(e.rstrip("/") + "/") for e in excluded)
        else:
            res = "OK" if sha256(p) == h else "FAILED"
            exp = res == "OK" or rel in changed
        rows.append({"file": rel, "result": res, "explained": exp,
                     "why": {"OK": "byte-identical to the run", "FAILED": "scrubbed (CODE_PROVENANCE.md)" if exp else "NOT EXPLAINED",
                             "missing": "excluded (CODE_PROVENANCE.md)" if exp else "NOT EXPLAINED"}[res]})
    t = pd.DataFrame(rows)
    print(t.groupby(["result", "why"]).size().rename("files").to_string())
    bad = t[~t.explained]
    print(f"\n{len(t)} files in CODE_SHA256SUMS; unexplained differences: {len(bad)}")
    return t, bad


def config_audit(repo, config=None, base=AUDIT_SCENARIO):
    """Step (c): every value of param_audit/PARAM_TRACE.csv against the configuration.

    'MR:<key>' paths are read from the resolved headline scenario dict (the frozen code's alliance.scenario()),
    other paths from the YAML; several paths separated by ';' give a list. Values are compared as the JSON text
    of PARAM_TRACE.csv (truncated there to 200 characters). Rows whose path is '(code) ...' are not config keys."""
    import json
    import pandas as pd
    import yaml
    cfg = yaml.safe_load(open(config or os.path.join(repo, "config", "config_full_audited.yaml")))
    sys.path.insert(0, os.path.join(repo, "code"))
    import alliance                                       # frozen code: resolves the scenario dict
    mr = alliance.scenario(cfg, base)

    def get(path):
        d = mr if path.startswith("MR:") else cfg
        for k in path.removeprefix("MR:").split("."):
            if not isinstance(d, dict) or k not in d:
                return "(absent)"
            d = d[k]
        return d

    def short(v, n=200):
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        return s if len(s) <= n else s[: n - 3] + "..."

    rows = []
    with open(os.path.join(repo, "param_audit", "PARAM_TRACE.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p = r["config_path"]
            if p.startswith("(code)"):
                rows.append({"id": r["id"], "config_path": p, "config": "(code)", "trace": r["value_in_config_full_audited"],
                             "same": None, "audited = config (trace)": r["value_matches_audit"]})
                continue
            vals = [get(x.strip()) for x in p.split(";")]
            s = short(vals[0] if len(vals) == 1 else vals)
            rows.append({"id": r["id"], "config_path": p, "config": s, "trace": r["value_in_config_full_audited"],
                         "same": s == r["value_in_config_full_audited"],
                         "audited = config (trace)": r["value_matches_audit"]})
    t = pd.DataFrame(rows)
    n = t.same.notna().sum()
    print(f"{len(t)} audited parameters; {n} config keys checked: {int((t.same == True).sum())} equal, "  # noqa: E712
          f"{int((t.same == False).sum())} differ; {len(t) - n} code-level rows (not config keys); "  # noqa: E712
          f"PARAM_TRACE 'value_matches_audit' = yes for {int((t['audited = config (trace)'] == 'yes').sum())}")
    return t


def run_audit_subset(work_dir, dest, ranks=2, lock=None, scenario=AUDIT_SCENARIO, sites_file=AUDIT_SITES_FILE,
                     seeds=AUDIT_SEEDS):
    """Step (d): the headline scenario on the fixed 300-site subset, seeds 1-3, from scratch, into DEST/{out,parts}."""
    out, parts = os.path.join(dest, "out"), os.path.join(dest, "parts")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    mpirun(work_dir, ranks, sites(work_dir, sites_file) + ["--seeds", seeds, "--no-shapefile", "--fresh", "--out", out,
                                                         "--parts-dir", parts, "--alliance", scenario],
           log=os.path.join(dest, "run.log"), lock=lock)
    return dest


SUMMARY_PER_SEED = "per_seed_full_audited.csv"    # label, seed, island_MH, years, site_years_mean, transport_share, tonnes
SUMMARY_TABLE = "summary_full_audited.csv"        # label, n_seeds, years_mean/min/max, mh_M_mean/min/max, ...
SEASON_DAYS = 90.0


def per_seed_from_parts(parts_dir, label):
    """Per-seed island totals from alliance part files seed_NNNN.sites.csv.gz (the rule of tools/v12_summary.py):
    island MH = sum of mh_total over the sites; island years = (max finish_day + 1) / 90."""
    import pandas as pd
    rows = []
    for f in sorted(glob.glob(os.path.join(parts_dir, "seed_*.sites.csv.gz"))):
        s = pd.read_csv(f)
        rows.append({"label": label, "seed": int(os.path.basename(f)[5:9]), "island_MH": s.mh_total.sum(),
                     "years": (s.finish_day.max() + 1) / SEASON_DAYS, "site_years_mean": (s.days / SEASON_DAYS).mean(),
                     "transport_share": s.mh_transport.sum() / s.mh_total.sum(), "tonnes": s.tonnes.sum()})
    return pd.DataFrame(rows)


def headline_from_summaries(summary_dir, label=AUDIT_SCENARIO, parts_dir=None, rtol=1e-6):
    """Step (e): island years and man-hours of LABEL recomputed from the shipped per-seed table (and, when the part
    files are at hand, the per-seed table recomputed from them), compared with the shipped summary table."""
    import pandas as pd
    ps_path, sm_path = os.path.join(summary_dir, SUMMARY_PER_SEED), os.path.join(summary_dir, SUMMARY_TABLE)
    for p in (ps_path, sm_path):
        if not os.path.isfile(p):
            print(f"NOT YET AVAILABLE: {p} (shipped with the results package; see outputs/summary/README.md)")
            return None
    ps = pd.read_csv(ps_path)
    ps = ps[ps.label == label].sort_values("seed")
    sm = pd.read_csv(sm_path).set_index("label")
    re_ = {"n_seeds": len(ps), "years_mean": ps.years.mean(), "years_min": ps.years.min(), "years_max": ps.years.max(),
           "mh_M_mean": ps.island_MH.mean() / 1e6, "mh_M_min": ps.island_MH.min() / 1e6,
           "mh_M_max": ps.island_MH.max() / 1e6}
    rows = []
    for k, v in re_.items():
        sv = sm.loc[label, k] if k in sm.columns else float("nan")
        rows.append({"quantity": k, "recomputed": v, "shipped": sv,
                     "equal": bool(abs(float(v) - float(sv)) <= rtol * max(1.0, abs(float(sv))))})
    t = pd.DataFrame(rows)
    if parts_dir:
        pp = per_seed_from_parts(parts_dir, label).sort_values("seed")
        same = len(pp) == len(ps) and all(abs(a - b) <= rtol * abs(b) for a, b in zip(pp.island_MH, ps.island_MH)) \
            and all(abs(a - b) <= rtol * abs(b) for a, b in zip(pp.years, ps.years))
        print(f"per-seed table recomputed from {len(pp)} part files in {parts_dir}: {'equal' if same else 'DIFFERENT'}")
    print(f"{label}: island years {re_['years_mean']:.1f} (min {re_['years_min']:.1f}, max {re_['years_max']:.1f}); "
          f"island man-hours {re_['mh_M_mean']:.1f} M (min {re_['mh_M_min']:.1f}, max {re_['mh_M_max']:.1f}) over "
          f"{re_['n_seeds']} seeds")
    return t
