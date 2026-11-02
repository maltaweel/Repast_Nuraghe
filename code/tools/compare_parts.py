"""Identity test: compare two alliance part-file trees (cache/runs/alliance_NAME/<signature>/) file by file.

  python tools/compare_parts.py REF_DIR NEW_DIR --out IDENTITY.txt

Both must hold the same signature folder(s) and the same file names; .csv.gz files are compared on their
decompressed content (the gzip header holds a time stamp), all other files byte for byte.
Exit 0 = identical, 1 = any difference.
"""
import argparse
import gzip
import hashlib
import os
import sys


def digest(p):
    h = hashlib.sha256()
    with (gzip.open(p, "rb") if p.endswith(".gz") else open(p, "rb")) as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("new")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r, n = tree(a.ref), tree(a.new)
    lines = [f"reference: {len(r)} files; new: {len(n)} files",
             f"signature folders: reference {sorted({k.split(os.sep)[0] for k in r})}, new {sorted({k.split(os.sep)[0] for k in n})}"]
    only_r, only_n = sorted(set(r) - set(n)), sorted(set(n) - set(r))
    diff = [k for k in sorted(set(r) & set(n)) if digest(r[k]) != digest(n[k])]
    lines += [f"only in reference: {len(only_r)} {only_r[:5]}", f"only in new: {len(only_n)} {only_n[:5]}",
              f"compared: {len(set(r) & set(n))}; different content: {len(diff)} {diff[:10]}"]
    ok = not only_r and not only_n and not diff
    lines.append("IDENTITY " + ("PASS" if ok else "FAIL"))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
