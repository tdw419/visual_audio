#!/usr/bin/env python3
"""
Capture stval/mtval values during Alpine boot stall.
Logs trap changes to identify faulting virtual addresses.
"""

import sys
import os
import json

# Add parent directory to path to import tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE


def main():
    print("=== RV64I stval/mtval Probe ===")
    print()

    # Initialize CPU
    print("Initializing CPU...")
    core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)

    # Load OpenSBI and Alpine kernel
    print("Loading OpenSBI and Alpine kernel...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    # OpenSBI expects a0=hart id, a1=DTB address on entry — without this it dereferences
    # a garbage/zero a1 almost immediately (the M-mode mtval=0x4 fault every other run of
    # this script hit before this fix was a NULL-ish deref from a never-set a1, not the
    # real S-mode stall this probe exists to investigate).
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    print(f"DTB at: 0x{dtb_addr:x}")
    print()

    # Track previous trap state to detect changes
    prev_mcause = None
    prev_scause = None

    # Log file for trap events
    log_file = "/tmp/rv64i_stval_trap_log.jsonl"

    print("Starting boot sequence...")
    print()

    with open(log_file, 'w') as f:
        # Step quickly to ~55M (just before stall). Batch into single step() calls
        # (as monitor_rv64i.py does) instead of one Python-level call per instruction —
        # each step() is a GPU dispatch+sync round trip, so 55M individual calls would
        # take hours; batches of 1M cost the same GPU work with negligible host overhead.
        print(f"Fast stepping to 55M...")
        for step in range(0, 55_000_000, 1_000_000):
            core.step(steps=1_000_000)

            if step % 10_000_000 == 0:
                print(f"  {step:,} steps done...")

        print(f"Reached 55M steps, switching to trap monitoring mode...")
        print()

        # Now step in smaller batches, monitoring trap changes
        small_step_size = 100_000
        target_steps = 70_000_000
        steps_done = 55_000_000

        trap_count = 0
        unique_faulting_addrs = set()

        while steps_done < target_steps:
            # Step one small batch
            core.step(steps=small_step_size)
            steps_done += small_step_size

            # Get full state
            state = core.get_state()
            pc = state['pc']
            mode = state['mode']

            # Read CSRs
            mcause = core.read_csr(0x342)  # mcause
            scause = core.read_csr(0x142)  # scause
            stval = core.read_csr(0x143)  # stval
            mtval = core.read_csr(0x343)  # mtval

            # Check if trap state changed (new trap taken)
            trap_changed = False
            if mcause != prev_mcause or scause != prev_scause:
                trap_changed = True
                trap_count += 1
                prev_mcause = mcause
                prev_scause = scause

                # Log the trap event
                log_entry = {
                    'step': steps_done,
                    'pc': f"0x{pc:x}",
                    'mode': int(mode),
                    'mcause': mcause,
                    'scause': scause,
                    'stval': f"0x{stval:x}",
                    'mtval': f"0x{mtval:x}",
                    'stval_dec': stval,
                    'mtval_dec': mtval
                }
                f.write(json.dumps(log_entry) + "\n")

                # Track unique faulting addresses
                if stval != 0:
                    unique_faulting_addrs.add(stval)
                if mtval != 0:
                    unique_faulting_addrs.add(mtval)

            # Progress report every 500K steps
            if steps_done % 500_000 == 0:
                print(f"  {steps_done:,} steps | PC=0x{pc:x} | mode={mode} | mcause={mcause:x} | scause={scause:x} | stval=0x{stval:x} | mtval=0x{mtval:x}")

                if trap_changed:
                    print(f"    ^^^ NEW TRAP DETECTED ^^^")

            # If we detect sustained faulting (same small set of PCs), we can stop early
            if trap_count > 50:
                print(f"Detected {trap_count} trap changes - likely in fault loop, stopping...")
                break

    print()
    print(f"=== Probe Complete ===")
    print(f"Total steps: {steps_done:,}")
    print(f"Trap state changes logged: {trap_count}")
    print(f"Unique faulting addresses: {len(unique_faulting_addrs)}")
    print()
    print(f"Trap log written to: {log_file}")
    print()
    print("Unique faulting addresses:")
    for addr in sorted(unique_faulting_addrs):
        print(f"  0x{addr:x}")


if __name__ == "__main__":
    main()