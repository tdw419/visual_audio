#!/usr/bin/env python3
"""BM602 lane guard: one executed boot at a time, BM903's boots included.

rung9/bm903_lane.py has the measured reasons (QEMU takes a write lock on the
image even for a read-only boot, and three concurrent TCG guests push an
11-second boot past a 45-second one). This file exists because that guard only
looks for `bm903` in a qemu command line, and a bm602 boot is just as
contentious -- in both directions. So the check is bidirectional by prefix.

  usage: python3 bm602_lane.py        exit 0 = lane is clear
"""
import os
import sys
from pathlib import Path

MARKS = ('bm903', 'bm602')


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
        print('lane clear: no bm903/bm602 qemu alive')
        return 0
    print(f'lane BUSY: {len(boots)} bm903/bm602 qemu alive')
    for pid, med in boots:
        print(f'  pid {pid}: {med}')
        # Any live boot is enough to spoil a timed leg, but naming the exact
        # file is what tells a caller whether it is waiting on itself.
        for w in want:
            if Path(med).resolve() == Path(w):
                print(f'  REFUSE: this leg needs {w}, which pid {pid} has locked')
    return 1


if __name__ == '__main__':
    sys.exit(main())
