"""FIX1030B check: each regenerated table against its delivered version.

  check1030b.py --out DIR OLD.csv:NEW.csv:KEY [...]

Rows are matched on KEY (empty KEY: whole-table comparison in row order). A row passes if every column is equal
(numbers to rtol 1e-12). Expected: only rows whose key names the `low` scenario (low, low_P10, ...) differ, and
rows/columns are the same sets. Writes DIR/<new name>_diff.csv (changed rows, old and new values side by side) and
DIR/summary.txt; exit 1 if anything other than a low row changed.
"""
import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

LOW = re.compile(r"(^|[^a-z])low([^a-z]|$)")


def same(a, b):
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        return np.isclose(a.to_numpy(float), b.to_numpy(float), rtol=1e-12, atol=0, equal_nan=True)
    return (a.astype(str).to_numpy() == b.astype(str).to_numpy()) | (a.isna().to_numpy() & b.isna().to_numpy())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("pairs", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    lines, bad = [], 0
    for p in a.pairs:
        old_f, new_f, key = p.split(":")
        tag = os.path.relpath(new_f, os.path.dirname(os.path.dirname(new_f))).replace("/", "__")
        old = pd.read_csv(old_f, comment=None)
        new = pd.read_csv(new_f, comment=None)
        if set(old.columns) != set(new.columns):
            lines.append(f"{tag}: COLUMNS differ {sorted(set(old.columns) ^ set(new.columns))}"); bad += 1; continue
        new = new[list(old.columns)]
        if key:
            if old[key].duplicated().any() or new[key].duplicated().any():
                k2 = [key] + [c for c in ("phasing", "family") if c in old.columns]
                old = old.set_index(k2); new = new.set_index(k2)
            else:
                old = old.set_index(key); new = new.set_index(key)
            if set(old.index) != set(new.index):
                lines.append(f"{tag}: ROWS differ {sorted(map(str, set(old.index) ^ set(new.index)))[:10]}"); bad += 1; continue
            new = new.loc[old.index]
        elif len(old) != len(new):
            lines.append(f"{tag}: row count {len(old)} -> {len(new)}"); bad += 1; continue
        eq = np.ones((len(old), len(old.columns)), bool)
        for j, c in enumerate(old.columns):
            eq[:, j] = same(old[c].reset_index(drop=True), new[c].reset_index(drop=True))
        rows = ~eq.all(axis=1)
        keys = [str(k) for k in old.index[rows]]
        nonlow = [k for k in keys if not LOW.search(k)]
        if rows.any():
            cols = [c for j, c in enumerate(old.columns) if (~eq[rows, j]).any()]
            d = pd.concat({"old": old[rows][cols], "new": new[rows][cols]}, axis=1)
            d.to_csv(os.path.join(a.out, f"{tag}_diff.csv"))
        lines.append(f"{tag}: {len(old)} rows, {int(rows.sum())} changed ({', '.join(keys[:6])}{' ...' if len(keys) > 6 else ''})"
                     + (f"; NON-LOW rows changed: {nonlow[:6]}" if nonlow else ""))
        bad += bool(nonlow)
    lines.append(f"CHECK {'PASS: only low rows changed' if not bad else 'FAIL: see above'} ({len(a.pairs)} tables)")
    open(os.path.join(a.out, "summary.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
