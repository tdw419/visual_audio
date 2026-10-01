#!/usr/bin/env python3
"""
Run up to 50M instructions to reach timerinit().
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))
import numpy as np
import wgpu
import wgpu.utils

# Minimal boot harness setup
MEMORY_SIZE_MB = 128
MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
PHYS_START = 0x80000000
pixel_count = MEMORY_SIZE // 4

# Load kernel using boot_xv6_gpu's loader
import boot_xv6_gpu
elf = boot_xv6_gpu.ELF64Loader('/tmp/xv6-riscv/kernel/kernel')

# Load segments into memory
pixel_data = np.zeros((pixel_count, 4), dtype=np.uint32)
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
        pixel_data[start_pixel:start_pixel + word_count] = byte_data.reshape(-1, 4)
    else:
        for i, byte in enumerate(data):
            pixel_idx = (offset + i) // 4
            byte_idx = (offset + i) % 4
            pixel_data[pixel_idx, byte_idx] = byte

# Create CPU state
from riscv_gpu_cpu import make_cpu_state
cpu_state = make_cpu_state(elf.entry_point, priv_mode=3)

# Setup GPU
device = wgpu.utils.get_default_device()
queue = device.queue

# Create buffers
memory_buffer = device.create_buffer(
    size=pixel_data.nbytes,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)
cpu_buffer = device.create_buffer(
    size=cpu_state.nbytes,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)
output_buffer = device.create_buffer(
    size=65536,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
)
input_buffer = device.create_buffer(
    size=1024,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    mapped_at_creation=False,
)
# Use 5M instructions per dispatch
max_instr_arr = np.array([5000000], dtype=np.uint32)
uniform_buffer = device.create_buffer(
    size=max_instr_arr.nbytes,
    usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
)

# Upload initial data
queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
queue.write_buffer(uniform_buffer, 0, max_instr_arr.tobytes())
queue.write_buffer(input_buffer, 0, np.zeros(256, dtype=np.uint32).tobytes())

# Bind group
bind_group_layout = device.create_bind_group_layout(entries=[
    {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
    {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
    {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
    {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
])

bind_group = device.create_bind_group(
    layout=bind_group_layout,
    entries=[
        {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': pixel_data.nbytes}},
        {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 65536}},
        {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instr_arr.nbytes}},
        {'binding': 4, 'resource': {'buffer': input_buffer, 'offset': 0, 'size': 1024}},
    ]
)

# Load shader
shader_path = Path(__file__).parent / 'tools' / 'RISCV_CPU_MMU.wgsl'
shader_code = shader_path.read_text()
compute_shader = device.create_shader_module(code=shader_code)
pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
pipeline = device.create_compute_pipeline(
    layout=pipeline_layout,
    compute={'module': compute_shader, 'entry_point': 'main'},
)

from riscv_gpu_cpu import CPU_DTYPE

# Track state
last_mtimecmp = 0
last_irq = 0

# Run 10 dispatches (up to 50M instructions)
print("Running up to 50M instructions (10 dispatches x 5M each)...")
for iteration in range(10):
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(pipeline)
    pass_enc.set_bind_group(0, bind_group)
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])
    
    cpu_readback_bytes = queue.read_buffer(cpu_buffer)
    cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=CPU_DTYPE)
    pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
    running = cpu_readback['running'][0]
    timer_irq_count = cpu_readback['timer_interrupt_count'][0]
    total_irq_count = cpu_readback['total_interrupt_count'][0]
    instr_count = cpu_readback['instr_count'][0]
    mtimecmp_low = cpu_readback['mtimecmp_low'][0]
    mtimecmp_high = cpu_readback['mtimecmp_high'][0]
    mtimecmp = (mtimecmp_high << 32) | mtimecmp_low
    
    # Check for timer arm
    if mtimecmp != last_mtimecmp:
        print(f"\n  [{instr_count:8d} instrs] Timer armed: mtimecmp = 0x{mtimecmp:016x}")
        last_mtimecmp = mtimecmp
    
    # Check for interrupt
    if total_irq_count != last_irq:
        print(f"  [{instr_count:8d} instrs] Interrupt! total_irq={total_irq_count}")
        last_irq = total_irq_count
    
    print(f"  Iter {iteration}: {instr_count:8d} instrs, PC=0x{pc:08x}, timer_irq={timer_irq_count}, total_irq={total_irq_count}, mtimecmp=0x{mtimecmp:016x}")
    
    if running == 0:
        print(f"\nCPU stopped after {instr_count} instructions")
        break

print(f"\nDone! Final state: {instr_count} instrs, timer_irq={timer_irq_count}, total_irq={total_irq_count}")