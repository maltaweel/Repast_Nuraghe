"""Download every PUBLIC raw input of the model from its official source into DATA_DIR, rebuild the files the model
reads, and check them against notebooks/inputs_manifest.csv (the SHA-256 of the copies used for the runs).

    python notebooks/fetch_data.py                      # everything public, into REPO/data (the default DATA_DIR)
    python notebooks/fetch_data.py --data-dir /path/to/data [--only soils,rivers,lithology,dem,costsurface]
    python notebooks/fetch_data.py --no-rasters          # download only; skip the DEM mosaic and the cost/slope rasters
    python notebooks/fetch_data.py --check-only          # only report what is present and whether it matches
    python notebooks/fetch_data.py --derived-url URL     # also download + unpack a prebuilt derived-input pack
    python notebooks/fetch_data.py --rebuild-derived     # rebuild every derived input from the raw inputs (long)

From a notebook: `import fetch_data; fetch_data.fetch(DATA_DIR, ...)` (02_inputs.ipynb, section 0).
Step-by-step manual instructions for the same files: notebooks/HOW_TO_USE.md ("Linking the data yourself").

What each input needs (details: HOW_TO_USE.md and data/README.md)

| input (DATA_DIR/...)                    | official source                       | processing                    | SHA-256 = run copy?  |
|-----------------------------------------|---------------------------------------|-------------------------------|----------------------|
| sites/nurnet_nuraghi.*                  | Nurnet's data, in data/nurnet/        | copied to the expected names  | yes                  |
| stone/nid_materiale_prod.csv            | Nurnet's data, in data/nurnet/        | copied (nurnet_site_building_stone.csv) | yes        |
| soils/soils250k.geojson                 | AGRIS WFS (GeoServer)                 | GeoServer timeStamp -> run's  | yes                  |
| water/sardinia_rivers_25832.*           | RAS PPR06 fiumiTorrenti_ARC.zip       | tools_extra/build_rivers.py   | .prj/.cpg yes; .shp/.shx/.dbf no (5 mm, row order) |
| geology/sardinia_lithology_25832.*      | ARPAS carta_litologica_2019.zip       | tools_extra/build_lithology.py | .prj/.cpg yes; .shp/.shx/.dbf no (5 mm, row order) |
| dem/sardinia_dem_GLO30_25832.tif        | Copernicus GLO-30, 8 tiles (AWS)      | tools_extra/build_dem.py      | no with the public mask (yes with the run's mask) |
| costsurface/*_mu03_*_int.tif, *_slope_* | from the DEM                          | code/tools/build_cost_mu.py, tools_extra/build_slope.py | only if the DEM is identical |

Every download is streamed to disk (DOWNLOADS, default DATA_DIR/_downloads), checked against the SHA-256 observed
on 2 November 2026 where the provider serves a fixed file, and kept so that a rerun downloads nothing. The result of
every input is written to DATA_DIR/fetch_provenance.json; notebooks/repro.py (preflight) reads it, so a file that
was rebuilt from the official source and is not byte-comparable is reported as such instead of as "wrong".

Standard library only for downloading and checking; the rebuild steps call tools_extra/*.py and code/tools/*.py
with this Python (they need numpy, pyproj, pyogrio, geopandas, rasterio: requirements-colab.txt).
Memory: the vector steps stay below ~400 MB; the DEM mosaic needs about 1.5 GB, the cost raster about 1 GB.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MANIFEST = os.path.join(HERE, "inputs_manifest.csv")
PROVENANCE = "fetch_provenance.json"

# Prebuilt derived-input pack (the cached derived inputs of the full audited run). Placeholder until the results
# package is public: set it here, with --derived-url, or with the environment variable NURAGHE_DERIVED_URL.
DERIVED_URL = os.environ.get("NURAGHE_DERIVED_URL") or None
DERIVED_SHA256 = None            # to be filled together with DERIVED_URL

# --------------------------------------------------------------------------------------------------- Nurnet files
# Nurnet's data, published in this repository (data/nurnet/); copied to the names the configuration expects.
NURNET_DIR = os.path.join(REPO, "data", "nurnet")
NURNET_COPIES = [(f"nurnet_nuraghi{e}", f"sites/nurnet_nuraghi{e}") for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")] + \
                [("nurnet_site_building_stone.csv", "stone/nid_materiale_prod.csv")]
NURNET_NOTE = (
    "The site list (nurnet_nuraghi.shp: 7,167 nuraghi with tower counts) and the per-site building stone file are "
    "Nurnet's data; the files are included in data/nurnet/ (nurnet_nuraghi.{shp,shx,dbf,prj,cpg}, "
    "nurnet_site_building_stone.csv). For the latest version and source information contact Nurnet at "
    "nurnet.presidente@gmail.com.")

# --------------------------------------------------------------------------------------------------- sources
# SHA-256 / size of the files the providers served on 2 November 2026 (checked when downloaded; a difference means
# the provider changed the file and is reported, the result is then checked against the manifest as usual).
DEM_TILES = {
    "Copernicus_DSM_COG_10_N38_00_E008_00_DEM": (2041115, "75af652dfb44c0394d1439bf646ae701728de734ef6fb034ae7d7166c4b5847c"),
    "Copernicus_DSM_COG_10_N38_00_E009_00_DEM": (109701, "421e3120ae463aa6132670c0000d5b6cb5fd1bf839d0181ff60d660ab44395c3"),
    "Copernicus_DSM_COG_10_N39_00_E008_00_DEM": (27330793, "099700e54d5b9dabb81bad3e24190c5c8ac1f3f4d8382e0daada5cf05d19a9d0"),
    "Copernicus_DSM_COG_10_N39_00_E009_00_DEM": (25048790, "c17084e7fc4339c56eab315c0383bc2ee9291b6768cea94674c021c3d8c2fad2"),
    "Copernicus_DSM_COG_10_N40_00_E008_00_DEM": (27572645, "989c392dd889529b07343056713d4b51241e8c32463d0591528863e293fad843"),
    "Copernicus_DSM_COG_10_N40_00_E009_00_DEM": (32279531, "05dff4c868a0d1897b432fa7d60a1d08836781e85f9f0ff0e65717ce0f095876"),
    "Copernicus_DSM_COG_10_N41_00_E008_00_DEM": (6685206, "2836ae44fddd0467b3b6a0d7dd41f180749c45d807892c2a054f33ace7da3b8d"),
    "Copernicus_DSM_COG_10_N41_00_E009_00_DEM": (15446420, "ef3671be263e6e0ee4bbc1a625de47032e92a2b281cd0be81cb3c4a7d6b56335"),
}
DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"
LITHOLOGY_ZIP = ("https://webgis.regione.sardegna.it/scaricocartografiaETL/arpas/carta_litologica_2019.zip",
                 243185200, "547f64c41b4ee7268b35c45e1478a651c86fe13ba29dd0fcabbb796c6b681aa6")
RIVERS_ZIP = ("https://webgis.regione.sardegna.it/scaricocartografiaETL/ppr/fiumiTorrenti_ARC.zip",
              10364839, "daf6e16689d7a41d672387f7b6711c5a60e2b16b124faf9448e422ef3393c063")
REGION_ZIP = ("https://webgis.regione.sardegna.it/scaricocartografiaETL/limitiAmministrativi/limiteAmministrRegionale/"
              "limiteAmministrReg_CTR.zip", 1128613, "e26e03269e1862e73a0fce65d3a6ab46cc0edbd65d007aa11c901978c6caafea")
SOILS_WFS = ("https://geoserver.sardegnaportalesuolo.it/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature"
             "&typeNames=Agris:carta_dei_suoli_sardegna_scala_250000&outputFormat=application/json&srsName=EPSG:4326")
# GeoServer writes the time of the request into the GeoJSON ("timeStamp"); the run's copy was fetched at this time.
# Writing it back is the only change to the downloaded bytes; everything else must match byte for byte.
SOILS_TIMESTAMP_OF_RUN_COPY = "2026-10-20T16:31:34.004Z"

SHP = (".shp", ".shx", ".dbf", ".prj", ".cpg")
INPUTS = ("sites", "stone", "soils", "rivers", "lithology", "dem", "costsurface")

WHY = {
    "rivers": "rebuilt from the official RAS file; the run's copy was exported from the same layer held in a project "
              "database: same 41,877 segments, IDs and vertices, coordinates within 5 mm (another datum "
              "transformation at import), rows in database order. Not byte-comparable (.prj/.cpg are).",
    "lithology": "rebuilt from the official ARPAS file; the run's copy was exported from the same map held in a "
                 "project database: same 47,780 polygons, IDs, map units and vertex counts, coordinates within 5 mm, "
                 "rows in database order. Not byte-comparable (.prj/.cpg are).",
    "dem_region": "rebuilt from the official GLO-30 tiles with the run's recipe, but with the public regional boundary "
                  "as land mask (the run used the regional river catchments as held in a project database, not "
                  "public); grid identical, mask differs in about 75 km2 of mostly coastal sea cells. Not "
                  "byte-comparable.",
    "costsurface": "computed from the DEM; byte-comparable only when the DEM is byte-identical to the run's copy.",
}


# --------------------------------------------------------------------------------------------------- helpers
def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def manifest():
    with open(MANIFEST, newline="") as f:
        return {r["path"]: r for r in csv.DictReader(f)}


def log(msg):
    print(msg, flush=True)


def download(url, dest, size=None, sha=None, tries=3, timeout=120):
    """Stream URL to DEST (via DEST.part). Skips the download when DEST exists with the expected SHA-256 (or size).
    Returns (sha256, matches_expected or None)."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    if os.path.isfile(dest) and (sha or size):
        got = sha256(dest)
        if (sha and got == sha) or (not sha and size and os.path.getsize(dest) == size):
            log(f"  have {os.path.basename(dest)} ({os.path.getsize(dest):,d} B, SHA-256 OK)")
            return got, True if sha else None
    last = None
    for k in range(tries):
        try:
            t0 = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": "Repast_Nuraghe-fetch/1.0"})
            h = hashlib.sha256()
            n = 0
            with urllib.request.urlopen(req, timeout=timeout) as r, open(dest + ".part", "wb") as f:
                for b in iter(lambda: r.read(1 << 20), b""):
                    f.write(b); h.update(b); n += len(b)
            os.replace(dest + ".part", dest)
            got = h.hexdigest()
            ok = None if sha is None else (got == sha)
            log(f"  got  {os.path.basename(dest)} ({n:,d} B, {time.time() - t0:.0f} s)"
                + ("" if ok is None else ("  SHA-256 OK" if ok else "  SHA-256 DIFFERS from the file served on 2 Nov 2026")))
            return got, ok
        except Exception as e:                                   # network hiccup: retry
            last = e
            log(f"  download failed ({e}); retry {k + 1}/{tries}")
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"could not download {url}: {last}")


