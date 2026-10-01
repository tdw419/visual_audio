#!/usr/bin/env python3
"""
Minimal test to trace timer state transitions.

Tests the exact sequence xv6 uses:
1. Initial state (mtimecmp=0, timer_fired=0)
2. Write stimecmp to value in future (timer_fired should clear)
3. Let mtime cross the threshold
4. Verify edge trigger fires exactly once
"""

import struct
import numpy as np
from pathlib import Path
import wgpu
import wgpu.utils
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE

# Minimal test program that loops and writes progress
TEST_ASM = [
    # Basic setup: zero registers
    0x00000293,  # li t0, 0
    0x00000313,  # li t1, 0
    0x00000393,  # li t2, 0

    # Main loop: increment counter, check timer, repeat
    # Loop body (~20 iterations before timer should fire)
    0x00128293,  # addi t0, t0, 1  # increment loop counter
    0x02029263,  # bne t0, zero, end_loop  # if t0 == 32, exit

    # Read current time (TIME CSR) - just to show progress
    0xc010222f,  # rdtime t0  # read mtime into t0

    # Jump back to loop start
    0xffdff06f,  # j loop_start

    # End: halt with ebreak
    0x00100073,  # ebreak

    # Loop start label
    0xffdff06f,  # j loop_body  # infinite loop
]

# Convert test assembly to RGBA pixels
def build_test_binary():
    instr_count = len(TEST_ASM)
    pixels = np.zeros((instr_count, 4), dtype=np.uint8)
    for i, instr in enumerate(TEST_ASM):
        pixels[i] = [
            instr & 0xFF,
            (instr >> 8) & 0xFF,
            (instr >> 16) & 0xFF,
            (instr >> 24) & 0xFF,
        ]
    return pixels

