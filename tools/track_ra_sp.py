#!/usr/bin/env python3
"""
Track x1 (ra - return address) and sp (stack pointer) to diagnose NULL PC crash.

Focus: Detect when x1 becomes NULL or corrupted, which causes ret/jalr to jump to 0.
"""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from spatial_rv64i_cpu import SpatialRV64ICore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

def track_ra_sp(max_steps: int = 20_000_000, steps_per_tick: int = 500_000):
    core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)

    total_steps = 0
    last_good_ra = None
    last_good_pc = None
    sp_history = []

    print(f"{'steps':>12} {'pc':>18} {'x1(ra)':>18} {'sp':>18} {'mode'}")
    print("=" * 78)

    while total_steps < max_steps:
        batch = min(steps_per_tick, max_steps - total_steps)
        core.step(steps=batch)
        total_steps += batch

        state = core.get_state()
        regs = state['regs']
        pc = state['pc']
        ra = (regs[1][0] | (regs[1][1] << 32))
        sp = (regs[2][0] | (regs[2][1] << 32))
        mode = {0: 'U', 1: 'S', 3: 'M'}[state['mode']]

        # Check for NULL or suspicious values
        if pc == 0:
            print(f"\n!! NULL PC at step {total_steps}")
            print(f"   Last good PC: 0x{last_good_pc:x}")
            print(f"   Last good ra: 0x{last_good_ra:x}")
            print(f"   Current ra:   0x{ra:x}")
            print(f"   Current sp:   0x{sp:x}")
            print(f"   Mode: {mode}")
            # Show stack trace around sp
            print(f"\n   Stack around sp (16 words):")
            for i in range(-8, 8):
                if 0 <= i < 100:  # Safety limit
                    addr = sp + i * 8
                    try:
                        word = core.read_mem_word(addr - 0x80000000) if addr >= 0x80000000 else 0
                        print(f"     [{addr:+04x}]: 0x{word:016x}")
                    except:
                        break
            return total_steps, state

        if ra == 0 or (ra & 0xFFFFFFFF80000000) != 0xFFFFFFFF80000000:
            # ra is NULL or not in kernel space
            if mode == 'S':  # Only warn in S-mode (not M-mode)
                print(f"!! Suspicious ra at step {total_steps}: 0x{ra:x}")

        last_good_ra = ra
        last_good_pc = pc
        sp_history.append((total_steps, sp))

        # Print periodic updates
        if total_steps % (steps_per_tick * 2) == 0:
            print(f"{total_steps:>12} 0x{pc:016x} 0x{ra:016x} 0x{sp:016x} {mode}")

    print(f"\nNo NULL PC found in {total_steps} steps")
    return total_steps, state

if __name__ == '__main__':
    steps = 0
    state = None
    try:
        steps, state = track_ra_sp()
        print(f"\nFinal state at step {steps}:")
        print(f"  PC: 0x{state['pc']:x}")
        print(f"  halted: {bool(state['halted'])}")
    except KeyboardInterrupt:
        print(f"\nInterrupted at step {steps}")