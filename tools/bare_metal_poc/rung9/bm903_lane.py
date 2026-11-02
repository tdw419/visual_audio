#!/usr/bin/env python3
"""BM903 lane guard: one executed boot at a time, on one medium at a time.

MEASURED, not theorised: two of the step-2 legs "failed" for purely operational
reasons while another qemu was alive -- QEMU takes a write lock on the image
even for a read-only boot (second qemu: `Failed to get "write lock"`, and the
gdb side then reports `could not connect`), and three concurrent TCG guests were
enough to push a boot that reaches `tc@box` in 11 s past a 240 s budget. So a
leg that runs beside another boot cannot be trusted either way, and the gates
ask this module first.

  usage: python3 bm903_lane.py [medium ...]      exit 0 = lane is clear
"""
import os
import sys
from pathlib import Path

MARK = ('bm903_medium', 'bm903_stage', 'qemu-system')


def live_boots():
    """(pid, medium-ish argv tail) for every qemu that is running BM903 work."""
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
        if 'bm903' in joined:
            med = next((w for w in cmd if w.startswith('file=') and 'bm903' in w), '?')
            out.append((int(e.name), med[5:]))
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    want = [str(Path(a).resolve()) for a in argv if not a.startswith('-')]
    boots = live_boots()
    if not boots:
        print('lane clear: no bm903 qemu alive')
        return 0
    print(f'lane BUSY: {len(boots)} bm903 qemu alive')
    for pid, med in boots:
        print(f'  pid {pid}: {med}')
        for w in want:
            if Path(med).resolve() == Path(w):
                print(f'  REFUSE: this leg needs {w}, which pid {pid} has locked')
    return 1


if __name__ == '__main__':
    sys.exit(main())
