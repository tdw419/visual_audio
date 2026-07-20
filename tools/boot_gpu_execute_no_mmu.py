#!/usr/bin/env python3
"""
GPU Execution Harness - No MMU (SATP=off)
"""

import wgpu
import wgpu.utils
import numpy as np
import struct
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <pixels.npy> <entry_point>")
        print(f"\nExample:")
        print(f"  {sys.argv[0]} test_kernel_no_mmu.npy 0x1000")
        sys.exit(1)

    pixels_path = sys.argv[1]
    entry_point = int(sys.argv[2], 16) if sys.argv[2].startswith('0x') else int(sys.argv[2])

    print("=" * 70)
    print("GPU EXECUTION HARNESS - NO MMU (SATP=off)")
    print("=" * 70)

    # Load pixels
    print(f"\n[1] Loading pixel memory: {pixels_path}")
    pixels = np.load(pixels_path)
    print(f"  Shape: {pixels.shape}")

    # Initialize GPU
    print("\n[2] Initializing GPU...")
    device = wgpu.utils.get_default_device()
    queue = device.queue
    print(f"  Device: {device.adapter.info.device}")

    # Load shader (MMU version, but we'll set SATP=off)
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    print(f"  Shader: {shader_path}")

    # Create memory buffer
    pixel_data = pixels.reshape(-1, 4).astype(np.uint32)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
    print(f"\n[3] Memory buffer: {pixel_data.shape[0]} words ({pixel_data.nbytes // 1024}KB)")

    # Create CPU state (SATP=0 = MMU off)
    cpu_layout = np.dtype([
        ('pc', np.uint32, 2),
        ('regs', np.uint32, (32, 2)),
        ('running', np.uint32),
        ('instr_count', np.uint32),
        ('output_ptr', np.uint32),
        ('satp', np.uint32),
    ])

    cpu_state = np.zeros(1, dtype=cpu_layout)
    cpu_state[0]['pc'] = [entry_point & 0xFFFFFFFF, (entry_point >> 32) & 0xFFFFFFFF]
    cpu_state[0]['running'] = 1
    cpu_state[0]['instr_count'] = 0
    cpu_state[0]['satp'] = 0  # MMU OFF (mode=0)
    cpu_state[0]['regs'] = np.zeros((32, 2), dtype=np.uint32)

    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    print(f"  CPU: PC=0x{entry_point:016x}, SATP=0 (MMU OFF)")

    # Output buffer
    output_buffer = device.create_buffer(
        size=65536,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    # Max instructions uniform
    max_instructions = np.array([10000], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())
    print(f"  Max instructions: {max_instructions[0]}")

    # Create bind group
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': pixel_data.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 65536}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instructions.nbytes}},
        ]
    )

    # Create compute pipeline
    print("\n[4] Creating compute pipeline...")
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )

    # Execute
    print("\n[5] Executing on GPU...")
    print()

    last_pc = 0
    stale_count = 0
    pc = entry_point
    instr_count = 0
    running = 1

    for iteration in range(100):
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])

        # Read CPU state
        cpu_readback = np.frombuffer(
            device.queue.read_buffer(cpu_buffer),
            dtype=cpu_layout
        )[0]

        running = cpu_readback['running']
        pc_low = cpu_readback['pc'][0]
        pc_high = cpu_readback['pc'][1]
        pc = (pc_high << 32) | pc_low
        instr_count = cpu_readback['instr_count']

        # Stall detection
        if pc == last_pc:
            stale_count += 1
            if stale_count > 5:
                print(f"  Iter {iteration:3d}: PC stalled at 0x{pc:016x}")
                break
        else:
            stale_count = 0
            last_pc = pc

        # Progress
        print(f"  Iter {iteration:3d}: PC=0x{pc:016x}, instr={instr_count:6d}, running={running}")

        if running == 0:
            print(f"\n  Halted after {instr_count} instructions")
            break

    # Read output
    print("\n[6] Reading output buffer...")
    output_data = np.frombuffer(
        device.queue.read_buffer(output_buffer),
        dtype=np.uint8
    )

    # Decode output - show raw hex and ASCII
    output_str = ''
    print("  Raw output buffer (first 20 bytes):", end=" ")
    for i in range(min(20, len(output_data))):
        print(f"{output_data[i]:02x}", end=" ")
    print()
    
    # Decode only what the kernel actually wrote (output_ptr from CPU state)
    # For now, decode until null or end of buffer
    for i in range(0, len(output_data), 4):
        word_bytes = output_data[i:i+4]
        if len(word_bytes) < 4:
            break
        for b in word_bytes:
            if b == 0:
                break
            if 32 <= b < 127:
                output_str += chr(b)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Final PC: 0x{pc:016x}")
    print(f"Instructions executed: {instr_count}")
    print(f"Status: {'HALTED' if running == 0 else 'RUNNING'}")

    if output_str:
        print(f"\nKernel output:\n{output_str}")
    else:
        print("\n(no output captured)")

    print("=" * 70)


if __name__ == '__main__':
    main()