def run(cmd, cwd=REPO):
    log("  $ " + " ".join(cmd))
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    for ln in r.stdout.splitlines()[-25:]:
        log("    " + ln)
    log(f"  [exit {r.returncode}, {time.time() - t0:.0f} s]")
    if r.returncode:
        raise RuntimeError("command failed: " + " ".join(cmd))


def check_files(data_dir, rels, status_if_differs=None, why=None):
    """Compare DATA_DIR/<rel> with the manifest. Returns rows {path, status, sha256, expected, note}."""
    man = manifest()
    rows = []
    for rel in rels:
        key = "data/" + rel
        exp = man.get(key, {}).get("sha256") or None
        p = os.path.join(data_dir, rel)
        if not os.path.isfile(p):
            rows.append(dict(path=rel, status="missing", sha256=None, expected=exp, note=""))
            continue
        got = sha256(p)
        if exp is None:
            st, note = "present (no hash recorded)", ""
        elif got == exp:
            st, note = "identical", "SHA-256 = inputs_manifest.csv"
        else:
            st, note = (status_if_differs or "differs"), (why or "SHA-256 differs from inputs_manifest.csv")
        rows.append(dict(path=rel, status=st, sha256=got, expected=exp, note=note))
    return rows


def write_provenance(data_dir, rows, extra=None):
    p = os.path.join(data_dir, PROVENANCE)
    old = {}
    if os.path.isfile(p):
        with open(p) as f:
            old = json.load(f)
    files = old.get("files", {})
    for r in rows:
        files[r["path"]] = {k: r[k] for k in ("status", "sha256", "expected", "note", "source") if k in r}
    out = {"written": datetime.datetime.now().isoformat(timespec="seconds"), "files": files}
    out.update(old.get("meta", {}) and {"meta": old["meta"]} or {})
    if extra:
        out.setdefault("meta", {}).update(extra)
    with open(p, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)


