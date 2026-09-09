#!/usr/bin/env python3
"""
Debug script to capture CSR state at stall during Alpine boot
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

print("=" * 70)
print("CSR STATE DEBUG DURING ALPINE BOOT")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(RAM_SIZE)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)
print()

# Run to near stall point (around 40M steps)
print("[2] Running to 40M steps (past initramfs unpack start)...")
core.step(steps=40_000_000)

# Get state
state = core.get_state()
uart = core.read_uart_output().decode('utf-8', errors='replace')

print(f"  PC: 0x{state['pc']:016x}")
print(f"  Mode: {state['mode']} ({'M' if state['mode'] == 3 else 'S' if state['mode'] == 1 else 'U'})")
print(f"  Halted: {state['halted'] != 0}")
print(f"  Trap pending: {state['trap_pending'] != 0}")
print(f"  TLB hits: {int(state['tlb_hits'])}")
print(f"  TLB misses: {int(state['tlb_misses'])}")
print()

# Read CSRs
CSR_MCAUSE = 0x342
CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x144
CSR_SATP = 0x180

mcause = core.read_csr(CSR_MCAUSE)
scause = core.read_csr(CSR_SCAUSE)
stval = core.read_csr(CSR_STVAL)
sepc = core.read_csr(CSR_SEPC)
satp = core.read_csr(CSR_SATP)

print("CSR STATE:")
print(f"  mcause = 0x{mcause:016x}")
print(f"  scause = 0x{scause:016x}")
print(f"  stval  = 0x{stval:016x}")
print(f"  sepc   = 0x{sepc:016x}")
print(f"  satp   = 0x{satp:016x}")
print()

# Decode scause
if scause != 0:
    is_interrupt = (scause >> 63) != 0
    exc_code = scause & 0x7FFFFFFF

    exc_names = {
        0: "instruction address misaligned",
        1: "instruction access fault",
        2: "illegal instruction",
        3: "breakpoint",
        4: "load address misaligned",
        5: "load access fault",
        6: "store/AMO address misaligned",
        7: "store/AMO access fault",
        8: "ecall from U-mode",
        9: "ecall from S-mode",
        12: "instruction page fault",
        13: "load page fault",
        15: "store/AMO page fault",
    }

    exc_name = exc_names.get(exc_code, f"unknown {exc_code}")
    print(f"  SCAUSE decoded: {'interrupt' if is_interrupt else 'exception'} {exc_code} ({exc_name})")
    print()

# Show recent UART
print("RECENT UART OUTPUT (last 500 chars):")
print("-" * 70)
if len(uart) > 500:
    print(uart[-500:])
else:
    print(uart)
print("-" * 70)
print()

# Continue for a few more steps to see if we're stuck
print("[3] Running 10 more batches of 1M steps each, checking for stall...")
last_pc = state['pc']
pc_changes = 0
stuck_count = 0

for i in range(10):
    core.step(steps=1_000_000)
    new_state = core.get_state()
    if new_state['pc'] != last_pc:
        pc_changes += 1
        last_pc = new_state['pc']
    else:
        stuck_count += 1

    print(f"  Batch {i+1}: PC=0x{new_state['pc']:016x}, "
          f"{'STUCK' if new_state['pc'] == last_pc else 'OK'}")

print()
print(f"PC changed in {pc_changes}/10 batches, stuck in {stuck_count}/10 batches")

if stuck_count > 7:
    print("\n!! STALLED: PC is not progressing")
    # Final CSR check at stall
    final_scause = core.read_csr(CSR_SCAUSE)
    final_stval = core.read_csr(CSR_STVAL)
    final_sepc = core.read_csr(CSR_SEPC)
    print(f"Final stall state: scause=0x{final_scause:x}, stval=0x{final_stval:x}, sepc=0x{final_sepc:x}")