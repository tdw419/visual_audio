#!/usr/bin/env python3
"""Minimal diagnostic: run 10k steps and dump the first trap."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from test_alpine_opensbi_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Run until first trap or 100k steps
for i in range(20):
    core.step(steps=5000)
    state = core.get_state()
    if state['trap_pending']:
        print(f"Trap at step {i*5000}:")
        print(f"  pc: 0x{state['pc']:016x}")
        print(f"  mode: {state['mode']}")
        print(f"  mcause: {hex(core.read_csr(0x342))}")
        print(f"  scause: {hex(core.read_csr(0x142))}")

        # Read satp
        satp = core.read_csr(0x180)
        print(f"  satp: 0x{satp:016x}")

        # Try to see what the trap handler does
        core.step(steps=1000)
        state2 = core.get_state()
        print(f"\nAfter trap handler (1k steps):")
        print(f"  pc: 0x{state2['pc']:016x}")
        print(f"  scause: {hex(core.read_csr(0x142))}")

        # Try another step to see if we return
        core.step(steps=5000)
        state3 = core.get_state()
        print(f"\nAfter return attempt (5k steps):")
        print(f"  pc: 0x{state3['pc']:016x}")
        print(f"  scause: {hex(core.read_csr(0x142))}")
        break

uart = core.read_uart_output()
print(f"\nUART output ({len(uart)} bytes):")
print(uart[:500].decode('utf-8', 'replace'))