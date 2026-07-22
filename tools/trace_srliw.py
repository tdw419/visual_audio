#!/usr/bin/env python3
"""
Trace what happens around the srliw instruction.
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader, create_gpu_hardware
import wgpu
import wgpu.utils


def trace_srliw():
    """Find what's wrong with srliw."""
    print(f"\n{'='*70}")
    print("Tracing srliw instruction")
    print(f"{'='*70}")

    elf = ELF64Loader('/tmp/xv6-riscv/kernel/kernel')
    
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

    cpu_state = make_cpu_state(elf.entry_point, priv_mode=3)
    device = wgpu.utils.get_default_device()
    queue = device.queue
    
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    
    memory_buffer = device.create_buffer(
        size=memory.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
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
    
    # Run to reach the srliw instruction (0x80001180)
    print("\nRunning to reach srliw instruction...")
    queue.write_buffer(uniform_buffer, 0, np.array([100_000], dtype=np.uint32).tobytes())
    
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
    
    print(f"Reached PC=0x{pc:016x}")
    
    # Single step to catch the srliw
    for step in range(50):
        cpu_readback_bytes = queue.read_buffer(cpu_buffer)
        cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=CPU_DTYPE)
        pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
        regs = cpu_readback['regs'][0]
        
        # Check if at srliw (0x80001180)
        if pc == 0x80001180:
            print(f"\nStep {step}: AT SRLIW instruction")
            a2_lo = regs[12][0]
            a2_hi = regs[12][1]
            a2_full = (a2_hi << 32) | a2_lo
            print(f"  a2 (x12): lo=0x{a2_lo:08x}, hi=0x{a2_hi:08x}, full=0x{a2_full:016x} = {a2_full}")
            print(f"  Expected: a2 = 4096 (PGSIZE)")
            
            # Execute the srliw
            queue.write_buffer(uniform_buffer, 0, np.array([1], dtype=np.uint32).tobytes())
            encoder = device.create_command_encoder()
            pass_enc = encoder.begin_compute_pass()
            pass_enc.set_pipeline(pipeline)
            pass_enc.set_bind_group(0, bind_group)
            pass_enc.dispatch_workgroups(1)
            pass_enc.end()
            queue.submit([encoder.finish()])
            
            cpu_readback_bytes = queue.read_buffer(cpu_buffer)
            cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=CPU_DTYPE)
            regs = cpu_readback['regs'][0]
            pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
            
            a6_lo = regs[18][0]
            a6_hi = regs[18][1]
            a6_full = (a6_hi << 32) | a6_lo
            print(f"  After srliw:")
            print(f"    a6 (x18): lo=0x{a6_lo:08x}, hi=0x{a6_hi:08x}, full=0x{a6_full:016x} = {a6_full}")
            print(f"    Expected: 512 (4096 >> 3)")
            print(f"    PC: 0x{pc:016x}")
            
            # Calculate what we SHOULD get
            expected_32 = (a2_lo >> 3) & 0xFFFFFFFF
            expected_sign_extended = (expected_32 ^ 0x80000000) - 0x80000000  # Sign extend
            print(f"  Manual calculation:")
            print(f"    a2_lo >> 3 = 0x{(a2_lo >> 3):08x} = {a2_lo >> 3}")
            print(f"    Expected sign-extended: {expected_sign_extended}")
            break
        
        # Not at srliw yet, execute one instruction
        queue.write_buffer(uniform_buffer, 0, np.array([1], dtype=np.uint32).tobytes())
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])


if __name__ == '__main__':
    trace_srliw()