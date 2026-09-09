#!/usr/bin/env python3
"""
Track MIE/MIP/MSTATUS during boot
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb
import numpy as np

print("=" * 70)
print("TRACK INTERRUPT STATE DURING BOOT")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

CSR_MIP = 0x134
CSR_MIE = 0x104
CSR_MSTATUS = 0x300
CSR_MIDELEG = 0x103

step_intervals = [500000, 1000000, 5000000, 10000000, 20000000, 30000000, 35000000, 40000000]

total_steps = 0
for idx, target in enumerate(step_intervals, 1):
    steps = target - total_steps
    print(f"[{idx}] Running {steps:,} steps (total {target:,})...")
    core.step(steps=steps)

    # Read CSRs
    mip_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_MIP * 8, size=8)
    mip_low, mip_high = np.frombuffer(mip_bytes, dtype=np.uint32)
    mip = (mip_high << 32) | mip_low

    mie_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_MIE * 8, size=8)
    mie_low, mie_high = np.frombuffer(mie_bytes, dtype=np.uint32)
    mie = (mie_high << 32) | mie_low

    mstatus_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_MSTATUS * 8, size=8)
    mstatus_low, mstatus_high = np.frombuffer(mstatus_bytes, dtype=np.uint32)
    mstatus = (mstatus_high << 32) | mstatus_low

    mideleg_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_MIDELEG * 8, size=8)
    mideleg_low, mideleg_high = np.frombuffer(mideleg_bytes, dtype=np.uint32)
    mideleg = (mideleg_high << 32) | mideleg_low

    # Read mtime and stimecmp
    CSR_STIMECMP = 0x14D
    stimecmp_bytes = core.queue.read_buffer(core.csr_buffer, buffer_offset=CSR_STIMECMP * 8, size=8)
    stimecmp_low, stimecmp_high = np.frombuffer(stimecmp_bytes, dtype=np.uint32)
    stimecmp = (stimecmp_high << 32) | stimecmp_low

    state_data = core.queue.read_buffer(core.state_buffer, size=140)
    state_u32 = np.frombuffer(state_data, dtype=np.uint32)
    mtime_low = state_u32[10]
    mtime_high = state_u32[11]
    mtime = (mtime_high << 32) | mtime_low

    # Read timer interrupt counters
    timer_fired = state_u32[30]
    interrupts_delivered = state_u32[31]

    print(f"  MIP:      0x{mip:016x}")
    print(f"  MIE:      0x{mie:016x}")
    print(f"  MSTATUS:  0x{mstatus:016x}")
    print(f"  MIDELEG:  0x{mideleg:016x}")
    print(f"  stimecmp: 0x{stimecmp:016x}")
    print(f"  mtime:    0x{mtime:016x}")
    print(f"  timer_fired: {timer_fired}")
    print(f"  interrupts_delivered: {interrupts_delivered}")

    # Decode MIE
    print(f"  MIE bits: SSIE={mie & 1}, MSIE={(mie>>3)&1}, STIE={(mie>>5)&1}, MTIE={(mie>>7)&1}")

    # Decode MSTATUS
    print(f"  MSTATUS: MIE={(mstatus>>3)&1}, SIE={(mstatus>>1)&1}")

    # Decode MIDELEG
    print(f"  MIDELEG: STIE={(mideleg>>5)&1}, MTIE={(mideleg>>7)&1}")

    print()

    total_steps = target

print("=" * 70)
print("DIAGNOSIS:")
print("=" * 70)
print()

print("Key findings:")
print()
print("1. If MIE is always 0, interrupts are NEVER enabled.")
print("2. If MIDELEG bit 5 (STIE delegation) is 0, timer goes to M-mode, not S-mode.")
print("3. If mtime >= stimecmp but timer_fired = 0, the comparison logic is broken.")
print("4. If timer_fired > 0 but interrupts_delivered = 0, delivery logic is broken.")
print()
print("The kernel MUST enable interrupts by setting MIE bits.")
print("If MIE remains 0, check:")
print("  - Is the kernel setting MIE at all?")
print("  - Is something clearing MIE after it's set?")
print("  - Is csrw MIE instruction working correctly?")