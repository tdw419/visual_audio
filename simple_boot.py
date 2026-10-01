#!/usr/bin/env python3
"""
Single-run boot to capture panic.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

# Initialize core
core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)

# Load OpenSBI + Alpine + DTB
load_opensbi_alpine_and_dtb(core)

print(f"  [x] Running boot...")

# Single 10M step run
core.step(10000000)

# Read UART
uart = core.read_uart_output()
print(f"\n  [x] UART ({len(uart)} bytes):")
print("="*80)
if uart:
    decoded = uart.decode('utf-8', errors='replace')
    print(decoded)
else:
    print("(no output)")

print("="*80)

# Final state
state = core.get_state()
mode_names = {0: 'U', 1: 'S', 3: 'M'}
print(f"\n  [x] PC: 0x{state['pc']:x}, Mode: {mode_names.get(state['mode'], state['mode'])}")

regs = state['regs']
sp_low = regs[2][0]
sp_high = regs[2][1]
sp = sp_low | (sp_high << 32)
print(f"  [x] SP: 0x{sp:x}")