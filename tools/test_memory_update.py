#!/usr/bin/env python3
"""
Check if memory is actually being updated on the GPU.
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader
import wgpu
import wgpu.utils


def test_memory_update():
    """Test if GPU memory updates are visible."""
    print(f"\n{'='*70}")
    print("Testing GPU memory updates")
    print(f"{'='*70}")

    # Create a simple test program: sw a0, 0(a1) where a0=0x12345678, a1=0x80000000
    # Encode: sw a0, 0(a1) = rs2=x10, rs1=x11, imm=0, funct3=2
    # 0x80000000 = 0x00000AF5  (sw a0, 0(a1))
    
    # Actually let me use python to encode it properly
    # S-type: imm[11:5] rs2 rs1 funct3 imm[4:0] opcode
    # sw a0, 0(a1): rs2=10, rs1=11, imm=0, funct3=010, opcode=0100011
    instr = (0b0000000 << 25) | (10 << 20) | (11 << 15) | (0b010 << 12) | (0b00000 << 7) | 0b0100011
    print(f"Instruction: sw a0, 0(a1) = 0x{instr:08x}")
    
    MEMORY_SIZE_MB = 128
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
    PHYS_START = 0x80000000
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)
    
    # Write a test value to memory at 0x80000000
    memory[0] = [0xDE, 0xAD, 0xBE, 0xEF]
    
    cpu_state = make_cpu_state(0x80000000, priv_mode=3)
    
    # Set a0 = 0x12345678, a1 = 0x80000000
    cpu_state['regs'][0][10][0] = 0x12345678 & 0xFFFFFFFF
    cpu_state['regs'][0][10][1] = 0
    cpu_state['regs'][0][11][0] = 0x80000000 & 0xFFFFFFFF
    cpu_state['regs'][0][11][1] = 0
    
    device = wgpu.utils.get_default_device()
    queue = device.queue
    
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    
    # Patch the memory with our instruction
    memory[0, 0] = instr & 0xFF
    memory[0, 1] = (instr >> 8) & 0xFF
    memory[0, 2] = (instr >> 16) & 0xFF
    memory[0, 3] = (instr >> 24) & 0xFF
    
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
    
    # Execute one instruction
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(pipeline)
    pass_enc.set_bind_group(0, bind_group)
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])
    
    # Read memory back
    mem_readback_bytes = queue.read_buffer(memory_buffer)
    mem_readback = np.frombuffer(mem_readback_bytes, dtype=np.uint32).reshape((pixel_count, 4))
    
    print(f"\nBEFORE SW (manually set):")
    print(f"  memory[0] = {list(memory[0])}")
    print(f"  Word (RGBA) = 0x{memory[0, 3]:02x}{memory[0, 2]:02x}{memory[0, 1]:02x}{memory[0, 0]:02x}")
    
    print(f"\nAFTER SW (from GPU):")
    print(f"  memory[0] = {list(mem_readback[0])}")
    print(f"  Word (RGBA) = 0x{mem_readback[0, 3]:02x}{mem_readback[0, 2]:02x}{mem_readback[0, 1]:02x}{mem_readback[0, 0]:02x}")
    print(f"  Expected: 0x12345678 (stored word, little-endian in RGBA)")
    
    if (mem_readback[0, 0] == 0x78 and 
        mem_readback[0, 1] == 0x56 and 
        mem_readback[0, 2] == 0x34 and 
        mem_readback[0, 3] == 0x12):
        print("\nOK: SW instruction worked!")
    else:
        print("\nERROR: SW instruction failed!")
        print(f"  Got RGBA: [{mem_readback[0, 0]:02x}, {mem_readback[0, 1]:02x}, {mem_readback[0, 2]:02x}, {mem_readback[0, 3]:02x}]")
        print(f"  Expected: [78, 56, 34, 12]")


if __name__ == '__main__':
    test_memory_update()