def unzip(zp, dest):
    with zipfile.ZipFile(zp) as z:
        z.extractall(dest)


# The configuration of the v17 runs (the v17 code runs the v16_final configs; = config/config_full_audited.yaml +
# quarry.near_site_fixed_face_m 1000 + transport.min_haul_flatm 15, which the sea tables apply). Same as repro.RUN_CONFIG.
RUN_CONFIG = os.path.join("config", "v16_final", "config_full_audited.yaml")


def write_config(data_dir, cache_dir, out, stone_rule=None):
    """A copy of RUN_CONFIG with data_dir / cache_dir (/ stone_rule) set (same rule as repro.py)."""
    lines, seen = [], set()
    with open(os.path.join(REPO, RUN_CONFIG)) as f:
        for ln in f:
            if ln.startswith("data_dir:") and "data_dir" not in seen:
                ln = f"data_dir: {os.path.abspath(data_dir)}\n"; seen.add("data_dir")
            elif ln.startswith("  cache_dir:") and "cache_dir" not in seen:
                ln = f"  cache_dir: {os.path.abspath(cache_dir)}\n"; seen.add("cache_dir")
            elif ln.startswith("  output_dir:") and "output_dir" not in seen:
                ln = f"  output_dir: {os.path.abspath(os.path.join(cache_dir, '..', 'output'))}\n"; seen.add("output_dir")
            elif stone_rule and ln.startswith("stone_rule:") and "stone_rule" not in seen:
                ln = f"stone_rule: {stone_rule}\n"; seen.add("stone_rule")
            lines.append(ln)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        f.writelines(lines)
    return out


