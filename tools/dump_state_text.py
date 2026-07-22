#!/usr/bin/env python3
"""
Dump emulator state to a text buffer for visualization.
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader
import wgpu
import wgpu.utils


def dump_state_to_text():
    """Dump emulator state as readable text lines."""
    print(f"\n{'='*70}")
    print("Emulator State Dump")
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
    
    # TEXT BUFFER - this is where we'll dump readable state
    TEXT_BUFFER_SIZE = 4096
    text_buffer = device.create_buffer(
        size=TEXT_BUFFER_SIZE,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
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
    
    # Run until we hit the SW instruction
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
            print(f"\n{'='*70}")
            print(f"State at instruction: sw s2, 1784(a5) (PC = 0x{pc:08x})")
            print(f"{'='*70}")
            
            # Format state as readable text
            text_lines = []
            text_lines.append(f"PC=0x{pc:08x}")
            
            # Show relevant registers
            text_lines.append(f"s2=0x{(regs[18][1] << 32) | regs[18][0]:016x}")
            text_lines.append(f"a5=0x{(regs[15][1] << 32) | regs[15][0]:016x}")
            text_lines.append(f"a6=0x{(regs[16][1] << 32) | regs[16][0]:016x}")
            text_lines.append(f"a7=0x{(regs[17][1] << 32) | regs[17][0]:016x}")
            
            # Show computed target address
            imm = 1784
            a5_val = (regs[15][1] << 32) | regs[15][0]
            target_addr = a5_val + imm
            text_lines.append(f"TARGET=0x{target_addr:016x}")
            
            # Read memory at target
            mem_readback_bytes = queue.read_buffer(memory_buffer)
            mem_uint8 = np.frombuffer(mem_readback_bytes, dtype=np.uint8)
            offset = target_addr - PHYS_START
            pixel_idx = offset // 4
            pixel = mem_uint8[pixel_idx * 4:(pixel_idx + 1) * 4]
            word_value = (pixel[3] << 24) | (pixel[2] << 16) | (pixel[1] << 8) | pixel[0]
            
            text_lines.append(f"MEM[0x{target_addr:016x}]=0x{word_value:08x}")
            text_lines.append(f"EXPECTED=0x{(regs[18][1] << 32) | regs[18][0]:08x}")
            
            # Combine into single text buffer
            text_content = '\n'.join(text_lines)
            
            print(f"\nText dump:")
            print(text_content)
            
            # Write to text buffer on GPU
            text_bytes = text_content.encode('ascii')
            queue.write_buffer(text_buffer, 0, text_bytes)
            
            print(f"\n✓ Wrote state to text buffer ({len(text_bytes)} bytes)")
            print(f"  This could be encoded as audio via Visual Audio for \"spoken\" debugging")
            
            return text_content


if __name__ == '__main__':
    dump_state_to_text()