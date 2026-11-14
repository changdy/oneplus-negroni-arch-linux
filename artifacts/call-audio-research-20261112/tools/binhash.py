"""Match legacy QShrink hashes against 'file.c: ADSP: fmt' strings left in firmware binaries.

usage: python -I binhash.py OUT.json LOG[,LOG...] BINARY...
Only reads the given files. Hash = last 4 MD5 bytes, big endian, +1 when divisible by 4.
"""
import hashlib
import json
import re
import sys

MARK = re.compile(rb"[A-Za-z0-9_]+\.(?:c|cpp|h):[\x20-\x7e\t\n]{1,400}")
QLINE = re.compile(r"^Q (\d+) ", re.M)


def qhash(text):
    h = int.from_bytes(hashlib.md5(text).digest()[-4:], "big")
    return h + 1 if h % 4 == 0 else h


def wanted(paths):
    texts = [open(p, errors="replace").read() for p in paths]
    return {int(m) for t in texts for m in QLINE.findall(t)}


def candidates(blob):
    return {m.group(0) for m in MARK.finditer(blob)}


def trims(s):
    return [s]


def scan(path, want):
    blob = open(path, "rb").read()
    found = {}
    cands = candidates(blob)
    pairs = [(qhash(t), t) for s in cands for t in trims(s)]
    found.update({h: t.decode("latin1") for h, t in pairs if h in want})
    return len(cands), found


def main():
    out, logs, bins = sys.argv[1], sys.argv[2].split(","), sys.argv[3:]
    want = wanted(logs)
    total = {}
    for b in bins:
        n, found = scan(b, want)
        total.update(found)
        print(b, "strings", n, "matches", len(found))
    print("TOTAL", len(total), "of", len(want))
    json.dump({str(k): v for k, v in sorted(total.items())}, open(out, "w"), indent=1)


main()