# --------------------------------------------------------------------------------------------------- per input
def _copy_nurnet(data_dir, pairs):
    rows = []
    for src_name, rel in pairs:
        src, dst = os.path.join(NURNET_DIR, src_name), os.path.join(data_dir, rel)
        if os.path.abspath(src) != os.path.abspath(dst) and os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not (os.path.isfile(dst) and sha256(dst) == sha256(src)):
                shutil.copy2(src, dst)
        r = check_files(data_dir, [rel], status_if_differs="differs",
                        why="not the copy used for the runs: restore it from data/nurnet/")[0]
        r["source"] = f"Nurnet's data, data/nurnet/{src_name}"
        rows.append(r)
    if any(r["status"] == "missing" for r in rows):
        log(f"  {NURNET_DIR} is incomplete (a partial clone?). " + NURNET_NOTE)
    return rows


def do_sites(data_dir, dl, **_):
    return _copy_nurnet(data_dir, NURNET_COPIES[:5])


def do_stone(data_dir, dl, **_):
    return _copy_nurnet(data_dir, NURNET_COPIES[5:])


def do_soils(data_dir, dl, **_):
    rel = "soils/soils250k.geojson"
    raw = os.path.join(dl, "soils250k_wfs.geojson")
    download(SOILS_WFS, raw, timeout=300)
    b = open(raw, "rb").read()
    tail = b[-400:]
    m = re.search(rb'"timeStamp":"[^"]*"', tail)
    if m:
        new_tail = tail[:m.start()] + b'"timeStamp":"' + SOILS_TIMESTAMP_OF_RUN_COPY.encode() + b'"' + tail[m.end():]
        b = b[:-400] + new_tail
    os.makedirs(os.path.join(data_dir, "soils"), exist_ok=True)
    with open(os.path.join(data_dir, rel), "wb") as f:
        f.write(b)
    rows = check_files(data_dir, [rel], status_if_differs="differs",
                       why="the provider's layer changed since 20 Oct 2026 (35 units expected); compare the features")
    for r in rows:
        r["source"] = "AGRIS WFS " + SOILS_WFS
        if r["status"] == "identical":
            r["note"] = "identical after writing back the GeoServer timeStamp of the run's copy"
    return rows


def do_rivers(data_dir, dl, **_):
    zp = os.path.join(dl, "fiumiTorrenti_ARC.zip")
    download(RIVERS_ZIP[0], zp, RIVERS_ZIP[1], RIVERS_ZIP[2])
    out = os.path.join(data_dir, "water", "sardinia_rivers_25832.shp")
    run([sys.executable, os.path.join(REPO, "tools_extra", "build_rivers.py"), zp, out])
    rows = check_files(data_dir, [f"water/sardinia_rivers_25832{e}" for e in SHP], "rebuilt (not byte-comparable)",
                       WHY["rivers"])
    for r in rows:
        r["source"] = RIVERS_ZIP[0]
    return rows


