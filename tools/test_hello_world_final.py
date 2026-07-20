#!/usr/bin/env python3
"""
Fixed RISC-V Hello World test with read-write memory buffer
"""

import sys
import numpy as np
import wgpu
from create_hello_kernel_correct import create_hello_kernel

def create_gpu_device():
    import wgpu.utils
    device = wgpu.utils.get_default_device()
    queue = device.queue
    return device, queue

def main():
    # Load WGSL shader
    with open('RISCV_CPU.wgsl', 'r') as f:
        shader_code = f.read()

    # Create hello kernel
    kernel_binary, expected_msg = create_hello_kernel()
    print(f'\nKernel size: {len(kernel_binary)} bytes')
    print(f'Expected output: {expected_msg!r}')

    # Pad to multiple of 4 bytes for uint32 array
    padded_size = ((len(kernel_binary) + 3) // 4) * 4
    kernel_padded = kernel_binary.ljust(padded_size, b'\x00')

    # Convert to u32 array
    kernel_words = np.frombuffer(kernel_padded, dtype=np.uint32)

    # Pack into u32 pixel array
    pixel_data = np.zeros((4096 * 4096 * 4,), dtype=np.uint32)

    for i, word in enumerate(kernel_words):
        base_idx = i * 4
        pixel_data[base_idx + 0] = word & 0xFF
        pixel_data[base_idx + 1] = (word >> 8) & 0xFF
        pixel_data[base_idx + 2] = (word >> 16) & 0xFF
        pixel_data[base_idx + 3] = (word >> 24) & 0xFF

    # Initialize GPU
    device, queue = create_gpu_device()

    # Create memory buffer (read-write RAM)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())

    # CPU state buffer
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

    # Output buffer (1024 u32 words)
    output_buffer = device.create_buffer(
        size=4096,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(output_buffer, 0, bytes(4096))

    # Max instructions uniform
    max_instructions = np.array([100], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())

    # Bind group
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': memory_buffer.size}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_buffer.size}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': output_buffer.size}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': uniform_buffer.size}},
        ],
    )

    # Pipeline
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={"module": compute_shader, "entry_point": "main"},
    )

    # Execute
    print('\nExecuting on GPU:')
    for iteration in range(20):
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])

        cpu_readback = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_layout)
        pc = cpu_readback[0]['pc'][0]
        running = cpu_readback[0]['running']
        instr_count = cpu_readback[0]['instr_count']
        output_ptr = cpu_readback[0]['output_ptr']

        print(f"  Iter {iteration:2d}: PC=0x{pc:04x}, running={running}, instr_count={instr_count:2d}, output_ptr={output_ptr}")

        if running == 0 or instr_count >= 50:
            break

    # Check final state
    final_cpu = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_layout)

    print(f'\nFinal state:')
    print(f'  a0 (x10) = 0x{final_cpu[0]["regs"][10]:08x}')
    print(f'  a1 (x11) = 0x{final_cpu[0]["regs"][11]:08x}')
    print(f'  a2 (x12) = 0x{final_cpu[0]["regs"][12]:08x}')
    print(f'  a7 (x17) = 0x{final_cpu[0]["regs"][17]:08x}')
    print(f'  output_ptr = {final_cpu[0]["output_ptr"]}')

    # Read output buffer as u32 words, then unpack bytes
    output_readback_u32 = np.frombuffer(device.queue.read_buffer(output_buffer), dtype=np.uint32)

    # Unpack bytes from u32 words
    num_bytes_needed = final_cpu[0]['output_ptr']
    output_bytes = bytearray(num_bytes_needed)
    for i in range(num_bytes_needed):
        word_idx = i // 4
        byte_in_word = i % 4
        word = output_readback_u32[word_idx]
        byte_val = (word >> (byte_in_word * 8)) & 0xFF
        output_bytes[i] = byte_val

    captured_msg = output_bytes.decode('ascii', errors='replace')

    print(f'\nCaptured output: {captured_msg!r}')

    if captured_msg == expected_msg:
        print('  *** SUCCESS *** - GPU RISC-V emulator with ECALL working!')
        return 0
    else:
        print(f'  Expected: {expected_msg!r}')
        print('  *** FAIL ***')
        return 1

if __name__ == '__main__':
    sys.exit(main())