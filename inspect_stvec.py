#!/usr/bin/env python3
"""
Check what code is at STVEC (trap handler)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb
import struct
import numpy as np

print("=" * 70)
print("STVEC CODE INSPECTION")
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

# Read STVEC
CSR_STVEC = 0x105
stvec = core.read_csr(CSR_STVEC)

print(f"  STVEC: 0x{stvec:016x}")
print()

# Check STVEC.MODE (bits 1:0)
stvec_mode = stvec & 0x3
stvec_base = stvec & ~0x3

print(f"  STVEC.MODE: {stvec_mode}")
print(f"  STVEC.BASE: 0x{stvec_base:016x}")
print()

mode_names = {0: "Direct", 1: "Vectored"}
print(f"  Trap mode: {mode_names.get(stvec_mode, f'Unknown {stvec_mode}')}")
print()

# Read some instructions from STVEC
print("[3] Reading code at STVEC...")

for i in range(5):
    # Translate virtual address to physical (assuming identity for kernel space)
    phys_addr = stvec_base + i * 4

    # Read from memory (bypassing translation for now)
    try:
        mem_len = core.memory.buffer.size // 4
        N = int((mem_len) ** 0.5)

        # Hilbert mapping
        word_idx = phys_addr // 4
        x, y = core._d2xy(N, word_idx)
        idx = y * N + x

        data = core.queue.read_buffer(core.memory.buffer, buffer_offset=idx * 4, size=4)
        inst = int(np.frombuffer(data, dtype=np.uint32)[0])

        print(f"  0x{stvec_base + i*4:016x}: 0x{inst:08x}")
    except Exception as e:
        print(f"  0x{stvec_base + i*4:016x}: (error: {e})")

print()
print("[4] Checking if we're in the trap handler...")

# Read PC from state
state = core.get_state()
pc = state['pc']
mode = state['mode']

print(f"  Current PC: 0x{pc:016x}")
print(f"  Current mode: {mode}")

# Check if PC is near STVEC
distance = abs(pc - stvec_base)
print(f"  Distance from STVEC: {distance:,}")

if distance < 0x1000:
    print("  ✓ In or near trap handler")
else:
    print("  ✗ NOT in trap handler")

print()
print("[5] Running to see if PC moves...")

initial_pc = pc
for i in range(5):
    core.step(steps=1000)
    state = core.get_state()
    pc = state['pc']
    print(f"  After {(i+1)*1000} steps: PC=0x{pc:016x}")

print()
print("[6] Analysis:")

final_pc = pc
if final_pc == initial_pc:
    print("  ✗ PC did not move - CPU is truly stalled")
    print("  This could be:")
    print("    - An infinite loop in the trap handler")
    print("    - Waiting for something that never happens")
    print("    - Instruction fetch failing (page fault)")
elif abs(final_pc - stvec_base) < 0x1000:
    print("  ⚠ PC moving but stuck in trap handler")
    print("  The handler might have an infinite loop")
else:
    print("  ✓ PC moving normally")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)