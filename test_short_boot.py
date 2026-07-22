#!/usr/bin/env python3
"""
Test boot with very short instruction limit.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))
from boot_xv6_gpu import boot_xv6_on_gpu, create_gpu_hardware, create_cpu_state
from ELF64Loader import ELF64Loader
import numpy as np

# Load kernel
elf = ELF64Loader('/tmp/xv6-riscv/kernel/kernel')

# Setup with 1000 instruction limit
print("Creating GPU harness with 1000 instruction limit...")

# Create CPU state
cpu_state = create_cpu_state(elf.entry_point)

# Create memory
MEMORY_SIZE_MB = 128
MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
PHYS_START = 0x80000000
pixel_count = MEMORY_SIZE // 4
memory = np.zeros((pixel_count, 4), dtype=np.uint32)

for seg in elf.get_loadable_segments():
    offset = seg['p_vaddr'] - PHYS_START
    if offset < 0 or offset + seg['p_memsz'] > MEMORY_SIZE:
        continue
    data = elf.get_segment_data(seg)
    start_pixel = offset // 4
    start_byte = offset % 4

    if start_byte == 0:
        word_count = (len(data) + 3) // 4
        byte_data = np.frombuffer(data, dtype=np.uint8)
        padded_len = word_count * 4
        if len(byte_data) < padded_len:
            padded = np.zeros(padded_len, dtype=np.uint8)
            padded[:len(byte_data)] = byte_data
            byte_data = padded
        pixel_data = byte_data.reshape(-1, 4)
        memory[start_pixel:start_pixel + word_count] = pixel_data
    else:
        for i, byte in enumerate(data):
            pixel_idx = (offset + i) // 4
            byte_idx = (offset + i) % 4
            memory[pixel_idx, byte_idx] = byte

# Create harness
print("Creating GPU harness...")
harness = create_gpu_hardware(memory, cpu_state, max_instructions=1000)

print("Running 1000 instructions...")

import wgpu.utils
device = wgpu.utils.get_default_device()
queue = device.queue

# Run a few iterations
for i in range(5):
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(harness['pipeline'])
    pass_enc.set_bind_group(0, harness['bind_group'])
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])

    # Read CPU state
    from riscv_gpu_cpu import CPU_DTYPE
    cpu_readback = np.frombuffer(
        queue.read_buffer(harness['cpu_buffer']),
        dtype=CPU_DTYPE
    )
    pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
    running = int(cpu_readback['running'][0])
    instr_count = int(cpu_readback['instr_count'][0])
    
    print(f"  Iter {i}: PC=0x{pc:08x}, running={running}, instr={instr_count}")

print("\nDone!")