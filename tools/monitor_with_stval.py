#!/usr/bin/env python3
"""
monitor_rv64i.py with stval/mtval logging for Alpine boot stall diagnosis.
Based on original monitor_rv64i.py but adds trap value logging.

Usage:
    python3 tools/monitor_with_stval.py --steps-per-tick 100000 --max-steps 70000000 --out /tmp/rv64i_stval_detailed.jsonl
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

CSR_MCAUSE = 0x342
CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_MTVAL = 0x343

MODE_NAMES = {0: 'U', 1: 'S', 3: 'M'}


def monitor_alpine(steps_per_tick: int, max_steps: int, out_path: str):
    print("=== Alpine boot with stval/mtval logging ===\n")

    # Initialize CPU
    core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)

    # Load OpenSBI and Alpine kernel
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    print(f"DTB at: 0x{dtb_addr:x}\n")

    out_fh = open(out_path, 'w')
    total_steps = 0
    t_start = time.time()

    print(f"{'steps':>12} {'steps/s':>10} {'pc':>18} {'mode':>4} {'mcause':>4} {'scause':>4} {'stval':>18} {'mtval':>18}")

    while total_steps < max_steps:
        batch = min(steps_per_tick, max_steps - total_steps)
        t0 = time.time()
        core.step(steps=batch)
        state = core.get_state()
        t1 = time.time()
        total_steps += batch

        # Read all trap CSRs
        mcause = core.read_csr(CSR_MCAUSE)
        scause = core.read_csr(CSR_SCAUSE)
        stval = core.read_csr(CSR_STVAL)
        mtval = core.read_csr(CSR_MTVAL)

        rate = batch / (t1 - t0) if t1 > t0 else float('inf')
        mode = MODE_NAMES.get(state['mode'], str(state['mode']))

        # Write detailed log
        log_entry = {
            'steps': total_steps,
            'steps_per_s': round(rate),
            'pc': state['pc'],
            'mode': mode,
            'mcause': mcause,
            'scause': scause,
            'stval': stval,
            'mtval': mtval,
            'halted': bool(state['halted']),
            'trap_pending': bool(state['trap_pending'])
        }
        out_fh.write(json.dumps(log_entry) + "\n")

        # Print progress
        print(f"{total_steps:>12} {round(rate):>10} {hex(state['pc']):>18} {mode:>4} {hex(mcause):>4} {hex(scause):>4} {hex(stval):>18} {hex(mtval):>18}")

        # Stop early if we see sustained faulting
        if total_steps > 55_000_000 and mcause == 9 and scause == 12 and stval != 0:
            print(f"\n*** Faulting at 0x{stval:x} (mtval=0x{mtval:x}) at step {total_steps:,} ***")

    out_fh.close()
    print(f"\nTrace written to {out_path}")
    print(f"Total steps: {total_steps:,}")
    print(f"Duration: {time.time() - t_start:.1f}s")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Monitor Alpine boot with stval/mtval logging')
    parser.add_argument('--steps-per-tick', type=int, default=100_000, help='Steps per batch')
    parser.add_argument('--max-steps', type=int, default=70_000_000, help='Maximum steps')
    parser.add_argument('--out', type=str, default='/tmp/rv64i_stval_detailed.jsonl', help='Output file')
    args = parser.parse_args()

    monitor_alpine(args.steps_per_tick, args.max_steps, args.out)