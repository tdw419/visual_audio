#!/usr/bin/env python3
"""
Check timer interrupt counters directly from state
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb
import numpy as np

print("=" * 70)
print("TIMER INTERRUPT COUNTER CHECK")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Read initial state
state_data = core.queue.read_buffer(core.state_buffer, size=140)
state_u32 = np.frombuffer(state_data, dtype=np.uint32)

initial_timer_fired = state_u32[30]
initial_interrupts_delivered = state_u32[31]
initial_mtime_low = state_u32[10]
initial_mtime_high = state_u32[11]
initial_mtime = (initial_mtime_high << 32) | initial_mtime_low

print(f"  Initial timer_interrupts_fired:   {initial_timer_fired}")
print(f"  Initial interrupts_delivered:     {initial_interrupts_delivered}")
print(f"  Initial mtime:                     0x{initial_mtime:016x} ({initial_mtime:,})")

print()
print("[2] Running 1M steps...")

core.step(steps=1_000_000)

# Read final state
state_data = core.queue.read_buffer(core.state_buffer, size=140)
state_u32 = np.frombuffer(state_data, dtype=np.uint32)

final_timer_fired = state_u32[30]
final_interrupts_delivered = state_u32[31]

# Also check mtime
final_mtime_low = state_u32[10]
final_mtime_high = state_u32[11]
final_mtime = (final_mtime_high << 32) | final_mtime_low

final_mtimecmp_low = state_u32[12]
final_mtimecmp_high = state_u32[13]
final_mtimecmp = (final_mtimecmp_high << 32) | final_mtimecmp_low

print(f"  Final timer_interrupts_fired:     {final_timer_fired}")
print(f"  Final interrupts_delivered:       {final_interrupts_delivered}")
print()
print(f"  Final mtime:                       0x{final_mtime:016x} ({final_mtime:,})")
print(f"  Final mtimecmp:                    0x{final_mtimecmp:016x} ({final_mtimecmp:,})")

print()
print("[3] Analysis:")

delta_timer_fired = final_timer_fired - initial_timer_fired
delta_interrupts_delivered = final_interrupts_delivered - initial_interrupts_delivered
delta_mtime = final_mtime - initial_mtime

print(f"  Timer fires in 1M steps:           {delta_timer_fired}")
print(f"  Interrupts delivered:              {delta_interrupts_delivered}")
print(f"  mtime increment:                  {delta_mtime}")

print()

if delta_mtime == 0:
    print("  ✗ CRITICAL: mtime did NOT increment!")
    print("  The timer increment code is broken.")
elif delta_timer_fired == 0:
    print("  ✗ mtime incremented but no timer fires detected")
    if final_mtime >= final_mtimecmp:
        print("  ✗ AND mtime >= mtimecmp - timer SHOULD have fired!")
        print("  Bug in maybe_take_interrupt() or MIP/MIE logic")
    else:
        print("  Timer not due yet: mtime < mtimecmp")
elif delta_interrupts_delivered == 0:
    print("  ⚠ Timer fires but interrupts not delivered")
    print("  Check MIP/MIE/MSTATUS/mideleg logic")
else:
    print(f"  ✓ System seems OK: {delta_interrupts_delivered} interrupts delivered")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)