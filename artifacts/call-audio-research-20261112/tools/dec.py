"""usage: python -I dec.py MAP.json LOG FIRST LAST [regex]  -- print decoded F3 lines"""
import json
import re
import sys

m = json.load(open(sys.argv[1]))
L = open(sys.argv[2], errors='replace').read().splitlines()
a, b = int(sys.argv[3]), int(sys.argv[4])
flt = re.compile(sys.argv[5]) if len(sys.argv) > 5 else None
SPEC = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?(?:ll|l|h|z)?[diuxXp]")


def expand(fmt, args):
    it = iter(args)
    return SPEC.sub(lambda s: next(it, '?'), fmt)


def line(i):
    f = L[i].split()
    q = len(f) > 3 and f[0] == 'Q'
    if q and f[1] in m:
        return '%d %s' % (i + 1, expand(m[f[1]], f[4:]))
    return '%d %s' % (i + 1, L[i][:170])


out = [line(i) for i in range(a - 1, min(b, len(L)))]
out = [o for o in out if not flt or flt.search(o)]
print('\n'.join(o[:260] for o in out))