def do_lithology(data_dir, dl, **_):
    zp = os.path.join(dl, "carta_litologica_2019.zip")
    download(LITHOLOGY_ZIP[0], zp, LITHOLOGY_ZIP[1], LITHOLOGY_ZIP[2], timeout=300)
    out = os.path.join(data_dir, "geology", "sardinia_lithology_25832.shp")
    run([sys.executable, os.path.join(REPO, "tools_extra", "build_lithology.py"), zp, out,
         "--classes", os.path.join(REPO, "data", "lithology_STONE_classes.csv")])
    rows = check_files(data_dir, [f"geology/sardinia_lithology_25832{e}" for e in SHP],
                       "rebuilt (not byte-comparable)", WHY["lithology"])
    for r in rows:
        r["source"] = LITHOLOGY_ZIP[0]
    return rows


def do_dem(data_dir, dl, rasters=True, basins=None, **_):
    tiles = os.path.join(dl, "dem_tiles")
    for n, (size, sha) in DEM_TILES.items():
        download(DEM_URL.format(n=n), os.path.join(tiles, n + ".tif"), size, sha, timeout=300)
    rel = "dem/sardinia_dem_GLO30_25832.tif"
    if not rasters:
        log("  rasters off: the 8 tiles are downloaded; build the DEM with tools_extra/build_dem.py (HOW_TO_USE.md)")
        return check_files(data_dir, [rel])
    if basins:
        mask = ["basins", basins]
        why = "rebuilt with the run's recipe and mask; should be byte-identical (same GDAL / rasterio)"
    else:
        zp = os.path.join(dl, "limiteAmministrReg_CTR.zip")
        download(REGION_ZIP[0], zp, REGION_ZIP[1], REGION_ZIP[2])
        unzip(zp, os.path.join(dl, "region"))
        mask = ["region", os.path.join(dl, "region", "limiteAmministrRegionale_CTR.shp")]
        why = WHY["dem_region"]
    run([sys.executable, os.path.join(REPO, "tools_extra", "build_dem.py"), tiles, os.path.join(data_dir, rel),
         "--mask", *mask, "--workdir", dl])
    rows = check_files(data_dir, [rel], "rebuilt (not byte-comparable)" if not basins else "differs", why)
    for r in rows:
        r["source"] = "Copernicus DEM GLO-30, " + DEM_URL.format(n="<tile>")
    return rows


def do_costsurface(data_dir, dl, rasters=True, **_):
    rels = ["costsurface/sardinia_drag_cost_8dir_mu03_25832_int.tif", "costsurface/sardinia_slope_deg_25832.tif"]
    dem = os.path.join(data_dir, "dem", "sardinia_dem_GLO30_25832.tif")
    if not rasters or not os.path.isfile(dem):
        log("  skipped (rasters off or no DEM yet)")
        return check_files(data_dir, rels)
    os.makedirs(os.path.join(data_dir, "costsurface"), exist_ok=True)
    cfg = write_config(data_dir, os.path.join(dl, "cache"), os.path.join(dl, "config_fetch.yaml"))
    run([sys.executable, "tools/build_cost_mu.py", cfg, "0.3", os.path.join(data_dir, rels[0])], cwd=os.path.join(REPO, "code"))
    run([sys.executable, os.path.join(REPO, "tools_extra", "build_slope.py"), dem, os.path.join(data_dir, rels[1])])
    dem_ok = manifest().get("data/" + "dem/sardinia_dem_GLO30_25832.tif", {}).get("sha256") == sha256(dem)
    rows = check_files(data_dir, rels, "differs" if dem_ok else "rebuilt (not byte-comparable)", WHY["costsurface"])
    for r in rows:
        r["source"] = "computed from the DEM"
    return rows


STEPS = {"sites": do_sites, "stone": do_stone, "soils": do_soils, "rivers": do_rivers, "lithology": do_lithology,
         "dem": do_dem, "costsurface": do_costsurface}


# --------------------------------------------------------------------------------------------------- derived inputs
def derived_status(derived_dir):
    """Presence of every derived input of the manifest (group 'derived') under DERIVED_DIR."""
    rows = [r for r in manifest().values() if r["group"] == "derived"]
    miss = [r["path"] for r in rows if not os.path.isfile(os.path.join(derived_dir, r["path"].split("/", 1)[1]))]
    log(f"derived inputs in {derived_dir}: {len(rows) - len(miss)} of {len(rows)} present")
    for p in miss[:15]:
        log(f"  missing {p}")
    if len(miss) > 15:
        log(f"  ... and {len(miss) - 15} more")
    return miss


