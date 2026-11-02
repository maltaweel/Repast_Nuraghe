"""Check of an own-cache sea-table build (gap-closing runs, specified by the authors): after tools/sea_routes.py wrote
<cache>/sea/, compare <cache>/sea/sea_meta.json with <cache>/sea_expect.json (written by make_gaps.py from the run
config with the same arithmetic as tools/sea_routes.py sea_params): every listed parameter (drag / walk speed, pull,
crew, boat factor, hoist, mean crew and block of the block draw ...) equal to 1e-9 relative, the speeds equal, and the
haul and people tables present and non-empty for every speed. Exit 1 on any mismatch. json only (no numpy).
    python check_sea_meta.py <cache_dir>"""
import json, os, sys

cd = sys.argv[1]
exp = json.load(open(os.path.join(cd, "sea_expect.json")))
meta = json.load(open(os.path.join(cd, "sea", "sea_meta.json")))
p = meta["params"]
bad = []
for k, v in exp["params"].items():
    got = p.get(k)
    if got is None or abs(float(got) - float(v)) > 1e-9 * max(1.0, abs(float(v))):
        bad.append(f"{k}: expected {v}, sea_meta {got}")
if [float(x) for x in meta["speeds"]] != [float(x) for x in exp["speeds"]]:
    bad.append(f"speeds: expected {exp['speeds']}, sea_meta {meta['speeds']}")
for kn in exp["speeds"]:
    for f in (f"sites_haul_sea{float(kn):g}kn.csv", f"people_sea{float(kn):g}kn.csv.gz"):
        q = os.path.join(cd, "sea", f)
        if not (os.path.isfile(q) and os.path.getsize(q) > 0):
            bad.append(f"missing or empty {q}")
if bad:
    print("SEA META CHECK FAILED " + cd + "\n  " + "\n  ".join(bad))
    sys.exit(1)
print(f"SEA META CHECK OK {cd}: " + ", ".join(f"{k} {p[k]}" for k in exp["params"]) + f"; speeds {meta['speeds']}")
