#!/usr/bin/env python3
"""BM653: what did the leg actually cost, measured the way BM652 measured it?

BM652 §6 priced the fork at 392 B of code from a probe file -- mode-exit 43,
exec+receipt 155, re-entry 53, helpers 79, strings 62 -- against a matched
baseline whose code end was 3,776 B. This file re-runs that arithmetic on the
REAL fork instead of the probe, because the row's budget claim should be a
measurement of what shipped:

  * baseline: rung6's own `bm602_stage2_px.asm`, assembled with rung6's own
    `.inc` on the include path, listing into scope653/;
  * fork: `build/bm653_stage2_px.asm` as mkimg assembled it for the green combo,
    same warning-free rule;
  * code end = the offset on the file's own `times` padding line (BM652's
    `list_end`), which is the only offset that answers "where did the code
    stop" for a file that contains legitimate zero bytes;
  * the BEE-OFF control is measured in the same breath, and must be
    SIZE-NEUTRAL: R-SCOPE-11 says a control that changes the code size is an
    edit to a gated loader, not a switch.

Writes only into scope653/. No boots, no media, no substrate.
  usage: python3 bm653_size.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG6 = HERE.parent / 'rung6'
RUNG9 = HERE.parent / 'rung9'
OUT = HERE / 'scope653'

sys.path.insert(0, str(HERE))
import bm650_scope as scope650                                       # noqa: E402
import bm652_scope as scope652                                       # noqa: E402

nasm, list_end = scope650.nasm, scope652.list_end


def end_of(src, tag):
    """Code end of `src`, warning-free nasm or the file does not count."""
    OUT.mkdir(exist_ok=True)
    nasm(src, OUT / f'{tag}.bin', lst=OUT / f'{tag}.lst',
         cwd=src.parent, incs=(HERE, RUNG6, RUNG9))
    return list_end(OUT / f'{tag}.lst')


def main() -> int:
    base = end_of(RUNG6 / 'bm602_stage2_px.asm', 'bm602_px_baseline')
    fork = end_of(HERE / 'build' / 'bm653_stage2_px.asm', 'bm653_px_fork')
    ctrl = end_of(HERE / 'build' / 'bm653_stage2_beeoff.asm', 'bm653_px_beeoff')
    leg = fork - base
    assert base == 3776, (
        f'rung6\'s baseline code end is {base:,} B, not the 3,776 B BM652 §6 '
        'measured -- the fork is still whatever it is, but "the leg cost N B" '
        'is an arithmetic on this baseline, so a moved baseline moves the claim')
    print(f'baseline (rung6/bm602_stage2_px.asm): code end {base:,} B '
          f'-- exactly BM652 §6\'s number for this file, so the methods agree')
    print(f'fork     (build/bm653_stage2_px.asm): code end {fork:,} B  ->  '
          f'the leg cost {leg:,} B, against BM652\'s priced estimate of 392 B '
          f'({leg - 392:+,} B, {100.0 * leg / 392:.0f} % of it)')
    print(f'control  (build/bm653_stage2_beeoff.asm): code end {ctrl:,} B ->  '
          f'{ctrl - fork:+,} B against the fork')
    assert ctrl == fork, (
        f'the BEE-OFF control moved the code end by {ctrl - fork:+,} B: that is '
        'an edit to a gated loader, not a switch (R-SCOPE-11)')
    free = 8192 - fork
    print(f'budget: {free:,} B of the 8,192 B stage2 container still free '
          f'({100.0 * fork / 8192:.1f} % used); BM652 measured 4,416 B free '
          f'in the baseline, so the leg spent {4416 - free:,} B of it')
    print('BM653_SIZE_STATUS=GREEN' if leg > 0 else 'BM653_SIZE_STATUS=RED')
    return 0 if leg > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
