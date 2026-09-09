#!/usr/bin/env python3
"""
Check mtime directly from state buffer at stall point (fixed version)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb
import numpy as np

print("=" * 70)
print("DIRECT STATE BUFFER MTIME CHECK (FIXED)")
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

# Read state buffer directly
# State buffer is 140 bytes = 35 u32s
print("[3] Reading state buffer directly...")
state_data = core.queue.read_buffer(core.state_buffer, size=140)
state_u32 = np.frombuffer(state_data, dtype=np.uint32)

print(f"  State buffer has {len(state_u32)} u32s (expected 35)")

# CPUState struct layout (from WGSL):
# 0: pc_low
# 1: pc_high
# 2: halted
# 3: steps_remaining
# 4: mode
# 5: trap_pending
# 6: reservation_valid
# 7: reservation_addr_low
# 8: reservation_addr_high
# 9: uart_tx_len
# 10: mtime_low
# 11: mtime_high
# 12: mtimecmp_low
# 13: mtimecmp_high
# 14: ram_base_low
# 15: ram_base_high
# 16: uart_rx_data_pending
# 17: uart_rx_byte
# 18: instr_len
# 19: last_d2idx_d
# 20: last_d2idx_result
# 21-22: _pad[2]
# 23: bb_total_insts
# 24: bb_ctl_insts
# 25: bb_fallback_insts
# 26: bb_threaded_insts
# 27: bb_threading_enabled
# 28: tlb_hits
# 29: tlb_misses
# 30: timer_interrupts_fired
# 31: interrupts_delivered
# 32: sbi_ecall_console
# 33: sbi_ecall_time
# 34: sbi_ecall_unknown

print()
print("  State buffer u32 dump:")
for i in range(len(state_u32)):
    print(f"    [{i:2d}]: 0x{state_u32[i]:08x}")

print()

# Extract mtime fields
mtime_low_idx = 10
mtime_high_idx = 11

mtime_low = state_u32[mtime_low_idx]
mtime_high = state_u32[mtime_high_idx]

print(f"  mtime_low (state[{mtime_low_idx}]):  0x{mtime_low:08x} ({mtime_low:,})")
print(f"  mtime_high (state[{mtime_high_idx}]): 0x{mtime_high:08x}")

mtime = (mtime_high << 32) | mtime_low
print(f"  mtime (combined): 0x{mtime:016x} ({mtime:,})")

print()

# Also check mtimecmp
mtimecmp_low_idx = 12
mtimecmp_high_idx = 13
mtimecmp_low = state_u32[mtimecmp_low_idx]
mtimecmp_high = state_u32[mtimecmp_high_idx]

print(f"  mtimecmp_low (state[{mtimecmp_low_idx}]):  0x{mtimecmp_low:08x} ({mtimecmp_low:,})")
print(f"  mtimecmp_high (state[{mtimecmp_high_idx}]): 0x{mtimecmp_high:08x}")

mtimecmp = (mtimecmp_high << 32) | mtimecmp_low
print(f"  mtimecmp (combined): 0x{mtimecmp:016x} ({mtimecmp:,})")

print()
print("[5] Analysis:")

if mtime == 0:
    print("  ✗ BUG CONFIRMED: mtime is 0 after 40M steps!")
    print("  The timer is NOT incrementing.")
    print()
    print("  Root cause: mtime increment code is not executing")
    print("  or mtime is being reset somewhere.")
elif mtime >= mtimecmp:
    print(f"  ✓ Timer SHOULD have fired: mtime (0x{mtime:x}) >= mtimecmp (0x{mtimecmp:x})")
else:
    print(f"  ⏳ Timer not yet due: mtime (0x{mtime:x}) < mtimecmp (0x{mtimecmp:x})")
    diff = mtimecmp - mtime
    print(f"  Ticks until fire: {diff:,}")

print()
print("[6] Checking PC and mode...")

# PC is at indices 0-1
pc_low = state_u32[0]
pc_high = state_u32[1]
pc = (pc_high << 32) | pc_low

# Mode is at index 4
mode = state_u32[4]

# Halted is at index 2
halted = state_u32[2]

print(f"  PC:   0x{pc:016x}")
print(f"  Mode: {mode} (3=M, 1=S, 0=U)")
print(f"  Halted: {halted}")

print()
print("[7] Basic block counters:")
bb_total = state_u32[23]
bb_ctl = state_u32[24]
bb_fallback = state_u32[25]
bb_threaded = state_u32[26]
bb_threading_enabled = state_u32[27]

print(f"  bb_total_insts:       {bb_total:,}")
print(f"  bb_ctl_insts:         {bb_ctl:,}")
print(f"  bb_fallback_insts:    {bb_fallback:,}")
print(f"  bb_threaded_insts:    {bb_threaded:,}")
print(f"  bb_threading_enabled: {bb_threading_enabled}")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)