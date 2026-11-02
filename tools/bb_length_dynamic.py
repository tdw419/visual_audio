#!/usr/bin/env python3
"""Measure the DYNAMIC basic-block length distribution of a real Alpine boot.

Runs the RV64I GPU emulator (with bb_* counters added to SPATIAL_RV64I.wgsl) for a
fixed number of steps and reads back:
  bb_total_insts    — instructions executed through either path
  bb_ctl_insts      — control-flow instructions (block ends) via the fast path
  bb_fallback_insts — instructions that fell back to runtime decode (not pre-decoded)

avg_block = (bb_total - bb_fallback) / bb_ctl is the honest dynamic average basic-block
length on the pre-decoded fast path — the number that decides whether basic-block
threading is worth implementing in the real emulator (vs. the toy benchmark).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # tools/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from test_alpine_opensbi_boot import load_opensbi_alpine_and_dtb, RAM_SIZE


def main():
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 15_000_000
    core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
    print('[1] Loading OpenSBI + Alpine + DTB...')
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    print('[2] Running %d steps...' % steps)
    t0 = time.time()
    core.step(steps)
    dt = time.time() - t0
    s = core.get_state()
    total = s['bb_total_insts']
    ctl = s['bb_ctl_insts']
    fb = s['bb_fallback_insts']
    thr = s['bb_threaded_insts']
    print('[3] Done in %.1fs (%.0f steps/s)' % (dt, steps / dt))
    print('    pc=0x%x mode=%d halted=%d' % (s['pc'], s['mode'], s['halted']))
    # Key registers at freeze: a0 (hartid from OpenSBI), a1 (dtb), sp, ra
    regs = s['regs']
    for name, idx in [('a0', 10), ('a1', 11), ('a2', 12), ('a3', 13),
                      ('sp', 2), ('ra', 1), ('t0', 5), ('t1', 6)]:
        lo, hi = regs[idx]
        print('    %-4s = 0x%x' % (name, int(lo) | (int(hi) << 32)))
    print('    bb_total_insts    = %d' % total)
    print('    bb_ctl_insts      = %d' % ctl)
    print('    bb_fallback_insts = %d' % fb)
    print('    bb_threaded_insts = %d' % thr)
    fast_total = total - fb
    if fast_total > 0 and ctl > 0:
        avg = fast_total / ctl
        print('    fast-path avg block = %.2f instructions' % avg)
        print('    (fast-path insts %d / ctl insts %d; fallback fraction %.4f)' % (
            fast_total, ctl, fb / total if total else 0))
    elif fast_total == 0:
        print('    ERROR: no fast-path instructions executed — counters not working?')
    else:
        print('    ERROR: ctl=0 — counters not working?')


if __name__ == '__main__':
    main()
