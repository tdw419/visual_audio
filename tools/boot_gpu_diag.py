#!/usr/bin/env python3
"""GPU execution diagnostic - dumps CPU state after halt"""
import wgpu
import wgpu.utils
import numpy as np
import struct
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <pixels.npy> <entry_point>")
        sys.exit(1)

    pixels_path = sys.argv[1]
    entry_point = int(sys.argv[2], 16) if sys.argv[2].startswith('0x') else int(sys.argv[2])

    print("=" * 70)
    print("GPU DIAGNOSTIC - NO MMU")
    print("=" * 70)

    pixels = np.load(pixels_path)
    print(f"Pixel memory: {pixels.shape}")

    device = wgpu.utils.get_default_device()
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    print(f"Shader: {shader_path}")

    # Memory
    pixel_data = pixels.reshape(-1, 4).astype(np.uint32)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue = device.queue
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())

    # CPU state layout
    cpu_layout = np.dtype([
        ('pc', np.uint64),
        ('running', np.uint32),
        ('instr_count', np.uint32),
        ('regs', np.uint64, 32),
        ('output_ptr', np.uint32),
    ])
    cpu_buffer = device.create_buffer(
        size=cpu_layout.itemsize,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST,
    )
    cpu_state = np.zeros(1, dtype=cpu_layout)
    cpu_state['pc'] = entry_point
    cpu_state['running'] = 1
    cpu_state['output_ptr'] = 0
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())

    # Output buffer
    output_buffer_size = 65536
    output_buffer = device.create_buffer(
        size=output_buffer_size,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    max_instructions = np.array([10000], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())

    # Create bind group
    bind_group_layout = device.create_bind_group_layout(entries=[
        {"binding": 0, "visibility": wgpu.BindingVisibility.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 1, "visibility": wgpu.BindingVisibility.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 2, "visibility": wgpu.BindingVisibility.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 3, "visibility": wgpu.BindingVisibility.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
    ])
    bind_group = device.create_bind_group(entries=[
        {"binding": 0, "resource": {"buffer": memory_buffer}},
        {"binding": 1, "resource": {"buffer": cpu_buffer}},
        {"binding": 2, "resource": {"buffer": output_buffer}},
        {"binding": 3, "resource": {"buffer": uniform_buffer}},
    ], layout=bind_group_layout)

    # Pipeline
    shader_module = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={"module": shader_module, "entry_point": "main"},
    )

    print(f"Executing at PC=0x{entry_point:016x}...")

    # Run in a single dispatch
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(pipeline)
    pass_enc.set_bind_group(0, bind_group)
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])
    queue.submit([])  # flush

    # Read CPU state
    cpu_readback = np.frombuffer(
        device.queue.read_buffer(cpu_buffer),
        dtype=cpu_layout
    )[0]

    pc = cpu_readback['pc']
    running = cpu_readback['running']
    instr_count = cpu_readback['instr_count']
    output_ptr = cpu_readback['output_ptr']

    print(f"\nCPU State after execution:")
    print(f"  PC: 0x{pc:016x}")
    print(f"  Instructions: {instr_count}")
    print(f"  Running: {running}")
    print(f"  Output ptr: {output_ptr}")

    # Print key registers
    reg_names = ['zero','ra','sp','gp','tp','t0','t1','t2','s0','s1','a0','a1','a2','a3','a4','a5',
                 'a6','a7','s2','s3','s4','s5','s6','s7','s8','s9','s10','s11','t3','t4','t5','t6']
    print("\nRegisters:")
    for i in range(0, 32, 4):
        regs_str = []
        for j in range(4):
            r = i + j
            v = cpu_readback['regs'][r]
            if v == 0:
                regs_str.append(f"{reg_names[r]:4s}=0x0")
            else:
                regs_str.append(f"{reg_names[r]:4s}=0x{v:016x}")
        print(f"  {'  '.join(regs_str)}")

    # Read output
    output_data = np.frombuffer(
        device.queue.read_buffer(output_buffer),
        dtype=np.uint8
    )

    # Show output
    output_str = ''
    for i in range(min(output_ptr, 500)):
        b = output_data[i]
        if 32 <= b < 127:
            output_str += chr(b)
        else:
            output_str += f'[{b:02x}]'

    print(f"\nOutput ({output_ptr} bytes):")
    print(f"  '{output_str}'")

    # Show raw output area
    print(f"\nRaw output buffer (first 64 bytes):")
    for i in range(0, min(64, len(output_data)), 16):
        hex_bytes = ' '.join(f'{output_data[i+j]:02x}' for j in range(min(16, len(output_data)-i)))
        ascii_chars = ''.join(chr(output_data[i+j]) if 32 <= output_data[i+j] < 127 else '.' for j in range(min(16, len(output_data)-i)))
        print(f"  {i:04x}: {hex_bytes:48s} {ascii_chars}")

if __name__ == '__main__':
    main()
