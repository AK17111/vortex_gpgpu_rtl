#!/usr/bin/env python3
"""Idle-window statistics for the Vortex unit clock gates.

Reads a VCD recorded with gating on (CONFIGS="-DVX_ICG_ENABLE" ... --vcd).
For each gate (int_icg, mdv_icg, fpu_icg, wctl_icg) it looks at clk_en on
every rising edge of the top-level clock and reports:
  - % of cycles the unit's clock was on / gated off
  - how many idle windows (runs of consecutive gated-off cycles) there were
  - a histogram of idle-window lengths
  - how much of the idle time sits in windows at least N cycles long
    (useful for asking "would power gating with an N-cycle break-even pay off?")

Usage:  python3 idle_windows.py trace.vcd [--csv out.csv]
"""
import sys, csv

GATES = ('int_icg', 'mdv_icg', 'fpu_icg', 'wctl_icg')
NAMES = {'int_icg': 'ALU int', 'mdv_icg': 'muldiv', 'fpu_icg': 'FPU', 'wctl_icg': 'SFU wctl'}
BUCKETS = [(1, 1), (2, 3), (4, 7), (8, 15), (16, 63), (64, 255), (256, None)]
THRESH = [4, 16, 64, 256]

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    out_csv = sys.argv[sys.argv.index('--csv') + 1] if '--csv' in sys.argv else None

    f = open(path, 'rb')
    scope, en_code, clk = [], {}, None
    for raw in f:
        l = raw.decode('latin1').strip()
        if l.startswith('$scope'):
            scope.append(l.split()[2])
        elif l.startswith('$upscope'):
            scope.pop()
        elif l.startswith('$var'):
            p = l.split(); code, name = p[3], p[4]
            if name == 'clk_en' and scope and scope[-1] in GATES:
                en_code[code] = scope[-1]
            if name == 'clk' and len(scope) == 1 and clk is None:
                clk = code
        elif l.startswith('$enddefinitions'):
            break
    if not en_code:
        sys.exit("No clock gates found. Record the VCD with CONFIGS=\"-DVX_ICG_ENABLE\".")

    val = {c: '0' for c in en_code}
    on = {c: 0 for c in en_code}
    run = {c: 0 for c in en_code}            # current idle run length
    windows = {c: [] for c in en_code}       # finished idle windows
    edges, cur = 0, '0'
    for raw in f:
        l = raw.decode('latin1').strip()
        if not l or l[0] == '#':
            continue
        if l[0] in '01xz':
            v, c = l[0], l[1:]
            if c in val:
                val[c] = v
            elif c == clk:
                if v == '1' and cur == '0':
                    edges += 1
                    for k in val:
                        if val[k] == '1':
                            on[k] += 1
                            if run[k]:
                                windows[k].append(run[k]); run[k] = 0
                        else:
                            run[k] += 1
                cur = v
    for k in run:
        if run[k]:
            windows[k].append(run[k])

    rows = []
    print(f"{path}: {edges} clock edges\n")
    for c, g in sorted(en_code.items(), key=lambda x: GATES.index(x[1])):
        w = windows[c]; idle = edges - on[c]
        print(f"== {NAMES[g]} ({g})")
        print(f"   clock on {100*on[c]/edges:5.1f}%   gated off {100*idle/edges:5.1f}%   "
              f"idle windows: {len(w)}   avg length: {(sum(w)/len(w)) if w else 0:.1f}   longest: {max(w) if w else 0}")
        hist = []
        for lo, hi in BUCKETS:
            n = sum(1 for x in w if x >= lo and (hi is None or x <= hi))
            cyc = sum(x for x in w if x >= lo and (hi is None or x <= hi))
            lab = f"{lo}" if lo == hi else (f"{lo}+" if hi is None else f"{lo}-{hi}")
            hist.append((lab, n, cyc))
        print("   window length  count   share of idle cycles")
        for lab, n, cyc in hist:
            print(f"   {lab:>12}  {n:6d}   {100*cyc/idle if idle else 0:5.1f}%")
        ge = {t: (100*sum(x for x in w if x >= t)/idle if idle else 0) for t in THRESH}
        print("   idle time in windows >= N cycles: " +
              ", ".join(f"N={t}: {ge[t]:.0f}%" for t in THRESH) + "\n")
        row = {'unit': NAMES[g], 'edges': edges, 'clock_on_pct': round(100*on[c]/edges, 2),
               'gated_off_pct': round(100*idle/edges, 2), 'idle_windows': len(w),
               'avg_window': round(sum(w)/len(w), 2) if w else 0, 'longest_window': max(w) if w else 0}
        for lab, n, cyc in hist:
            row[f'windows_{lab}'] = n
        for t in THRESH:
            row[f'idle_in_ge{t}_pct'] = round(ge[t], 1)
        rows.append(row)

    if out_csv:
        with open(out_csv, 'w', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            wr.writeheader(); wr.writerows(rows)
        print(f"wrote {out_csv}")

if __name__ == '__main__':
    main()