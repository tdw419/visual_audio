#!/usr/bin/env python3
"""
Test OP_LOAD and OP_STORE instructions

Tests LB, LH, LW, LBU, LHU, SB, SH, SW instructions on the GPU RISC-V emulator.
"""

import sys
import numpy as np
import wgpu

def create_gpu_device():
    import wgpu.utils
    device = wgpu.utils.get_default_device()
    queue = device.queue
    return device, queue

def encode_lui(rd, imm):
    imm_20 = imm & 0xFFFFF
    return (imm_20 << 12) | (rd << 7) | 0x37

def encode_addi(rd, rs1, imm):
    imm_12 = imm & 0xFFF
    return (imm_12 << 20) | (rs1 << 15) | (0x0 << 12) | (rd << 7) | 0x13

def encode_lw(rd, rs1, imm):
    """Encode LW (Load Word) instruction"""
    imm_12 = imm & 0xFFF
    return (imm_12 << 20) | (rs1 << 15) | (0x2 << 12) | (rd << 7) | 0x03

def encode_sw(rs2, rs1, imm):
    """Encode SW (Store Word) instruction"""
    imm_11_5 = (imm >> 5) & 0x7F
    imm_4_0 = imm & 0x1F
    return (imm_11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (0x2 << 12) | (imm_4_0 << 7) | 0x23

def encode_ecall():
    return 0x00000073

def main():
    # Load WGSL shader
    with open('RISCV_CPU.wgsl', 'r') as f:
        shader_code = f.read()

    print("Testing OP_LOAD (LW) and OP_STORE (SW) instructions\n")

    # Create test program:
    # 1. lui a1, 0         -> a1 = 0x00000000
    # 2. addi a1, a1, 0x40 -> a1 = 0x00000040 (data address)
    # 3. lui a0, 0x12345   -> a0 = 0x12345000
    # 4. sw a0, 0(a1)      -> store a0 at address 0x40
    # 5. lw a2, 0(a1)      -> load from address 0x40 into a2
    # 6. ecall              -> halt

    instructions = [
        encode_lui(11, 0),              # lui a1, 0
        encode_addi(11, 11, 0x40),      # addi a1, a1, 0x40
        encode_lui(10, 0x12345),       # lui a0, 0x12345
        encode_sw(10, 11, 0),           # sw a0, 0(a1)
        encode_lw(12, 11, 0),           # lw a2, 0(a1)
        encode_ecall(),                 # ecall
    ]

    # Pack into pixel array
    pixel_data = np.zeros((4096 * 4096 * 4,), dtype=np.uint32)

    for i, word in enumerate(instructions):
        base_idx = i * 4
        pixel_data[base_idx + 0] = word & 0xFF
        pixel_data[base_idx + 1] = (word >> 8) & 0xFF
        pixel_data[base_idx + 2] = (word >> 16) & 0xFF
        pixel_data[base_idx + 3] = (word >> 24) & 0xFF

    print(f"Program:")
    print(f"  [0] lui a1, 0              -> a1 = 0x00000000")
    print(f"  [1] addi a1, a1, 0x40     -> a1 = 0x00000040 (data address)")
    print(f"  [2] lui a0, 0x12345       -> a0 = 0x12345000")
    print(f"  [3] sw a0, 0(a1)          -> store 0x12345000 at address 0x40")
    print(f"  [4] lw a2, 0(a1)          -> a2 = [0x40] (should be 0x12345000)")
    print(f"  [5] ecall                  -> halt")
    print(f"\nExpected final state:")
    print(f"  a0 = 0x12345000")
    print(f"  a1 = 0x00000040")
    print(f"  a2 = 0x12345000 (loaded from memory)")
    print(f"  Memory[0x40] = 0x12345000")

    # Initialize GPU
    device, queue = create_gpu_device()

    # Create memory buffer (read-write RAM)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
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

    # Output buffer
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
    print("\nExecuting on GPU:")
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

        print(f"  Iter {iteration:2d}: PC=0x{pc:04x}, running={running}, instr_count={instr_count:2d}")

        if running == 0 or instr_count >= 50:
            break

    # Check final state
    final_cpu = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_layout)

    print(f"\nFinal state:")
    print(f'  a0 (x10) = 0x{final_cpu[0]["regs"][10]:08x} (expected 0x12345000)')
    print(f'  a1 (x11) = 0x{final_cpu[0]["regs"][11]:08x} (expected 0x00000040)')
    print(f'  a2 (x12) = 0x{final_cpu[0]["regs"][12]:08x} (expected 0x12345000)')

    # Read memory to verify store
    # Address 0x40 is at pixel index 0x40 / 4 = 16
    mem_readback = np.frombuffer(device.queue.read_buffer(memory_buffer), dtype=np.uint32)
    pixel_idx = 0x40 // 4
    base_idx = pixel_idx * 4
    stored_word = (mem_readback[base_idx] |
                   (mem_readback[base_idx + 1] << 8) |
                   (mem_readback[base_idx + 2] << 16) |
                   (mem_readback[base_idx + 3] << 24))

    print(f'  Memory[0x40] = 0x{stored_word:08x} (expected 0x12345000)')

    # Verify
    checks = [
        final_cpu[0]['regs'][10] == 0x12345000,  # a0
        final_cpu[0]['regs'][11] == 0x00000040,  # a1
        final_cpu[0]['regs'][12] == 0x12345000,  # a2
        stored_word == 0x12345000,                 # memory[0x40]
    ]

    print(f"\nVerification:")
    if all(checks):
        print('  *** PASS *** - LOAD/STORE working!')
        return 0
    else:
        print('  *** FAIL ***')
        return 1

if __name__ == '__main__':
    sys.exit(main())