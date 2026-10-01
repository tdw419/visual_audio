#!/usr/bin/env python3
"""
Deep diagnosis of post-zbud stall

The PC is NOT stuck in a single location - it's moving between ~10 addresses.
This suggests a tight loop or trap/exception cycle.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb

print("=" * 70)
print("DEEP DIAGNOSIS: POST-ZBUD STALL")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Run to zbud message (around 35-40M steps)
print("[2] Running to 40M steps (after zbud loaded)...")
core.step(steps=40_000_000)

uart = core.read_uart_output().decode('utf-8', errors='replace')
if "zbud: loaded" in uart:
    print("  ✓ Reached zbud loaded message")
else:
    print("  ✗ Did not reach zbud")
    print("  Last output:", uart[-200:])

print()
print("[3] Tracing next 100,000 steps with detailed logging...")

# Capture PC sequence, CSRs, and any traps
pc_sequence = []
trap_count = 0
scause_values = {}
sepc_values = {}

CSR_SCAUSE = 0x142
CSR_SEPC = 0x144
CSR_STVAL = 0x143
CSR_SSTATUS = 0x100

for step in range(100000):
    core.step(steps=1)
    state = core.get_state()
    pc = state['pc']
    
    # Only record every 100th step to reduce noise
    if step % 100 == 0:
        pc_sequence.append(pc)
        
        # Check for traps by reading CSRs
        scause = core.read_csr(CSR_SCAUSE)
        if scause != 0 and scause != 0x8000000000000005:  # Not timer interrupt
            trap_count += 1
            scause_values[scause] = scause_values.get(scause, 0) + 1
            sepc = core.read_csr(CSR_SEPC)
            sepc_values[sepc] = sepc_values.get(sepc, 0) + 1
            stval = core.read_csr(CSR_STVAL)
            print(f"  Step {step}: PC=0x{pc:016x}, TRAP! scause=0x{scause:016x}, sepc=0x{sepc:016x}, stval=0x{stval:016x}")

print()
print(f"Traps detected: {trap_count}")
if scause_values:
    print("Unique SCAUSE values:")
    for scause, count in scause_values.items():
        print(f"  0x{scause:016x}: {count} times")

print()
print("[4] Analyzing PC pattern...")

# Group PCs by similarity (functions)
from collections import Counter
pc_counter = Counter(pc_sequence)

print("Top 20 PCs:")
for pc, count in pc_counter.most_common(20):
    print(f"  0x{pc:016x}: {count} times")

print()
print("[5] Reading memory at frequent PC locations...")

# Read instruction bytes at frequent PCs
frequent_pcs = [pc for pc, _ in pc_counter.most_common(5)]
for pc in frequent_pcs:
    # Read 4 instructions (16 bytes) at each location
    try:
        # Translate PC to physical address using SATP
        satp = core.read_csr(CSR_SATP)
        if satp == 0:
            # No translation
            phys_addr = pc
        else:
            # Sv39 translation: ppn = VPN + physical base
            # For now, assume identity for kernel space
            phys_addr = pc
        
        # Read bytes from spatial memory
        mem_bytes = core._gpu_context.read_buffer(phys_addr & 0xFFFFFFFF, 16)
        if mem_bytes:
            print(f"  0x{pc:016x}: " + " ".join(f"{b:02x}" for b in mem_bytes))
    except Exception as e:
        print(f"  0x{pc:016x}: (error: {e})")

print()
print("[6] Running 1M more steps and checking forward progress...")

initial_steps = 40_000_000
core.step(steps=1_000_000)
final_state = core.get_state()
final_uart = core.read_uart_output().decode('utf-8', errors='replace')

print(f"  Initial steps: {initial_steps:,}")
print(f"  Final steps: {initial_steps + 1_000_000:,}")
print(f"  UART bytes before: {len(uart):,}")
print(f"  UART bytes after: {len(final_uart):,}")
print(f"  UART delta: {len(final_uart) - len(uart):,}")

if len(final_uart) - len(uart) < 100:
    print("  ✗ STALLED: Minimal UART progress over 1M steps")
    print("  Last 200 chars of UART:", final_uart[-200:])
else:
    print("  ✓ Making progress")
    print("  New output:", final_uart[-(len(final_uart) - len(uart)):])

print()
print("[7] Analyzing TLB behavior...")

initial_state = core.get_state()
initial_hits = initial_state['tlb_hits']
initial_misses = initial_state['tlb_misses']

print(f"  TLB hits at 40M: {initial_hits:,}")
print(f"  TLB misses at 40M: {initial_misses:,}")
print(f"  TLB hit rate: {initial_hits / (initial_hits + initial_misses) * 100:.2f}%")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)