def main():
    print("=" * 70)
    print("Timer State Machine Test")
    print("=" * 70)

    pixel_data = build_test_binary()
    print(f"Test binary: {len(pixel_data)} instructions")

    # Memory layout: test code at 0x80000000
    MEMORY_SIZE = 2 * 1024 * 1024  # 2MB
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint8)

    # Place test code at 0x80000000
    memory[:len(pixel_data)] = pixel_data

    # CPU state: start at test code
    entry_point = 0x80000000
    cpu_state = make_cpu_state(entry_point, priv_mode=3)  # M-mode

    # Manually set up delegation as xv6 does
    cpu_state[0]['medeleg'] = [0xFFFF, 0]
    cpu_state[0]['mideleg'] = [0xFFFF, 0]

    # Enable SIE (bit 1 in mstatus.x for SIE, bit 3 for MIE)
    # Start with MIE=1 so we can take timer interrupts
    cpu_state[0]['mstatus'][0] = 0x08  # Set MIE (bit 3)

    print(f"Initial CPU state:")
    print(f"  PC: 0x{entry_point:016x}")
    print(f"  mstatus: 0x{cpu_state[0]['mstatus'][0]:08x}:{cpu_state[0]['mstatus'][1]:08x}")
    print(f"  mideleg: 0x{cpu_state[0]['mideleg'][0]:08x}")
    print(f"  mtimecmp: {cpu_state[0]['mtimecmp_low']}:{cpu_state[0]['mtimecmp_high']}")
    print(f"  timer_fired: {cpu_state[0]['timer_fired']}")

    # Load WGSL shader
    shader_path = Path(__file__).parent / 'tools' / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()

    device = wgpu.utils.get_default_device()
    queue = device.queue

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
    )
    uniform_buffer = device.create_buffer(
        size=4,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )

    # Initial uploads
    queue.write_buffer(memory_buffer, 0, memory.tobytes())
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    queue.write_buffer(uniform_buffer, 0, np.array([1000], dtype=np.uint32).tobytes())  # 1000 instructions
    queue.write_buffer(input_buffer, 0, np.zeros(256, dtype=np.uint32).tobytes())

    # Pipeline setup
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
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': 4}},
            {'binding': 4, 'resource': {'buffer': input_buffer, 'offset': 0, 'size': 1024}},
        ]
    )

    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )

    print("\n[TEST 1] Initial state - timer not enabled (mtimecmp=0)")
    print("Running 1000 instructions...")
    command = device.create_command_encoder()
    command.set_pipeline(pipeline)
    command.set_bind_group(0, bind_group, [], 0, 999999)
    command.dispatch(1, 1, 1)
    command.copy_buffer_to_buffer(cpu_buffer, 0, cpu_buffer, 0, cpu_state.nbytes)
    queue.submit([command.finish()])

    cpu_readback = np.frombuffer(queue.read_buffer(cpu_buffer), dtype=CPU_DTYPE)[0]
    print(f"  mtime: {cpu_readback['mtime_low']}:{cpu_readback['mtime_high']}")
    print(f"  mtimecmp: {cpu_readback['mtimecmp_low']}:{cpu_readback['mtimecmp_high']}")
    print(f"  timer_fired: {cpu_readback['timer_fired']}")
    print(f"  MIP: 0x{cpu_readback['mip'][0]:08x}")
    print(f"  mcause: 0x{cpu_readback['mcause'][0]:08x}")
    print(f"  instr_count: {cpu_readback['instr_count']}")

    print("\n[TEST 2] Simulate timerinit() - write stimecmp to future")
    # Write stimecmp = current_time + 500
    current_time_low = cpu_readback['mtime_low']
    current_time_high = cpu_readback['mtime_high']
    target_time = current_time_low + 500

    cpu_state[0]['mtimecmp_low'] = target_time
    cpu_state[0]['mtimecmp_high'] = current_time_high
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())

    print(f"  Set mtimecmp to: {cpu_state[0]['mtimecmp_low']}:{cpu_state[0]['mtimecmp_high']}")
    print(f"  Current mtime: {current_time_low}:{current_time_high}")
    print(f"  Gap: {target_time - current_time_low} cycles")

    print("\n[TEST 3] Run until timer crosses (should fire exactly once)")
    # Run enough instructions to cross
    command = device.create_command_encoder()
    command.set_pipeline(pipeline)
    command.set_bind_group(0, bind_group, [], 0, 999999)
    command.dispatch(1, 1, 1)
    command.copy_buffer_to_buffer(cpu_buffer, 0, cpu_buffer, 0, cpu_state.nbytes)
    queue.submit([command.finish()])

    cpu_readback = np.frombuffer(queue.read_buffer(cpu_buffer), dtype=CPU_DTYPE)[0]
    print(f"  mtime: {cpu_readback['mtime_low']}:{cpu_readback['mtime_high']}")
    print(f"  mtimecmp: {cpu_readback['mtimecmp_low']}:{cpu_readback['mtimecmp_high']}")
    print(f"  timer_fired: {cpu_readback['timer_fired']}")
    print(f"  MIP: 0x{cpu_readback['mip'][0]:08x}")
    print(f"  MIP bits set:")
    if cpu_readback['mip'][0] & 0x80:
        print("    MTIP (bit 7) - Machine timer interrupt")
    if cpu_readback['mip'][0] & 0x20:
        print("    STIP (bit 5) - Supervisor timer interrupt")
    print(f"  mcause: 0x{cpu_readback['mcause'][0]:08x}")
    print(f"  scause: 0x{cpu_readback['scause'][0]:08x}")
    print(f"  instr_count: {cpu_readback['instr_count']}")
    print(f"  PC: 0x{cpu_readback['pc'][0]:08x}:{cpu_readback['pc'][1]:08x}")

    print("\n[TEST 4] Run more - should NOT fire again (edge-triggered)")
    command = device.create_command_encoder()
    command.set_pipeline(pipeline)
    command.set_bind_group(0, bind_group, [], 0, 999999)
    command.dispatch(1, 1, 1)
    command.copy_buffer_to_buffer(cpu_buffer, 0, cpu_buffer, 0, cpu_state.nbytes)
    queue.submit([command.finish()])

    cpu_readback2 = np.frombuffer(queue.read_buffer(cpu_buffer), dtype=CPU_DTYPE)[0]
    print(f"  mtime: {cpu_readback2['mtime_low']}:{cpu_readback2['mtime_high']}")
    print(f"  timer_fired: {cpu_readback2['timer_fired']}")
    print(f"  MIP: 0x{cpu_readback2['mip'][0]:08x}")

    # Verify edge-trigger behavior
    if cpu_readback['timer_fired'] == 1 and cpu_readback2['timer_fired'] == 1:
        print("\n✓ PASS: Timer fired exactly once (edge-triggered)")
    else:
        print(f"\n✗ FAIL: timer_fired went {cpu_readback['timer_fired']} -> {cpu_readback2['timer_fired']}")

    if cpu_readback['mip'][0] & (0x80 | 0x20):
        print("✓ PASS: MIP bits set when timer crossed")
    else:
        print("✗ FAIL: MIP bits NOT set when timer crossed")

if __name__ == '__main__':
    main()