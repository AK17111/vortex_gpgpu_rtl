#!/usr/bin/env python3
"""How early does decode know a unit is about to wake up?

For each gated unit, every time its clock turns back on (clk_en 0 -> 1) this
looks back for the most recent instruction of that unit's type leaving
decode (core decode_if.valid && ready, by ex_type). The gap is the "lead
time": how many cycles of warning a decode-stage predictor would have had.

Mapping: ALU int <- EX_ALU (0), SFU wctl <- EX_SFU (2), FPU <- EX_FPU (3).
(muldiv is also EX_ALU, so it isn't separated here.)

Usage:  python3 lead_time.py trace.vcd     (VCD recorded with -DVX_ICG_ENABLE)
"""
import sys
from bisect import bisect_right

GATE_EX = {'int_icg': 0, 'wctl_icg': 2, 'fpu_icg': 3}
NAMES = {'int_icg': 'ALU int', 'wctl_icg': 'SFU wctl', 'fpu_icg': 'FPU'}

def main():
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    f = open(sys.argv[1], 'rb')
    scope, en, clk, dec = [], {}, None, {}
    for raw in f:
        l = raw.decode('latin1').strip()
        if l.startswith('$scope'): scope.append(l.split()[2])
        elif l.startswith('$upscope'): scope.pop()
        elif l.startswith('$var'):
            p = l.split(); code, name = p[3], p[4]
            if name == 'clk_en' and scope and scope[-1] in GATE_EX: en[code] = scope[-1]
            if name == 'clk' and len(scope) == 1 and clk is None: clk = code
            # the core's own decode_if (scope ends in ...core.decode_if[.data])
            if len(scope) >= 2 and scope[-2] == 'core' and scope[-1] == 'decode_if' and name in ('valid', 'ready'):
                dec.setdefault(name, code)
            if len(scope) >= 3 and scope[-3] == 'core' and scope[-2] == 'decode_if' and scope[-1] == 'data' and name == 'ex_type':
                dec.setdefault('ex_type', code)
        elif l.startswith('$enddefinitions'): break
    if not en or len(dec) < 3: sys.exit("Need a VCD recorded with -DVX_ICG_ENABLE (and decode_if signals).")

    rev = {v: k for k, v in dec.items()}
    sig = {'valid': '0', 'ready': '0', 'ex_type': '0'}
    ev = {c: '0' for c in en}; prev = dict(ev)
    decodes = {t: [] for t in GATE_EX.values()}
    wakes = {c: [] for c in en}
    cyc, cur = 0, '0'
    for raw in f:
        l = raw.decode('latin1').strip()
        if not l or l[0] == '#': continue
        if l[0] == 'b':
            v, c = l[1:].split()
            if c in rev: sig[rev[c]] = v
            continue
        if l[0] in '01xz':
            v, c = l[0], l[1:]
            if c in ev: ev[c] = v
            elif c in rev: sig[rev[c]] = v
            elif c == clk:
                if v == '1' and cur == '0':
                    cyc += 1
                    if sig['valid'] == '1' and sig['ready'] == '1':
                        try:
                            t = int(sig['ex_type'], 2)
                            if t in decodes: decodes[t].append(cyc)
                        except ValueError: pass
                    for k in ev:
                        if ev[k] == '1' and prev[k] == '0': wakes[k].append(cyc)
                        prev[k] = ev[k]
                cur = v

    buckets = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, None)]
    for c, g in en.items():
        d = decodes[GATE_EX[g]]; leads = []; miss = 0
        for w in wakes[c]:
            i = bisect_right(d, w) - 1
            if i >= 0: leads.append(w - d[i])
            else: miss += 1
        print(f"== {NAMES[g]}: {len(wakes[c])} wake-ups, {len(d)} decodes of that type")
        if leads:
            leads.sort()
            print(f"   lead time (cycles from decode to clock turning on): "
                  f"min {leads[0]}, median {leads[len(leads)//2]}, max {leads[-1]}")
            for lo, hi in buckets:
                n = sum(1 for x in leads if x >= lo and (hi is None or x <= hi))
                lab = f"{lo}" if lo == hi else (f"{lo}+" if hi is None else f"{lo}-{hi}")
                print(f"   {lab:>6} cycles: {n:5d} ({100*n/len(leads):4.0f}%)")
        if miss: print(f"   {miss} wake-ups had no earlier decode in the trace window")
        print()

if __name__ == '__main__':
    main()