def fetch_derived(derived_dir, url=None, sha=None, downloads=None):
    """Download + unpack the prebuilt derived-input pack (zip or tar.gz) into DERIVED_DIR."""
    url = url or DERIVED_URL
    if not url:
        log("DERIVED_URL is not set: the prebuilt derived-input pack is not public yet (results package, DOI "
            "pending). Rebuild instead (--rebuild-derived; HOW_TO_USE.md, section Derived inputs) or set DERIVED_URL when it is.")
        return derived_status(derived_dir)
    downloads = downloads or os.path.join(os.path.dirname(os.path.abspath(derived_dir)), "_downloads")
    name = os.path.basename(url.split("?")[0]) or "derived_pack"
    pack = os.path.join(downloads, name)
    got, ok = download(url, pack, sha=sha or DERIVED_SHA256, timeout=600)
    if ok is False:
        raise RuntimeError("derived pack: SHA-256 differs from DERIVED_SHA256")
    os.makedirs(derived_dir, exist_ok=True)
    if zipfile.is_zipfile(pack):
        unzip(pack, derived_dir)
    else:
        with tarfile.open(pack) as t:
            t.extractall(derived_dir)
    return derived_status(derived_dir)


# Rebuild order and the commands of data/derived/README.md. Times / memory from the project's logs (8 GB machine).
REBUILD_NOTES = """Derived-input rebuild (data/derived/README.md), with the times and peak memory recorded in the project's logs:
  cost rasters mu 0.05 / 0.1 / 0.38 / 0.5   tools/build_cost_mu.py            ~0.85 GB peak each (time not logged)
  base haul table                           preprocess.py                     14 s (stones7) / 249 s (hybrid), 1.7-2.4 GB
  haul tables per friction, buildstone, stones7  preprocess.py --tag ...      ~12 s each with stones7 (hybrid: up to ~4 min each), ~2 GB
  complexes quarrying far (S5c)             tools/haul_far.py                 seconds
  k-best quarry routes                      tools/kbest_quarries.py           95 s, 1.9 GB
  routes at mu 0.38 / wider-literature      tools/kbest_mu038.py, tools/wl_inputs.py   13 s (wl_inputs), 2.2 GB
  sea tables                                tools/sea_routes.py               192 s, 1.1 GB (cgroup peak 3.9 GB)
  food catchments r 1000/1500/2000/3000     tools/food_capacity.py            time not logged
  bichrome distances                        tools/census_bichrome.py          15 s, 1.5 GB
  stones4 comparison tables                 preprocess.py --rule stones4, tools/kbest_quarries.py   a few minutes
Total: about 30-45 min with hybrid (the full audited rule), 15-20 min with stones7 (estimate from the component logs; the sequence has
not been timed end to end). Peak memory ~2.5 GB (one process at a time)."""


