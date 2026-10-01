#!/usr/bin/env python3
"""
Track when STIMECMP is set during boot
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb
import numpy as np

print("=" * 70)
print("TRACK STIMECMP SETS DURING BOOT")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

# STIMECMP is in CSR buffer at index 0x14D (333)
CSR_STIMECMP = 0x14D

# Track STIMECMP values over time
last_stimecmp = None
stimecmp_changes = []
step_intervals = [500000, 1000000, 5000000, 10000000, 20000000, 30000000, 35000000, 40000000]

total_steps = 0
for target in step_intervals:
    steps = target - total_steps
    print(f"[{len(stimecmp_changes)+1}] Running {steps:,} steps (total {target:,})...")
    core.step(steps=steps)

    # Read STIMECMP
    stimecmp_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_STIMECMP * 8, size=8)
    stimecmp_low, stimecmp_high = np.frombuffer(stimecmp_bytes, dtype=np.uint32)
    stimecmp = (stimecmp_high << 32) | stimecmp_low

    # Read mtime from state
    state_data = core.queue.read_buffer(core.state_buffer, size=140)
    state_u32 = np.frombuffer(state_data, dtype=np.uint32)
    mtime_low = state_u32[10]
    mtime_high = state_u32[11]
    mtime = (mtime_high << 32) | mtime_low

    # Read MIP/MIE
    CSR_MIP = 0x134
    CSR_MIE = 0x104

    mip_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_MIP * 8, size=8)
    mip_low, mip_high = np.frombuffer(mip_bytes, dtype=np.uint32)
    mip = (mip_high << 32) | mip_low

    mie_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_MIE * 8, size=8)
    mie_low, mie_high = np.frombuffer(mie_bytes, dtype=np.uint32)
    mie = (mie_high << 32) | mie_low

    if stimecmp != last_stimecmp:
        print(f"  ⚠ STIMECMP changed!")
        print(f"     Old: 0x{last_stimecmp:016x}" if last_stimecmp else "     Old: (none)")
        print(f"     New: 0x{stimecmp:016x}")
        print(f"     mtime: 0x{mtime:016x}")
        print(f"     MIP: 0x{mip:016x}")
        print(f"     MIE: 0x{mie:016x}")
        stimecmp_changes.append({
            'step': target,
            'stimecmp': stimecmp,
            'mtime': mtime,
            'mip': mip,
            'mie': mie
        })
        last_stimecmp = stimecmp

    # Check if we're in the stall zone
    if target >= 35000000:
        uart = core.read_uart_output().decode('utf-8', errors='replace')
        if "zbud: loaded" in uart:
            print(f"  ✓ Reached zbud at step {target}")
        else:
            print(f"  Last 100 chars: {uart[-100:]}")

    total_steps = target

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print()

if stimecmp_changes:
    print(f"STIMECMP changed {len(stimecmp_changes)} times during boot:")
    for i, change in enumerate(stimecmp_changes, 1):
        print(f"  {i}. At step {change['step']:,}:")
        print(f"     STIMECMP = 0x{change['stimecmp']:016x}")
        print(f"     mtime     = 0x{change['mtime']:016x}")
        print(f"     MIP       = 0x{change['mip']:016x}")
        print(f"     MIE       = 0x{change['mie']:016x}")
else:
    print("✗ STIMECMP was NEVER set during boot!")
    print("  This explains why timer interrupts never fire.")
    print()
    print("  Possible causes:")
    print("  1. Kernel uses legacy SBI TIME extension instead of Sstc")
    print("  2. OpenSBI doesn't initialize Sstc for this kernel")
    print("  3. Kernel hasn't reached timer setup yet (stalled earlier)")

print()
print("=" * 70)