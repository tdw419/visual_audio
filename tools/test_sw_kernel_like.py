#!/usr/bin/env python3
"""
Minimal SW test matching the full kernel environment.
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
import wgpu
import wgpu.utils


def test_sw_kernel_like():
    """Test SW in a more kernel-like environment."""
    print(f"\n{'='*70}")
    print("SW test (kernel-like environment)")
    print(f"{'='*70}")

    MEMORY_SIZE_MB = 128
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
    PHYS_START = 0x80000000
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)
    
    # Put something at the target address (0x8000d1b0)
    target_offset = 0x8000d1b0 - PHYS_START
    pixel_idx = target_offset // 4
    memory[pixel_idx] = [0x23, 0x00, 0x00, 0x00]  # Same as kernel BSS
    
    cpu_state = make_cpu_state(0x80000000, priv_mode=3)
    
    # Set up state matching kernel at SW instruction
    cpu_state['pc'][0][0] = 0x80000abc
    cpu_state['pc'][0][1] = 0
    cpu_state['regs'][0][18][0] = 0x00000001  # s2 = 1
    cpu_state['regs'][0][18][1] = 0
    cpu_state['regs'][0][15][0] = 0x8000cab8  # a5
    cpu_state['regs'][0][15][1] = 0
    
    # Set up instruction at PC: sw s2, 1784(a5) = 0x6f27ac23
    instr = 0x6f27ac23
    memory[0, 0] = instr & 0xFF
    memory[0, 1] = (instr >> 8) & 0xFF
    memory[0, 2] = (instr >> 16) & 0xFF
    memory[0, 3] = (instr >> 24) & 0xFF
    
    device = wgpu.utils.get_default_device()
    queue = device.queue
    
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    
    memory_buffer = device.create_buffer(
        size=memory.nbytes,
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
    max_instr_arr = np.array([1], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instr_arr.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    
    queue.write_buffer(memory_buffer, 0, memory.tobytes())
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    queue.write_buffer(uniform_buffer, 0, max_instr_arr.tobytes())
    queue.write_buffer(input_buffer, 0, np.zeros(256, dtype=np.uint32).tobytes())
    
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
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': memory.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 65536}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instr_arr.nbytes}},
            {'binding': 4, 'resource': {'buffer': input_buffer, 'offset': 0, 'size': 1024}},
        ]
    )
    
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )
    
    print(f"\nBEFORE:")
    print(f"  s2 = 1")
    print(f"  a5 = 0x8000cab8")
    print(f"  target = 0x8000d1b0 (a5 + 1784)")
    
    mem_readback_before = queue.read_buffer(memory_buffer)
    mem_uint8 = np.frombuffer(mem_readback_before, dtype=np.uint8)
    pixel_before = mem_uint8[pixel_idx * 4:(pixel_idx + 1) * 4]
    word_before = (pixel_before[3] << 24) | (pixel_before[2] << 16) | (pixel_before[1] << 8) | pixel_before[0]
    print(f"  MEM[0x8000d1b0] = 0x{word_before:08x}")
    
    # Execute SW
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(pipeline)
    pass_enc.set_bind_group(0, bind_group)
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])
    
    print(f"\nAFTER (executed SW):")
    
    mem_readback_after = queue.read_buffer(memory_buffer)
    mem_uint8 = np.frombuffer(mem_readback_after, dtype=np.uint8)
    pixel_after = mem_uint8[pixel_idx * 4:(pixel_idx + 1) * 4]
    word_after = (pixel_after[3] << 24) | (pixel_after[2] << 16) | (pixel_after[1] << 8) | pixel_after[0]
    
    print(f"  MEM[0x8000d1b0] = 0x{word_after:08x}")
    print(f"  Expected = 0x00000001")
    
    if word_after == 0x00000001:
        print("\n✓ SW worked!")
    else:
        print("\n✗ SW failed!")
        print(f"  RGBA before: [{pixel_before[0]:02x}, {pixel_before[1]:02x}, {pixel_before[2]:02x}, {pixel_before[3]:02x}]")
        print(f"  RGBA after:  [{pixel_after[0]:02x}, {pixel_after[1]:02x}, {pixel_after[2]:02x}, {pixel_after[3]:02x}]")
        print(f"  Diff: 0x{word_after ^ word_before:08x}")


if __name__ == '__main__':
    test_sw_kernel_like()