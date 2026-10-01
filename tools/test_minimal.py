#!/usr/bin/env python3
"""
Simplify to just 2 instructions: lui a0, 0x00100; addi a0, a0, 0x010
Expected final a0 = 0x00101000
"""

import sys
import numpy as np
import wgpu

def create_gpu_device():
    import wgpu.utils
    device = wgpu.utils.get_default_device()
    queue = device.queue
    return device, queue

def main():
    # Load WGSL shader
    with open('RISCV_CPU.wgsl', 'r') as f:
        shader_code = f.read()

    # lui a0, 0x00100; addi a0, a0, 0x010
    # lui a0, 0x00100: 0x00100513
    # addi a0, a0, 0x010: 0x01050513
    kernel_words = np.array([0x00100513, 0x01050513], dtype=np.uint32)

    print('Instructions:')
    print(f'  [0] PC=0x0000: 0x{kernel_words[0]:08x} = lui a0, 0x00100 -> a0 = 0x00100000')
    print(f'  [1] PC=0x0004: 0x{kernel_words[1]:08x} = addi a0, a0, 0x010 -> a0 = 0x00101000')
    print(f'  Expected final a0 = 0x00101000')

    # Pack into pixels
    pixel_array = np.zeros((4096, 4096, 4), dtype=np.uint8)
    for i, word in enumerate(kernel_words):
        pixel_array[0, i, 0] = word & 0xFF
        pixel_array[0, i, 1] = (word >> 8) & 0xFF
        pixel_array[0, i, 2] = (word >> 16) & 0xFF
        pixel_array[0, i, 3] = (word >> 24) & 0xFF

        # Verify encoding
        reconstructed = pixel_array[0, i, 0] | (pixel_array[0, i, 1] << 8) | \
                        (pixel_array[0, i, 2] << 16) | (pixel_array[0, i, 3] << 24)
        if reconstructed != word:
            print(f'  *** ERROR: pixel[{i}] encodes 0x{reconstructed:08x} != 0x{word:08x}')

    pixel_data = pixel_array.reshape(-1, 4)

    # Initialize GPU
    device, queue = create_gpu_device()

    # Create buffers
    rom_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(rom_buffer, 0, pixel_data.tobytes())

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

    output_buffer = device.create_buffer(
        size=4096,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(output_buffer, 0, bytes(4096))

    max_instructions = np.array([10], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())

    # Bind group
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': rom_buffer, 'offset': 0, 'size': rom_buffer.size}},
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
    for iteration in range(5):
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
        a0 = cpu_readback[0]['regs'][10]

        print(f"  Iter {iteration}: PC=0x{pc:04x}, running={running}, instr_count={instr_count}, a0=0x{a0:08x}")

        if running == 0:
            # Check what halted us
            output_readback = np.frombuffer(device.queue.read_buffer(output_buffer), dtype=np.uint32)
            if output_readback[0] != 0:
                print(f"  Halted by unknown opcode: 0x{output_readback[0]:08x}")
            break

    # Check final state
    final_cpu = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_layout)
    final_a0 = final_cpu[0]['regs'][10]
    expected_a0 = 0x00101000

    print(f'\nFinal state:')
    print(f'  a0 = 0x{final_a0:08x} (expected 0x{expected_a0:08x})')

    if final_a0 == expected_a0:
        print('  *** PASS ***')
        return 0
    else:
        print('  *** FAIL ***')
        return 1

if __name__ == '__main__':
    sys.exit(main())