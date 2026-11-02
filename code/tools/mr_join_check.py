"""Checks for the join help mode (tests/mr_join_subset.sh).
  1 MOST_REALISTIC_handover_* == the pre-join MOST_REALISTIC_* subset runs (merged runs file and every part file, by
    content; the names and hence the signature hash differ, nothing else may)
  2 join runs: every site finished, max season, max site days.
  python tools/mr_join_check.py --root merged/subset/mr
"""
import argparse
import glob
import os

import pandas as pd


def pdir(root, name, oldest=False):
    ds = [d for d in glob.glob(os.path.join(root, "parts", f"alliance_{name}", "*")) if glob.glob(os.path.join(d, "*.done"))]
    return (min if oldest else max)(ds, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", required=True); a = ap.parse_args()
    ok_all = True
    for p in ("P10", "P20", "P100"):
        new, old = f"MOST_REALISTIC_handover_{p}", f"MOST_REALISTIC_{p}"
        r1 = pd.read_csv(os.path.join(a.root, "alliance", new, "nuraghe_manhours_runs.csv.gz"))
        r0 = pd.read_csv(os.path.join(a.root, "alliance_prejoin", old, "nuraghe_manhours_runs.csv.gz"))
        same = r1.equals(r0)
        d1 = pdir(a.root, new)
        d0 = pdir(a.root, old, oldest=True)        # the pre-join run of the old name (the newest dir there is the join run)
        files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d0, "seed_*.csv.gz")))
        bad = [f for f in files if not pd.read_csv(os.path.join(d1, f)).equals(pd.read_csv(os.path.join(d0, f)))]
        ok = same and not bad and len(files) == len(glob.glob(os.path.join(d1, "seed_*.csv.gz")))
        ok_all &= ok
        print(f"handover {p}: runs file equal {same}; part files {len(files)}, differ {len(bad)} -> {'PASS' if ok else 'FAIL'}")
    for p in ("P10", "P20", "P100"):
        n = f"MOST_REALISTIC_{p}"
        mx_s, mx_d, unf = 0, 0, 0
        for f in sorted(glob.glob(os.path.join(pdir(a.root, n), "seed_*.sites.csv.gz"))):
            s = pd.read_csv(f, usecols=["finish_day", "finish_season", "days"])
            unf += int((s.finish_day < 0).sum()); mx_s = max(mx_s, int(s.finish_season.max())); mx_d = max(mx_d, int(s.days.max()))
        print(f"join {p}: unfinished sites {unf}; max season {mx_s} (stop 20000); max site days {mx_d}")
    import json
    for n in [f"MOST_REALISTIC{v}_{p}" for v in ("", "_handover", "_alone") for p in ("P10", "P20", "P100")]:
        js = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(pdir(a.root, n), "seed_*.population.json")))]
        if js:
            j = pd.DataFrame(js)
            print(f"population {n}: total residents {j.total_residents.mean():,.0f}; active peak {j.active_peak_residents.mean():,.0f}"
                  f" (max {j.active_peak_residents.max():,.0f}); ceiling {j.ceiling.iloc[0]:,.0f} binding in {int(j.binding.sum())}/{len(j)} seeds,"
                  f" redraws {int(j.redraws.sum())}")
    print("ALL HANDOVER IDENTITY PASS" if ok_all else "HANDOVER IDENTITY FAIL")


if __name__ == "__main__":
    main()
