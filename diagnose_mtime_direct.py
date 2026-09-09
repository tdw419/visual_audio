#!/usr/bin/env python3
"""
Check mtime directly from state buffer at stall point
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb
import numpy as np

print("=" * 70)
print("DIRECT STATE BUFFER MTIME CHECK")
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
print("[3] Reading state buffer directly...")
state_data = core.queue.read_buffer(core.state_buffer, size=60 * 4)  # Read first 60 u32s
state_u32 = np.frombuffer(state_data, dtype=np.uint32)

# State structure (from WGSL):
# 0: halted
# 1-2: pc_low, pc_high
# 3: mode
# 4: trap_pending
# 5: instr_len
# 6-7: last_d2idx_d (unused in new version)
# 8: last_d2idx_result (unused)
# 9: bb_total_insts
# 10: bb_ctl_insts
# 11: bb_fallback_insts
# 12: steps_remaining
# 13: bb_threaded_insts
# 14: bb_threading_enabled
# 15: tlb_hits (low)
# 16: tlb_hits (high)
# 17: tlb_misses (low)
# 18: tlb_misses (high)
# ...
# mtime_low and mtime_high are at specific offsets

print("  State buffer u32 dump (first 40 words):")
for i in range(min(40, len(state_u32))):
    print(f"    [{i:2d}]: 0x{state_u32[i]:08x}")

print()

# From the WGSL struct, I need to find where mtime is in the state
# Let me search for it
print("[4] Checking where mtime is in state structure...")

# The state struct in WGSL starts with:
# var state: CPUState;
# CPUState has:
# halted, pc, mode, trap_pending, instr_len, last_d2idx_d, last_d2idx_result,
# bb_total_insts, bb_ctl_insts, bb_fallback_insts, steps_remaining,
# bb_threaded_insts, bb_threading_enabled, tlb_hits, tlb_misses,
# trap_count, reservation_addr, reservation_valid, uart_tx_len,
# mtime_low, mtime_high, mtimecmp_low, mtimecmp_high,
# ram_base_low, ram_base_high, uart_rx_data_pending, uart_rx_byte,
# decoded_ops_epoch, last_killed_pc, last_killed_len

# Count the fields before mtime:
# 0: halted (u32)
# 1: pc_low (u32)
# 2: pc_high (u32)
# 3: mode (u32)
# 4: trap_pending (u32)
# 5: instr_len (u32)
# 6-7: last_d2idx_d (vec2<u32>)
# 8: last_d2idx_result (u32)
# 9: bb_total_insts (u32)
# 10: bb_ctl_insts (u32)
# 11: bb_fallback_insts (u32)
# 12: steps_remaining (u32)
# 13: bb_threaded_insts (u32)
# 14: bb_threading_enabled (u32)
# 15-16: tlb_hits (vec2<u32>)
# 17-18: tlb_misses (vec2<u32>)
# 19-21: trap_count, reservation_addr_low, reservation_addr_high
# 22: reservation_valid (u32)
# 23: uart_tx_len (u32)
# 24: mtime_low (u32)
# 25: mtime_high (u32)
# 26: mtimecmp_low (u32)
# 27: mtimecmp_high (u32)
# 28: ram_base_low (u32)
# 29: ram_base_high (u32)
# 30: uart_rx_data_pending (u32)
# 31: uart_rx_byte (u32)

mtime_low_idx = 24
mtime_high_idx = 25

mtime_low = state_u32[mtime_low_idx]
mtime_high = state_u32[mtime_high_idx]

print(f"  mtime_low (state[{mtime_low_idx}]):  0x{mtime_low:08x} ({mtime_low:,})")
print(f"  mtime_high (state[{mtime_high_idx}]): 0x{mtime_high:08x}")

mtime = (mtime_high << 32) | mtime_low
print(f"  mtime (combined): 0x{mtime:016x} ({mtime:,})")

print()

# Also check mtimecmp
mtimecmp_low_idx = 26
mtimecmp_high_idx = 27
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

# PC is at indices 1-2
pc_low = state_u32[1]
pc_high = state_u32[2]
pc = (pc_high << 32) | pc_low

# Mode is at index 3
mode = state_u32[3]

# Halted is at index 0
halted = state_u32[0]

print(f"  PC:   0x{pc:016x}")
print(f"  Mode: {mode} (3=M, 1=S, 0=U)")
print(f"  Halted: {halted}")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)