def rebuild_derived(data_dir, derived_dir, stone_rule="hybrid", python=sys.executable, dry_run=False, resume=True):
    """Rebuild every derived input of the manifest into DERIVED_DIR, in the order of data/derived/README.md.

    resume=True: steps finished by an earlier, interrupted rebuild with the same configuration (recorded in
    DERIVED_DIR/../_rebuild/steps_done.txt) are skipped, so a disconnected runtime continues where it stopped.
    resume=False: every step is run again."""
    log(REBUILD_NOTES)
    if stone_rule == "hybrid" and not os.path.isfile(os.path.join(data_dir, "stone", "nid_materiale_prod.csv")):
        raise RuntimeError("stone_rule hybrid needs DATA_DIR/stone/nid_materiale_prod.csv: run fetch() first (it copies "
                           "data/nurnet/nurnet_site_building_stone.csv there). " + NURNET_NOTE)
    C = os.path.abspath(derived_dir)
    work = os.path.join(os.path.dirname(C), "_rebuild")
    cfg = write_config(data_dir, C, os.path.join(work, "config.yaml"), stone_rule)
    cfg4 = write_config(data_dir, os.path.join(C, "stones4"), os.path.join(work, "config_stones4.yaml"), "stones4")
    for d in ("cost_mu", "haul", "alliance", "sea", "food", "census", "stones4/haul", "stones4/alliance"):
        os.makedirs(os.path.join(C, d), exist_ok=True)
    MUS = ("0.05", "0.1", "0.38", "0.5")
    cost = lambda mu: os.path.join(C, "cost_mu", f"drag_cost_8dir_mu{mu}_int.tif")
    P = [python]
    cmds = [P + ["tools/build_cost_mu.py", cfg, mu, cost(mu)] for mu in MUS]
    cmds += [P + ["preprocess.py", cfg]]
    cmds += [P + ["preprocess.py", cfg, "--tag", f"mu{mu}", "--cost-raster", cost(mu)] for mu in MUS]
    cmds += [P + ["preprocess.py", cfg, "--tag", "buildstone", "--stones", "BUILDSTONE"],
             P + ["preprocess.py", cfg, "--tag", "buildstone_mu0.1", "--stones", "BUILDSTONE", "--cost-raster", cost("0.1")],
             P + ["preprocess.py", cfg, "--rule", "stones7", "--tag", "stones7"],
             P + ["tools/haul_far.py", cfg],
             P + ["tools/kbest_quarries.py", cfg],
             P + ["tools/kbest_mu038.py", cfg],
             P + ["tools/wl_inputs.py", cfg],
             P + ["tools/sea_routes.py", cfg]]
    cmds += [P + ["tools/food_capacity.py", cfg, "--soils", os.path.join(data_dir, "soils", "soils250k.geojson"),
                  "--radius", r, "--out", os.path.join(C, "food", f"site_food_r{r}.csv")] for r in ("1000", "1500", "2000", "3000")]
    cmds += [P + ["tools/census_bichrome.py", C]]
    # stones4 comparison set (tools/stone_rule.py): base, base_check, per friction, buildstone, far, k-best
    os.makedirs(os.path.join(C, "stones4", "cost_mu"), exist_ok=True)
    cmds += [P + ["preprocess.py", cfg4, "--rule", "stones4"],
             P + ["preprocess.py", cfg4, "--rule", "stones4", "--tag", "base_check"]]
    cmds += [P + ["preprocess.py", cfg4, "--rule", "stones4", "--tag", f"mu{mu}", "--cost-raster", cost(mu)] for mu in MUS]
    cmds += [P + ["preprocess.py", cfg4, "--tag", "buildstone", "--stones", "BUILDSTONE"],
             P + ["preprocess.py", cfg4, "--tag", "buildstone_mu0.1", "--stones", "BUILDSTONE", "--cost-raster", cost("0.1")],
             P + ["tools/haul_far.py", cfg4]]
    # the stones4 k-best routes need its own cost_mu/..._mu0.1 (link the base one)
    cmds += [["ln", "-sf", cost("0.1"), os.path.join(C, "stones4", "cost_mu", "drag_cost_8dir_mu0.1_int.tif")],
             P + ["tools/kbest_quarries.py", cfg4]]
    sig = hashlib.sha256(b"".join(open(p, "rb").read() for p in (cfg, cfg4))).hexdigest()
    done_f = os.path.join(work, "steps_done.txt")
    done = set()
    if resume and os.path.isfile(done_f):
        lines = open(done_f).read().splitlines()
        if lines and lines[0] == sig:
            done = set(lines[1:])
    if not dry_run and (not done or not resume):
        with open(done_f, "w") as f:
            f.write(sig + "\n")
    if done:
        log(f"  resuming an interrupted rebuild: {len(done)} of {len(cmds)} steps already done ({done_f})")
    t0 = time.time()
    for c in cmds:
        key = " ".join(c[1:]) if c[0] == python else " ".join(c)
        if dry_run:
            log("  (dry run) $ " + " ".join(c))
        elif key in done:
            log("  (done earlier) $ " + " ".join(c))
        else:
            run(c, cwd=os.path.join(REPO, "code"))
            with open(done_f, "a") as f:
                f.write(key + "\n")
    if not dry_run:
        os.remove(done_f)            # complete: a later rebuild (e.g. after DERIVED_DIR was emptied) starts afresh
        log(f"derived inputs rebuilt in {(time.time() - t0) / 60:.1f} min")
    return derived_status(derived_dir)


