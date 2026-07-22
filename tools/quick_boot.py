#!/usr/bin/env python3
"""
Run a short boot to see UART output.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Use boot_xv6_gpu.py but with a short timeout
from boot_xv6_gpu import boot_xv6_on_gpu, create_gpu_hardware, make_cpu_state, ELF64Loader
import numpy as np
import wgpu
import wgpu.utils
import struct

kernel_path = '/tmp/xv6-riscv/kernel/kernel'
elf = ELF64Loader(kernel_path)

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

# Load fs.img
fs_img_path = Path('/tmp/xv6-riscv/fs.img')
if fs_img_path.exists():
    fs_data = fs_img_path.read_bytes()
    fs_offset = 0x81000000 - PHYS_START
    start_pixel = fs_offset // 4
    start_byte = fs_offset % 4

    if start_byte == 0:
        word_count = (len(fs_data) + 3) // 4
        byte_data = np.frombuffer(fs_data, dtype=np.uint8)
        padded_len = word_count * 4
        if len(byte_data) < padded_len:
            padded = np.zeros(padded_len, dtype=np.uint8)
            padded[:len(byte_data)] = byte_data
            byte_data = padded
        pixel_data = byte_data.reshape(-1, 4)
        memory[start_pixel:start_pixel + word_count] = pixel_data
    else:
        for i, byte in enumerate(fs_data):
            pixel_idx = (fs_offset + i) // 4
            byte_idx = (fs_offset + i) % 4
            memory[pixel_idx, byte_idx] = byte

cpu_state = make_cpu_state(elf.entry_point, priv_mode=3)
harness = create_gpu_hardware(memory, cpu_state, 2_000_000)

print("Running 5M instructions...")
for i in range(3):
    device = harness['device']
    queue = harness['queue']
    
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(harness['pipeline'])
    pass_enc.set_bind_group(0, harness['bind_group'])
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])
    
    cpu_readback_bytes = queue.read_buffer(harness['cpu_buffer'])
    from riscv_gpu_cpu import CPU_DTYPE
    cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=CPU_DTYPE)
    pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
    running = int(cpu_readback['running'][0])
    
    print(f"Iter {i}: PC=0x{pc:016x}, running={running}")
    
    if not running:
        break

# Read UART output
output_data = np.frombuffer(
    device.queue.read_buffer(harness['output_buffer']),
    dtype=np.uint8
)

output_str = ''
for i in range(0, 16384, 4):
    word = struct.unpack('<I', output_data[i:i+4])[0]
    for b in word.to_bytes(4, 'little'):
        if b == 0:
            break
        if 32 <= b < 127 or b == ord('\n') or b == ord('\r'):
            output_str += chr(b)

print("\n" + "=" * 70)
print("UART OUTPUT:")
print("=" * 70)
print(output_str)
print("=" * 70)