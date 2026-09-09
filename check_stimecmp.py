#!/usr/bin/env python3
"""
Check STIMECMP (Sstc) value at stall point
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb

print("=" * 70)
print("STIMECMP (Sstc) CHECK AT STALL POINT")
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

# Read CSRs
CSR_STIMECMP = 0x14D
CSR_MIP = 0x134
CSR_MIE = 0x104
CSR_SIE = 0x104
CSR_MSTATUS = 0x300
CSR_TIME = 0xC01

stimecmp = core.read_csr(CSR_STIMECMP)
mtime = core.read_csr(CSR_TIME)
mip = core.read_csr(CSR_MIP)
mie = core.read_csr(CSR_MIE)
mstatus = core.read_csr(CSR_MSTATUS)

print()
print("[3] Timer State:")
print()
print(f"  TIME (timer counter):       0x{mtime:016x} ({mtime:,})")
print(f"  STIMECMP (S-mode timer):    0x{stimecmp:016x} ({stimecmp:,})")
print(f"  MIP (interrupt pending):    0x{mip:016x}")
print(f"  MIE (interrupt enable):     0x{mie:016x}")
print(f"  MSTATUS:                    0x{mstatus:016x}")
print()

# Check if timer should fire
print("[4] Analysis:")

if stimecmp == 0:
    print("  ⚠ STIMECMP is 0 - kernel has not armed S-mode timer!")
    print("    This might be a diagnostic run or the timer is disabled.")
elif mtime >= stimecmp:
    print(f"  ✗ Timer SHOULD HAVE fired: mtime (0x{mtime:x}) >= stimecmp (0x{stimecmp:x})")
    if (mip >> 5) & 1:
        print("  ✓ STIP is set in MIP - timer interrupt is pending")
    else:
        print("  ✗ STIP is NOT set in MIP - bug in timer interrupt generation!")
else:
    print(f"  ⏳ Timer not yet due: mtime (0x{mtime:x}) < stimecmp (0x{stimecmp:x})")
    diff = stimecmp - mtime
    print(f"  Ticks until fire: {diff:,}")
    print(f"    At ~1 tick per instruction, that's ~{diff:,} instructions")

print()
print("[5] Interrupt enable status:")

stie_enabled = (mie >> 5) & 1
sie = (mstatus >> 1) & 1

print(f"  STIE (bit 5 of MIE):  {stie_enabled}")
print(f"  SIE (bit 1 of MSTATUS): {sie}")
print(f"  Current mode: S (1)")

print()
print("[6] Running 1M more steps to see if timer fires...")

initial_mtime = mtime
initial_stip = (mip >> 5) & 1

core.step(steps=1_000_000)

final_mtime = core.read_csr(CSR_TIME)
final_mip = core.read_csr(CSR_MIP)
final_stip = (final_mip >> 5) & 1

print(f"  mtime before:  {initial_mtime:,}")
print(f"  mtime after:   {final_mtime:,}")
print(f"  mtime delta:   {final_mtime - initial_mtime:,}")

if final_mtime > initial_mtime:
    print("  ✓ mtime is incrementing!")
else:
    print("  ✗ mtime is NOT incrementing!")

print()
print(f"  STIP before:   {initial_stip}")
print(f"  STIP after:    {final_stip}")

if final_stip != initial_stip:
    print("  ✗ STIP changed - something is wrong with interrupt handling!")
else:
    print("  ✓ STIP stable")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)
print()
print("If mtime is incrementing but timer never fires, check:")
print("  1. Does the kernel ever set STIMECMP to a non-zero value?")
print("  2. Is STIE bit 5 set in MIE when timer fires?")
print("  3. Is SIE bit 1 set in MSTATUS when in S-mode?")
print("  4. Is maybe_take_interrupt() actually being called on each step?")