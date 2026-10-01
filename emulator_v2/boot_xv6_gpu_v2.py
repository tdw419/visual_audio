#!/usr/bin/env python3
"""
Boot xv6-riscv kernel on GPU RISC-V Emulator (v2)

Like tools/boot_xv6_gpu.py, but loads the emulator shader from a pixel frame
instead of from tools/RISCV_CPU_MMU.wgsl. The frame is verified by SHA-256 before
use.

This is Level 1 of the emulator_v2 migration: the emulator travels as pixels
but still compiles to native GPU code — zero runtime cost.
"""

import struct
import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
import sys
import argparse
import wgpu
import wgpu.utils

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / 'emulator_v2'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from pack_shader import unpack
from hybrid_kernel_loader import HybridKernelLoader


# ============================================================================
# MAIN BOOT SEQUENCE (adapted from boot_xv6_gpu.py)
# ============================================================================

def create_gpu_hardware_v2(shader_frame_path: Path, pixel_data: np.ndarray, cpu_state: np.ndarray, max_instructions: int = 100000000):
    """Initialize GPU and load emulator shader from a pixel frame (v2 variant)."""
    device = wgpu.utils.get_default_device()
    queue = device.queue

    # Load shader from pixel frame (v2: not from .wgsl file)
    print(f"\n[2] Loading emulator shader from pixel frame: {shader_frame_path}")
    
    # Unpack and verify the frame (SHA-256 check happens here)
    tmp_shader = Path('/tmp/xv6_gpu_v2_shader.wgsl')
    try:
        unpack(shader_frame_path, tmp_shader)
    except SystemExit as e:
        raise RuntimeError(f"Failed to unpack shader frame: {e}")
    
    shader_code = tmp_shader.read_text()
    print(f"    Loaded {len(shader_code)} bytes of WGSL from frame")
    
    # Clean up temp file
    tmp_shader.unlink()

    # Create buffers (same as original)
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

    # Input buffer for UART (inject keystrokes)
    input_buffer = device.create_buffer(
        size=1024,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        mapped_at_creation=False,
    )

    # Uniform buffer for instruction limit
    max_instr_arr = np.array([max_instructions], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instr_arr.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )

    # Upload initial data
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    queue.write_buffer(uniform_buffer, 0, max_instr_arr.tobytes())
    queue.write_buffer(input_buffer, 0, np.zeros(256, dtype=np.uint32).tobytes())

    # Bind group layout
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
        {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
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

    print(f"\n[5] Creating compute pipeline from pixel-sourced shader...")
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )

    print(f"    Device: {device.adapter.info['description']}")
    print(f"    Shader: {shader_frame_path} (verified SHA-256)")
    print(f"    Memory buffer: {pixel_data.nbytes // 4} words ({pixel_data.nbytes // 1024 // 1024}MB)")

    return {
        'device': device,
        'queue': queue,
        'pipeline': pipeline,
        'bind_group': bind_group,
        'cpu_buffer': cpu_buffer,
        'output_buffer': output_buffer,
        'input_buffer': input_buffer,
    }


