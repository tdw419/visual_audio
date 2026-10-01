#!/usr/bin/env python3
"""
Check SCAUSE at stall point to see what trap happened last
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb

print("=" * 70)
print("TRAP STATE CHECK AT STALL")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Run to stall point
print("[2] Running to 40M steps (after zbud loaded)...")
core.step(steps=40_000_000)

# Read trap-related CSRs
CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x144
CSR_STVEC = 0x105
CSR_SSTATUS = 0x100

scause = core.read_csr(CSR_SCAUSE)
stval = core.read_csr(CSR_STVAL)
sepc = core.read_csr(CSR_SEPC)
stvec = core.read_csr(CSR_STVEC)
sstatus = core.read_csr(CSR_SSTATUS)

print()
print("[3] Trap State:")
print()
print(f"  SCAUSE: 0x{scause:016x}")
print(f"  STVAL:  0x{stval:016x}")
print(f"  SEPC:   0x{sepc:016x}")
print(f"  STVEC:  0x{stvec:016x}")
print(f"  SSTATUS: 0x{sstatus:016x}")
print()

# Decode SCAUSE
is_interrupt = (scause >> 63) != 0
exc_code = scause & 0x7FFFFFFF

print("[4] SCAUSE Decoding:")
print(f"  Is interrupt: {is_interrupt}")
print(f"  Exception code: {exc_code}")

if is_interrupt:
    exc_names = {
        1: "Supervisor software interrupt (SSIP)",
        3: "Machine software interrupt (MSIP)",
        5: "Supervisor timer interrupt (STIP)",
        7: "Machine timer interrupt (MTIP)",
        9: "Supervisor external interrupt (SEIP)",
        11: "Machine external interrupt (MEIP)",
    }
    print(f"  Interrupt type: {exc_names.get(exc_code, f'Unknown {exc_code}')}")
else:
    exc_names = {
        0: "Instruction address misaligned",
        1: "Instruction access fault",
        2: "Illegal instruction",
        3: "Breakpoint",
        4: "Load address misaligned",
        5: "Load access fault",
        6: "Store/AMO address misaligned",
        7: "Store/AMO access fault",
        8: "Ecall from U-mode",
        9: "Ecall from S-mode",
        12: "Instruction page fault",
        13: "Load page fault",
        15: "Store/AMO page fault",
    }
    print(f"  Exception type: {exc_names.get(exc_code, f'Unknown {exc_code}')}")

print()
print("[5] Running 100 more steps to see if trap continues...")

initial_scause = scause
initial_sepc = sepc

core.step(steps=100)

scause = core.read_csr(CSR_SCAUSE)
sepc = core.read_csr(CSR_SEPC)

print(f"  After 100 steps:")
print(f"    SCAUSE: 0x{scause:016x}")
print(f"    SEPC:   0x{sepc:016x}")

if scause == initial_scause and sepc == initial_sepc:
    print("  ⚠ Stuck in same trap!")
else:
    print("  ✓ Trap state changed")

print()
print("[6] Analysis:")

if scause == 0:
    print("  No pending trap - CPU is not in trap handler")
else:
    if is_interrupt:
        if exc_code == 5:
            print("  In STIP (timer) interrupt handler")
            print("  Check if STVEC points to valid code")
        elif exc_code == 9:
            print("  In SSIP (software) interrupt handler")
        else:
            print(f"  In interrupt handler for type {exc_code}")
    else:
        print(f"  In exception handler: {exc_names.get(exc_code, str(exc_code))}")
        if exc_code in [5, 7, 13, 15]:
            print("  Memory access fault - check page tables and permissions")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)