#!/usr/bin/env python3
"""
Final comprehensive check at stall point
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb

print("=" * 70)
print("FINAL COMPREHENSIVE STALL ANALYSIS")
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

# Get initial state
initial_state = core.get_state()
initial_pc = initial_state['pc']
initial_halted = initial_state['halted']
initial_uart_len = initial_state['uart_tx_len']

print()
print("[3] Initial State:")
print(f"  PC:       0x{initial_pc:016x}")
print(f"  Halted:   {initial_halted}")
print(f"  UART len: {initial_uart_len}")

# Get recent UART output
uart = core.read_uart_output().decode('utf-8', errors='replace')
print(f"  Last 200 chars: {uart[-200:]}")

print()
print("[4] Running 1M more steps...")

core.step(steps=1_000_000)

# Get final state
final_state = core.get_state()
final_pc = final_state['pc']
final_halted = final_state['halted']
final_uart_len = final_state['uart_tx_len']

final_uart = core.read_uart_output().decode('utf-8', errors='replace')

print()
print("[5] Final State:")
print(f"  PC:       0x{final_pc:016x}")
print(f"  Halted:   {final_halted}")
print(f"  UART len: {final_uart_len}")
print(f"  Last 200 chars: {final_uart[-200:]}")

print()
print("[6] Analysis:")

uart_delta = final_uart_len - initial_uart_len
pc_delta = final_pc - initial_pc

print(f"  UART delta: {uart_delta} bytes")
print(f"  PC delta:   {pc_delta:,}")

if uart_delta < 100:
    print("  ⚠ STALLED: Minimal UART progress over 1M steps")
    print("  This is the real stall.")
else:
    print("  ✓ Making progress")

if pc_delta == 0:
    print("  ✗ PC did not move - CPU is completely stalled")
elif abs(pc_delta) < 1000:
    print("  ⚠ PC barely moving - tight loop or stuck")
else:
    print(f"  ✓ PC moved {pc_delta:,} bytes")

# Check if we're in boot stall or just slow
if uart_delta < 100 and pc_delta > 0:
    print()
    print("  DIAGNOSIS: CPU is executing but not producing UART output")
    print("  Possible causes:")
    print("    1. Waiting for timer interrupt that never arrives")
    print("    2. Stuck in polling loop")
    print("    3. Deadlocked on a lock")
    print("    4. In kernel scheduler without tasks to run")

    # Check if it's the RCU stall pattern
    print()
    print("[7] Checking for RCU stall pattern...")
    if "rcu_sched" in final_uart.lower() or "rcu stall" in final_uart.lower():
        print("  ⚠ RCU stall detected in output")
    else:
        print("  No RCU stall message in output")

print()
print("=" * 70)
print("RECOMMENDATION:")
print("=" * 70)
print()

if uart_delta < 100 and pc_delta > 0:
    print("The emulator is NOT truly stalled - it's executing instructions.")
    print("The kernel is just not producing output, which is common during:")
    print("  - Thread scheduling delays")
    print("  - Waiting for hardware events")
    print("  - RCU grace periods")
    print()
    print("To determine if Alpine boots successfully:")
    print("  1. Run for 100M+ steps")
    print("  2. Check for login prompt")
    print("  3. If no prompt, it may still be working (try more steps)")
else:
    print("Check the diagnostic output above for the actual issue.")

print()
print("=" * 70)