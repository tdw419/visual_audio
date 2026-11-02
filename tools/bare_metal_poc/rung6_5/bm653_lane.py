#!/usr/bin/env python3
"""BM653 lane guard: one executed boot at a time, BM903's and BM602's included.

Same measured reasons as `rung6/bm602_lane.py`, which itself inherits them from
`rung9/bm903_lane.py`: QEMU takes a write lock on the image even for a
read-only boot, and three concurrent TCG guests push an 11-second boot past a
45-second one. This file exists because both older guards look only for their
own prefix, and a bm653 boot -- which is the same guest, the same 512 MB, and a
LARGER medium -- is just as contentious in both directions.

The asymmetry is stated rather than fixed, because fixing it means editing a
landed rung: `rung6/bm602_lane.py` does NOT know about bm653, so running
`run_bm602_e2e.sh` beside this row is unguarded from that side. BM653's legs
therefore refuse whenever ANY of the three prefixes is live, which covers the
combination that actually happens -- this row's own script, and a stray rung9
or rung6 leg started from another shell.

  usage: python3 bm653_lane.py        exit 0 = lane is clear
"""
import os
import sys
from pathlib import Path

MARKS = ('bm903', 'bm602', 'bm653')


def live_boots():
    out = []
    for e in os.scandir('/proc'):
        if not e.name.isdigit():
            continue
        try:
            argv = Path(e.path, 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        cmd = [a.decode('latin-1') for a in argv if a]
        if not cmd or 'qemu-system' not in cmd[0]:
            continue
        joined = ' '.join(cmd)
        if any(m in joined for m in MARKS):
            med = next((w[5:] for w in cmd if w.startswith('file=')), '?')
            out.append((int(e.name), med))
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    want = [str(Path(a).resolve()) for a in argv if not a.startswith('-')]
    boots = live_boots()
    if not boots:
        print(f'lane clear: no {"/".join(MARKS)} qemu alive')
        return 0
    print(f'lane BUSY: {len(boots)} {"/".join(MARKS)} qemu alive')
    for pid, med in boots:
        print(f'  pid {pid}: {med}')
        for w in want:
            if Path(med).resolve() == Path(w):
                print(f'  REFUSE: this leg needs {w}, which pid {pid} has locked')
    return 1


if __name__ == '__main__':
    sys.exit(main())
