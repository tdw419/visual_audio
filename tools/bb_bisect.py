#!/usr/bin/env python3
"""Bisect the threading divergence: diff threaded vs non-threaded full register state.

Runs the SAME boot to the same step count twice — once with basic-block threading
enabled, once disabled — and prints the first differing register and pc. This pinpoints
the exact instruction where the threaded path diverges from the correct (non-threaded)
execution, so we can see what threading does wrong.

Usage: python3 tools/bb_bisect.py 4400000 [4500000 ...]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from test_alpine_opensbi_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

REG_NAMES = ['x0', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2',
             's0', 's1', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5',
             'a6', 'a7', 's2', 's3', 's4', 's5', 's6', 's7',
             's8', 's9', 's10', 's11', 't3', 't4', 't5', 't6']


def run(steps, threading):
    core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    core.set_bb_threading(threading)
    t0 = time.time()
    core.step(steps)
    dt = time.time() - t0
    s = core.get_state()
    return s, dt


def main():
    step_counts = [int(x) for x in sys.argv[1:]] or [4400000]
    for steps in step_counts:
        st_on, dt_on = run(steps, True)
        st_off, dt_off = run(steps, False)
        print(f'--- {steps} steps: threading ON {dt_on:.1f}s / OFF {dt_off:.1f}s ---')
        print(f'  pc  ON=0x{st_on["pc"]:x}  OFF=0x{st_off["pc"]:x}  mode {st_on["mode"]}/{st_off["mode"]}')
        regs_on = st_on['regs']
        regs_off = st_off['regs']
        diffs = []
        for i in range(32):
            lo_on, hi_on = regs_on[i]
            lo_off, hi_off = regs_off[i]
            v_on = int(lo_on) | (int(hi_on) << 32)
            v_off = int(lo_off) | (int(hi_off) << 32)
            if v_on != v_off:
                diffs.append((i, v_on, v_off))
        if not diffs:
            print('  registers: IDENTICAL')
        else:
            for i, v_on, v_off in diffs[:12]:
                print(f'  {REG_NAMES[i]:>3}: ON=0x{v_on:016x}  OFF=0x{v_off:016x}')
            if len(diffs) > 12:
                print(f'  ... and {len(diffs)-12} more')
        print(f'  bb: on={st_on["bb_threaded_insts"]} off={st_off["bb_threaded_insts"]} '
              f'total={st_on["bb_total_insts"]}/{st_off["bb_total_insts"]} '
              f'ctl={st_on["bb_ctl_insts"]}/{st_off["bb_ctl_insts"]}')


if __name__ == '__main__':
    main()
