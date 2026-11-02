#!/usr/bin/env python3
"""
Test harness for RISC-V GPU Emulator with ECALL (Hello World)

This version reads the output buffer and prints the captured message.
"""

import sys
import numpy as np
import wgpu

def create_gpu_device():
    """Initialize wgpu device."""
    import wgpu.utils
    device = wgpu.utils.get_default_device()
    queue = device.queue
    return device, queue

def main():
    print("=" * 60)
    print("RISC-V GPU Emulator Hello World Test (Phase 4)")
    print("=" * 60)

    # Load WGSL shader
    print("\n[1] Loading WGSL shader...")
    with open('RISCV_CPU.wgsl', 'r') as f:
        shader_code = f.read()

    # Create hello kernel
    print("\n[2] Creating hello kernel...")
    # Import the corrected kernel generator
    sys.path.insert(0, '.')
    from create_hello_kernel import create_hello_kernel
    kernel_binary, expected_msg = create_hello_kernel()
    print(f"    Kernel size: {len(kernel_binary)} bytes")

    # Convert binary to pixels (little-endian RGBA)
    print("\n[3] Converting to pixels...")
    # Pad to multiple of 4 bytes for uint32 array
    padded_size = ((len(kernel_binary) + 3) // 4) * 4
    kernel_padded = kernel_binary.ljust(padded_size, b'\x00')
    kernel_words = np.frombuffer(kernel_padded, dtype=np.uint32)

    # Create RGBA pixel array (4096 x 4096 x 4)
    pixel_array = np.zeros((4096, 4096, 4), dtype=np.uint8)

    # Pack into pixels (little-endian: R=byte0, G=byte1, B=byte2, A=byte3)
    for i, word in enumerate(kernel_words):
        pixel_array[0, i, 0] = word & 0xFF        # R
        pixel_array[0, i, 1] = (word >> 8) & 0xFF # G
        pixel_array[0, i, 2] = (word >> 16) & 0xFF # B
        pixel_array[0, i, 3] = (word >> 24) & 0xFF # A

    pixel_data = pixel_array.reshape(-1, 4)
    print(f"    Pixel array shape: {pixel_array.shape}")
    print(f"    Non-zero pixels: {np.count_nonzero(pixel_array)}")

    # Initialize GPU
    print("\n[4] Initializing GPU...")
    device, queue = create_gpu_device()
    print(f"    Device: {device.adapter.info.device}")

    # Create ROM buffer - binding 0
    rom_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(rom_buffer, 0, pixel_data.tobytes())
    print(f"    ROM buffer: {pixel_data.shape[0]} pixels ({pixel_data.nbytes} bytes)")

    # CPU state buffer - binding 1
    cpu_layout = np.dtype([
        ('pc', np.uint32, 2),
        ('regs', np.uint32, (32, 2)),
        ('running', np.uint32),
        ('instr_count', np.uint32),
        ('output_ptr', np.uint32),
        ('padding', np.uint32),
    ])
    cpu_state = np.zeros(1, dtype=cpu_layout)
    cpu_state[0]['pc'] = 0
    cpu_state[0]['running'] = 1
    cpu_state[0]['instr_count'] = 0

    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    print(f"    CPU buffer: {cpu_state.shape[0]} instance ({cpu_state.nbytes} bytes)")

    # Output buffer - binding 2
    output_buffer = device.create_buffer(
        size=4096,  # 1024 u32 words (4KB)
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    # Initialize to zero
    queue.write_buffer(output_buffer, 0, bytes(4096))
    print(f"    Output buffer: 4096 bytes (4KB)")

    # Max instructions uniform - binding 3
    max_instructions = np.array([1000], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())
    print(f"    Uniform buffer: max_instructions=1000")

    # Create bind group layout
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    # Create bind group
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': rom_buffer, 'offset': 0, 'size': rom_buffer.size}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_buffer.size}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': output_buffer.size}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': uniform_buffer.size}},
        ],
    )

    # Create compute pipeline
    print("\n[5] Creating compute pipeline...")
    compute_shader = device.create_shader_module(code=shader_code)

    pipeline_layout = device.create_pipeline_layout(
        bind_group_layouts=[bind_group_layout]
    )

    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={
            "module": compute_shader,
            "entry_point": "main",
        },
    )

    # Execute instructions
    print("\n[6] Executing RISC-V instructions on GPU...")

    for iteration in range(20):
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])

        # Read CPU state to check if still running
        cpu_readback = np.frombuffer(
            device.queue.read_buffer(cpu_buffer),
            dtype=cpu_layout
        )
        pc = cpu_readback[0]['pc'][0]
        running = cpu_readback[0]['running']
        instr_count = cpu_readback[0]['instr_count']
        output_ptr = cpu_readback[0]['output_ptr']

        print(f"    Iter {iteration:2d}: PC=0x{pc:04x}, running={running}, instr_count={instr_count}, output_ptr={output_ptr}")

        if running == 0:
            break

    # Read final CPU state
    print("\n[7] Reading final CPU state...")
    final_cpu = np.frombuffer(
        device.queue.read_buffer(cpu_buffer),
        dtype=cpu_layout
    )

    # Read output buffer
    output_readback = np.frombuffer(
        device.queue.read_buffer(output_buffer),
        dtype=np.uint32
    )

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(f"\nInstructions executed: {final_cpu[0]['instr_count']}")
    print(f"Final PC: 0x{final_cpu[0]['pc']:08x}")
    print(f"CPU running: {final_cpu[0]['running']}")
    print(f"Output pointer: {final_cpu[0]['output_ptr']}")

    # Extract output message (in CPU 0's region: 0-255)
    print(f"\nOutput buffer (first 32 words from CPU 0 region):")
    for i in range(min(32, len(output_readback))):
        if output_readback[i] != 0:
            # Try to interpret as ASCII
            ch = output_readback[i] & 0xFF
            if 32 <= ch <= 126 or ch == 10:  # Printable or newline
                print(f"  output[{i}] = 0x{output_readback[i]:08x} -> '{chr(ch)}'")
            else:
                print(f"  output[{i}] = 0x{output_readback[i]:08x}")

    # Extract message as bytes
    msg_len = final_cpu[0]['output_ptr']
    if msg_len > 0:
        msg_bytes = bytes([output_readback[i] & 0xFF for i in range(int(msg_len))])
        print(f"\nCaptured message ({msg_len} bytes):")
        print(f"  {msg_bytes.decode('ascii', errors='replace')}")

        print("\n" + "=" * 60)
        if msg_bytes == expected_msg:
            print("SUCCESS! Message matches expected output!")
        else:
            print("Message does not match expected output")
            print(f"  Expected: {expected_msg}")
            print(f"  Got:      {msg_bytes}")
        print("=" * 60)
    else:
        print("\nNo output captured (output_ptr = 0)")

    return 0

if __name__ == '__main__':
    sys.exit(main())