#!/usr/bin/env python3
"""
Test swap instruction at 0x80000abc.
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader
import wgpu
import wgpu.utils


def trace_swap():
    """Trace swap instruction."""
    print(f"\n{'='*70}")
    print("Tracing swap instruction at 0x80000abc")
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
    
    for step in range(200000):
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
        regs = cpu_readback['regs'][0]
        
        if pc == 0x80000abc:
            s2 = (regs[18][1] << 32) | regs[18][0]
            a5 = (regs[15][1] << 32) | regs[15][0]
            
            print(f"\nBEFORE swap:")
            print(f"  s2 = 0x{s2:016x}")
            print(f"  a5 = 0x{a5:016x}")
            
            # Calculate target address: a5 + 1784
            addr = a5 + 1784
            print(f"  Target address = 0x{addr:016x}")
            
            # Read the value at that address from memory
            # addr 0x80000cab8 + 1784 = 0x80000cb8
            offset = addr - PHYS_START
            if offset >= 0 and offset < MEMORY_SIZE:
                pixel_idx = offset // 4
                if pixel_idx < pixel_count:
                    pixel = memory[pixel_idx]
                    # Bytes are little-endian
                    word = (pixel[3] << 24) | (pixel[2] << 16) | (pixel[1] << 8) | pixel[0]
                    print(f"  Memory at 0x{addr:016x} = 0x{word:08x}")
            
            # Execute one more instruction
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
            s2_after = (regs[18][1] << 32) | regs[18][0]
            
            print(f"\nAFTER swap:")
            print(f"  s2 = 0x{s2_after:016x}")
            
            # Read the value at that address from memory after
            offset = addr - PHYS_START
            if offset >= 0 and offset < MEMORY_SIZE:
                pixel_idx = offset // 4
                if pixel_idx < pixel_count:
                    pixel = memory[pixel_idx]
                    word = (pixel[3] << 24) | (pixel[2] << 16) | (pixel[1] << 8) | pixel[0]
                    print(f"  Memory at 0x{addr:016x} = 0x{word:08x}")
            return


if __name__ == '__main__':
    trace_swap()