def boot_xv6_on_gpu_v2(elf_path: str, shader_frame_path: Path, 
                       command: str = None, autonomous: bool = False,
                       autonomous_turns: int = 20, autonomous_model: str = 'qwen2.5-coder:14b',
                       max_instructions: int = 100000000):
    """Boot xv6 on GPU emulator with pixel-sourced shader."""
    
    print("=" * 70)
    print("XV6 RISC-V GPU BOOT - v2 (shader from pixels)")
    print("=" * 70)
    print(f"Shader frame: {shader_frame_path}")
    
    # Load ELF kernel (same as original)
    print(f"\n[1] Loading ELF64 kernel...")
    loader, fmt = HybridKernelLoader.load(elf_path)
    
    # Memory setup (same as original)
    print("\n[2] Loading kernel segments into memory...")
    MEMORY_SIZE_MB = 128
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
    PHYS_START = 0x80000000
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)

    for seg in loader.get_loadable_segments():
        if fmt == "ELF64":
            addr = seg['p_vaddr']
            size = seg['p_memsz']
            filesz = seg['p_filesz']
            offset = addr - PHYS_START
        else:
            addr = seg['virtual_address'] + PHYS_START + 0x00200000
            size = seg['virtual_size']
            filesz = seg['size_of_raw_data']
            offset = addr - PHYS_START

        data = loader.get_segment_data(seg)
        for i, byte in enumerate(data):
            pixel_idx = (offset + i) // 4
            byte_idx = (offset + i) % 4
            memory[pixel_idx, byte_idx] = byte
        print(f"  Loaded {filesz} bytes at 0x{addr:016x}")

    # CPU state setup (simplified for demo - using default from loader if available)
    # For now, create minimal CPU state
    cpu_state_layout = np.dtype([
        ('pc', 'u8'),
        ('regs', 'u8', (32,)),
        ('priv_mode', 'u4'),
        ('instr_count', 'u4'),
        ('halted', 'u4'),
        ('diag_code', 'u4'),
        ('diag_instr', 'u4'),
        ('satp', 'u8'),
        ('mstatus', 'u8'),
        ('mtvec', 'u8'),
        ('mepc', 'u8'),
        ('mcause', 'u8'),
        ('mtval', 'u8'),
        ('mscratch', 'u8'),
        ('mie', 'u8'),
        ('mip', 'u8'),
        ('stvec', 'u8'),
        ('sepc', 'u8'),
        ('scause', 'u8'),
        ('stval', 'u8'),
        ('sscratch', 'u8'),
        ('medeleg', 'u8'),
        ('mideleg', 'u8'),
        ('menvcfg', 'u8'),
        ('plic_pending', 'u4'),
        ('plic_enable', 'u4'),
        ('plic_claimed', 'u4'),
        ('plic_priority_irq1', 'u4'),
        ('timer_interrupt_count', 'u4'),
        ('total_interrupt_count', 'u4'),
        ('mtime_low', 'u4'),
        ('mtime_high', 'u4'),
        ('mtimecmp_low', 'u4'),
        ('mtimecmp_high', 'u4'),
    ])
    
    cpu_state = np.zeros(1, dtype=cpu_state_layout)
    # Set initial PC to ELF entry point
    if fmt == "ELF64":
        entry = loader.entry_point
    else:
        entry = 0x80000000
    
    cpu_state[0]['pc'] = entry
    cpu_state[0]['priv_mode'] = 3  # M-mode
    
    print(f"\n[3] CPU state initialized: PC=0x{entry:016x}, M-mode, MMU off")
    
    # Setup GPU hardware with shader from pixels
    harness = create_gpu_hardware_v2(shader_frame_path, memory, cpu_state, max_instructions)
    
    print("\n[6] Starting execution loop...")
    print(f"    Max instructions: {max_instructions}")
    
    # Simple execution loop (dispatch batches)
    device = harness['device']
    queue = harness['queue']
    pipeline = harness['pipeline']
    bind_group = harness['bind_group']
    output_buffer = harness['output_buffer']
    cpu_buffer = harness['cpu_buffer']
    input_buffer = harness['input_buffer']
    
    instr_batch = 1000
    total_dispatches = 0
    
    for i in range(max_instructions // instr_batch + 1):
        # Dispatch batch
        command_encoder = device.create_command_encoder()
        compute_pass = command_encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(0, bind_group)
        compute_pass.dispatch_workgroups(1, 1, 1)
        compute_pass.end()
        queue.submit([command_encoder.finish()])
        
        # Check for halt
        cpu_readback = queue.read_buffer(cpu_buffer)
        halted = cpu_readback['halted'][0]
        
        total_dispatches += 1
        
        # Simple progress
        if total_dispatches % 10 == 0:
            pc = cpu_readback['pc'][0]
            print(f"    ... {total_dispatches * instr_batch} instructions (PC: 0x{pc:016x})")
        
        if halted:
            print(f"\n    Halted after {total_dispatches * instr_batch} instructions")
            break
    
    # Read UART output
    output_data = queue.read_buffer(output_buffer)
    text = ''
    for b in output_data:
        if b == 0:
            break
        text += chr(b)
    
    print("\n[7] UART Output:")
    print(text)
    
    print(f"\n[✓] Boot completed: {total_dispatches * instr_batch} instructions")
    print(f"    Shader source: {shader_frame_path.name} (pixel-encoded, SHA-256 verified)")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Boot xv6-riscv on GPU RISC-V Emulator (v2, shader from pixels)')
    parser.add_argument('kernel', help='Path to xv6 kernel ELF')
    parser.add_argument(
        '--shader-frame',
        default='emulator_v2/emulator_frame.png',
        help='Path to emulator shader pixel frame (default: emulator_v2/emulator_frame.png)'
    )
    parser.add_argument('--command', '-c', help='Single command to inject after shell prompt')
    parser.add_argument('--max-instructions', type=int, default=100000000,
                       help='Max instructions to execute (default: 100M)')
    
    args = parser.parse_args()
    
    kernel_path = Path(args.kernel)
    shader_frame_path = Path(args.shader_frame)
    
    if not kernel_path.exists():
        parser.error(f"Kernel not found: {kernel_path}")
    if not shader_frame_path.exists():
        parser.error(f"Shader frame not found: {shader_frame_path}")
    
    try:
        boot_xv6_on_gpu_v2(str(kernel_path), shader_frame_path, args.command, max_instructions=args.max_instructions)
    except Exception as e:
        print(f"\n[✗] Boot failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())