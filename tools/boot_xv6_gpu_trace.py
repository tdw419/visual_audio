#!/usr/bin/env python3
"""
Boot xv6 kernel with per-instruction trace capture for QEMU comparison.

Use this when you want to compare our GPU emulator against QEMU at the
instruction level to debug divergent behavior.

Usage:
    boot_xv6_gpu_trace.py <kernel.elf> --output trace.jsonl --max-instructions 1000
"""

import struct
import numpy as np
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from boot_xv6_gpu import (
    ELF64Loader, create_gpu_hardware, make_cpu_state,
    boot_xv6_on_gpu, inject_command, get_next_autonomous_command
)
import json


def trace_with_per_instruction(kernel_path: str, output_path: str, 
                                  max_instructions: int = 1000,
                                  target_pc: int = None):
    """
    Run the kernel with max_instructions=1 to capture per-instruction trace.
    
    This is slow but gives instruction-level granularity for diffing.
    """
    print(f"Tracing {kernel_path} (max {max_instructions} instructions)")
    
    # Load kernel
    elf = ELF64Loader(kernel_path)
    elf.print_info()
    
    # Build harness with max_instructions=1
    # We need to patch the harness creation to use max_instructions=1
    # For now, create a minimal trace harness
    import wgpu
    
    device = wgpu.utils.get_default_device()
    print(f"Using device: {device}")
    
    # Load kernel segments
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
    
    # Load fs.img if present
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
    
    # Create CPU state
    from riscv_gpu_cpu import CPU_DTYPE, make_cpu_state, MEDELEG_DEFAULT, MIDELEG_DEFAULT
    cpu_layout = CPU_DTYPE
    cpu = make_cpu_state(elf.entry_point, priv_mode=3)
    
    # Set up delegation
    cpu[0]['medeleg'] = [MEDELEG_DEFAULT & 0xFFFFFFFF, 0]
    cpu[0]['mideleg'] = [MIDELEG_DEFAULT & 0xFFFFFFFF, 0]
    
    # Create harness with max_instructions=1
    queue = device.queue
    
    # Memory buffer
    memory_buffer = device.create_buffer(
        size=memory.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        mapped_at_creation=False
    )
    queue.write_buffer(memory_buffer, 0, memory.tobytes())
    
    # CPU buffer
    cpu_buffer = device.create_buffer(
        size=cpu.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
        mapped_at_creation=False
    )
    queue.write_buffer(cpu_buffer, 0, cpu.tobytes())
    
    # Output buffer (UART)
    output_buffer = device.create_buffer(
        size=16384,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        mapped_at_creation=False
    )
    
    # Input buffer
    input_buffer = device.create_buffer(
        size=256 * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        mapped_at_creation=False
    )
    
    # Uniform buffer: max_instructions=1 for per-instruction trace
    max_instructions_array = np.array([1], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions_array.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions_array.tobytes())
    
    # Load shader
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    
    # Create bind group layout
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
        {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
    ])
    
    # Create bind group
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': memory.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 16384}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instructions_array.nbytes}},
            {'binding': 4, 'resource': {'buffer': input_buffer, 'offset': 0, 'size': 1024}},
        ]
    )
    
    # Create pipeline
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bind_group_layout]),
        compute={'module': compute_shader, 'entry_point': 'main'}
    )
    
    # Open trace output
    with open(output_path, 'w') as trace_f:
        print(f"Writing trace to {output_path}")
        
        trace_count = 0
        prev_pc = None
        
        try:
            while trace_count < max_instructions:
                # Dispatch one instruction
                encoder = device.create_command_encoder()
                pass_enc = encoder.begin_compute_pass()
                pass_enc.set_pipeline(pipeline)
                pass_enc.set_bind_group(0, bind_group)
                pass_enc.dispatch_workgroups(1)
                pass_enc.end()
                queue.submit([encoder.finish()])
                
                # Read CPU state
                cpu_readback_bytes = queue.read_buffer(cpu_buffer)
                cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=cpu_layout)
                
                pc_low = int(cpu_readback['pc'][0][0])
                pc_high = int(cpu_readback['pc'][0][1])
                pc = int((pc_high << 32) | pc_low)
                running = int(cpu_readback['running'][0])
                instr_count = int(cpu_readback['instr_count'][0])
                
                # Check if we're at target PC if specified
                if target_pc is not None and pc < target_pc:
                    continue
                
                # Write trace entry
                regs = cpu_readback['regs'][0]
                regs_dict = {
                    f'x{i}': int((regs[i][1] << 32) | regs[i][0])
                    for i in range(32)
                }
                
                # Add CSRs
                regs_dict['pc'] = int(pc)
                regs_dict['mstatus'] = int((cpu_readback['mstatus'][0][1] << 32) | cpu_readback['mstatus'][0][0])
                regs_dict['mepc'] = int((cpu_readback['mepc'][0][1] << 32) | cpu_readback['mepc'][0][0])
                regs_dict['mcause'] = int((cpu_readback['mcause'][0][1] << 32) | cpu_readback['mcause'][0][0])
                
                trace_entry = {
                    'pc': pc,
                    'instr': f"0x{prev_pc:08x}" if prev_pc else "N/A",
                    'regs': regs_dict
                }
                trace_f.write(json.dumps(trace_entry) + '\n')
                
                prev_pc = pc
                trace_count += 1
                
                # Progress indicator
                if trace_count % 100 == 0:
                    print(f"  Traced {trace_count}/{max_instructions} instructions, PC=0x{pc:016x}")
                
                if running == 0:
                    print(f"CPU halted after {trace_count} instructions")
                    break
        
        except KeyboardInterrupt:
            print(f"Interrupted after {trace_count} instructions")
    
    print(f"Trace complete: {trace_count} instructions written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Boot xv6 with instruction trace for QEMU comparison')
    parser.add_argument('kernel', help='xv6 kernel ELF path')
    parser.add_argument('--output', '-o', default='/tmp/gpu_trace.jsonl',
                        help='Trace output file (default: /tmp/gpu_trace.jsonl)')
    parser.add_argument('--max-instructions', type=int, default=1000,
                        help='Max instructions to trace (default: 1000)')
    parser.add_argument('--target-pc', type=lambda x: int(x, 0),
                        help='Start tracing at this PC (default: from entry point)')
    
    args = parser.parse_args()
    
    trace_with_per_instruction(
        args.kernel,
        args.output,
        args.max_instructions,
        args.target_pc
    )


if __name__ == '__main__':
    main()