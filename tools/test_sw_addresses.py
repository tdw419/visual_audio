#!/usr/bin/env python3
"""
Test SW at different addresses to find the failure pattern.
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
import wgpu
import wgpu.utils


def test_sw_at_address(target_addr):
    """Test SW at a specific address."""
    MEMORY_SIZE_MB = 128
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
    PHYS_START = 0x80000000
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)
    
    target_offset = target_addr - PHYS_START
    pixel_idx = target_offset // 4
    
    # Put instruction at 0x80000000: sw s2, 0(a0) where a0 = target_addr, s2 = 1
    # S-type: imm[11:5] rs2 rs1 funct3 imm[4:0] opcode
    # sw s2, 0(a0): rs2=18, rs1=10, imm=0, funct3=010, opcode=0100011
    instr = (0b0000000 << 25) | (18 << 20) | (10 << 15) | (0b010 << 12) | (0b00000 << 7) | 0b0100011
    
    cpu_state = make_cpu_state(0x80000000, priv_mode=3)
    cpu_state['regs'][0][18][0] = 0x00000001  # s2 = 1
    cpu_state['regs'][0][18][1] = 0
    cpu_state['regs'][0][10][0] = target_addr & 0xFFFFFFFF  # a0 = target_addr
    cpu_state['regs'][0][10][1] = target_addr >> 32
    
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
    
    # Execute SW
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(pipeline)
    pass_enc.set_bind_group(0, bind_group)
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])
    
    # Check result
    mem_readback = queue.read_buffer(memory_buffer)
    mem_uint8 = np.frombuffer(mem_readback, dtype=np.uint8)
    pixel = mem_uint8[pixel_idx * 4:(pixel_idx + 1) * 4]
    word = (pixel[3] << 24) | (pixel[2] << 16) | (pixel[1] << 8) | pixel[0]
    
    return word == 0x00000001


def main():
    """Test SW at various addresses."""
    print(f"\n{'='*70}")
    print("SW test at different addresses")
    print(f"{'='*70}\n")
    
    # Test addresses: 0x80000000, 0x8000d1b0, and some random ones
    test_addrs = [
        0x80000000,
        0x80000004,
        0x80000100,
        0x8000d1b0,
        0x8000d1b4,
        0x80010000,
        0x80100000,
    ]
    
    for addr in test_addrs:
        offset = addr - 0x80000000
        pixel_idx = offset // 4
        try:
            result = test_sw_at_address(addr)
            status = "✓" if result else "✗"
            print(f"{status} 0x{addr:08x} (offset={offset:6d}, pixel={pixel_idx:5d})")
        except Exception as e:
            print(f"✗ 0x{addr:08x} (ERROR: {e})")


if __name__ == '__main__':
    main()