# --------------------------------------------------------------------------------------------------- main entry
def fetch(data_dir=None, only=None, rasters=True, downloads=None, basins=None, check_only=False):
    """Fetch / rebuild the raw inputs into DATA_DIR. Returns the list of per-file rows (also printed and written to
    DATA_DIR/fetch_provenance.json)."""
    data_dir = os.path.abspath(data_dir or os.path.join(REPO, "data"))
    dl = os.path.abspath(downloads or os.path.join(data_dir, "_downloads"))
    names = list(INPUTS) if not only else [x.strip() for x in (only.split(",") if isinstance(only, str) else only)]
    bad = [n for n in names if n not in STEPS]
    if bad:
        raise ValueError(f"unknown input(s) {bad}; choose from {list(STEPS)}")
    os.makedirs(data_dir, exist_ok=True)
    all_rows = []
    for n in names:
        log(f"== {n}")
        try:
            if check_only:
                rows = (do_sites(data_dir, dl) if n == "sites" else do_stone(data_dir, dl) if n == "stone" else
                        check_files(data_dir, [r["path"][5:] for r in manifest().values()
                                               if r["group"] == "raw_input" and r["path"].startswith("data/" + {
                                                   "soils": "soils", "rivers": "water", "lithology": "geology",
                                                   "dem": "dem", "costsurface": "costsurface"}[n])]))
            else:
                rows = STEPS[n](data_dir, dl, rasters=rasters, basins=basins)
        except Exception as e:                                    # keep going: report it at the end
            log(f"  FAILED: {e}")
            rows = [dict(path=n, status="FAILED", sha256=None, expected=None, note=str(e)[:300])]
        all_rows += rows
    if not check_only:
        write_provenance(data_dir, [r for r in all_rows if r["status"] not in ("missing", "missing (optional)")])
    else:                                                         # a file rebuilt earlier by fetch(): its recorded status
        pf = os.path.join(data_dir, PROVENANCE)
        prov = json.load(open(pf)).get("files", {}) if os.path.isfile(pf) else {}
        for r in all_rows:
            pv = prov.get(r["path"]) or {}
            if r["status"] == "differs" and str(pv.get("status", "")).startswith("rebuilt") and pv.get("sha256") == r["sha256"]:
                r["status"], r["note"] = pv["status"], pv.get("note", "")
    log("\n" + summary(all_rows))
    return all_rows


def summary(rows):
    w = max(len(r["path"]) for r in rows) if rows else 10
    out = [f"{'file (under DATA_DIR)':<{w}}  status"]
    for r in rows:
        out.append(f"{r['path']:<{w}}  {r['status']}" + (f"  - {r['note']}" if r.get("note") and r["status"] not in
                                                         ("identical",) else ""))
    n_bad = sum(r["status"] in ("FAILED", "differs") for r in rows)
    req = [r for r in rows if r["path"].startswith("sites/") and r["status"] != "identical"]
    out.append(f"{len(rows)} files: {sum(r['status'] == 'identical' for r in rows)} identical to the run's copy, "
               f"{sum(r['status'].startswith('rebuilt') for r in rows)} rebuilt (not byte-comparable), "
               f"{sum(r['status'].startswith('missing') for r in rows)} missing, {n_bad} failed/differing.")
    if req:
        out.append("The Nurnet site list is required and is not identical to the run's copy: restore data/nurnet/. " + NURNET_NOTE)
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", default=os.path.join(REPO, "data"), help="DATA_DIR (default REPO/data)")
    ap.add_argument("--downloads", help="where downloads are kept (default DATA_DIR/_downloads)")
    ap.add_argument("--only", help="comma list of: " + ", ".join(INPUTS))
    ap.add_argument("--no-rasters", action="store_true", help="skip the DEM mosaic and the cost/slope rasters")
    ap.add_argument("--basins", help="the run's catchment layer (if you have it): DEM mask of the run")
    ap.add_argument("--check-only", action="store_true", help="report only; download and build nothing")
    ap.add_argument("--derived-dir", help="DERIVED_DIR (default DATA_DIR/derived/cache)")
    ap.add_argument("--derived-url", help="URL of a prebuilt derived-input pack (zip or tar.gz)")
    ap.add_argument("--rebuild-derived", action="store_true", help="rebuild every derived input (long; see REBUILD_NOTES)")
    ap.add_argument("--stone-rule", default="hybrid", choices=("hybrid", "stones7"),
                    help="for --rebuild-derived (hybrid = the rule of the full audited run, default)")
    a = ap.parse_args()
    rows = fetch(a.data_dir, a.only, rasters=not a.no_rasters, downloads=a.downloads, basins=a.basins,
                 check_only=a.check_only)
    ddir = a.derived_dir or os.path.join(a.data_dir, "derived", "cache")
    if a.derived_url or DERIVED_URL:
        fetch_derived(ddir, a.derived_url)
    if a.rebuild_derived:
        rebuild_derived(a.data_dir, ddir, a.stone_rule)
    sys.exit(1 if any(r["status"] in ("FAILED", "differs") for r in rows) else 0)
