#!/usr/bin/env python3
"""
Test harness for RISC-V GPU Emulator (Phase 1)

Tests the WGSL RISC-V CPU with LUI, ADDI, and JAL instructions.

Usage:
    python3 test_riscv_gpu.py
"""

import wgpu
import numpy as np
from pathlib import Path


def load_wgsl_shader(path: str) -> str:
    """Load WGSL shader from file."""
    return Path(path).read_text()


def create_gpu_device():
    """Initialize wgpu device."""
    import wgpu.utils
    device = wgpu.utils.get_default_device()
    queue = device.queue
    return device, queue


def load_pixel_program(pixel_path: str) -> np.ndarray:
    """Load program pixels from .npy file."""
    return np.load(pixel_path)


def main():
    print("=" * 60)
    print("RISC-V GPU Emulator Test Harness (Phase 1)")
    print("=" * 60)

    # Initialize GPU
    print("\n[1] Initializing GPU...")
    device, queue = create_gpu_device()
    print(f"    Device: {device.adapter.info.device}")

    # Load shader
    print("\n[2] Loading WGSL shader...")
    shader_code = load_wgsl_shader('tools/RISCV_CPU.wgsl')

    # Load test program pixels
    print("\n[3] Loading test program...")
    pixels = load_pixel_program('kernel_minimal_pixels.npy')

    # Instructions in the test program:
    print("\n    Program instructions:")
    print("      0: 0x00100537  lui   a0, 0x00100    ; a0 = 0x00100000")
    print("      1: 0x01100513  addi  a0, a0, 0x100  ; a0 = 0x00100100")
    print("      2: 0x02a00593  addi  a1, x0, 42     ; a1 = 42")
    print("      3: 0x01700613  addi  a2, x0, 23     ; a2 = 23")
    print("      4: 0x00b586b3  add   a3, a1, a2     ; a3 = 65")
    print("      5: 0x00000097  lui   ra, 0x00000    ; ra = 0")
    print("      6: 0x00000073  ecall                 ; halt")

    # Expected register values:
    print("\n    Expected final state:")
    print("      a0 (x10) = 0x00100100")
    print("      a1 (x11) = 42")
    print("      a2 (x12) = 23")
    print("      a3 (x13) = 65")
    print("      ra (x1)  = 0")

    # Reshape pixels to 1D array of InstructionPixel structs
    pixel_data = pixels.reshape(-1, 4).astype(np.uint32)

    # Create buffers
    print("\n[4] Creating GPU buffers...")

    # Memory buffer (program code) - binding 0
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
    print(f"    Memory buffer: {pixel_data.shape[0]} pixels ({pixel_data.nbytes} bytes)")

    cpu_layout = np.dtype([
        ('pc', np.uint32, 2),
        ('regs', np.uint32, (32, 2)),
        ('running', np.uint32),
        ('instr_count', np.uint32),
        ('output_ptr', np.uint32),
        ('padding', np.uint32),
    ])
    cpu_state = np.zeros(1, dtype=cpu_layout)
    cpu_state[0]['pc'] = 0          # Start at PC=0
    cpu_state[0]['running'] = 1     # CPU is running
    cpu_state[0]['instr_count'] = 0

    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    print(f"    CPU buffer: 1 instance ({cpu_state.nbytes} bytes)")

    # Output buffer - binding 2
    output_buffer = device.create_buffer(
        size=4096,  # 1024 u32 words (4KB) - plenty for output
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
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
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    # Create bind group
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': pixel_data.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 4096}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instructions.nbytes}},
        ]
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
        running = cpu_readback[0]['running']
        pc = cpu_readback[0]['pc'][0]
        instr_count = cpu_readback[0]['instr_count']

        print(f"    Iter {iteration:2d}: PC=0x{pc:04x}, running={running}, instr_count={instr_count}")

        if running == 0:
            break

    # Read final CPU state
    print("\n[7] Reading final CPU state...")
    final_cpu = np.frombuffer(
        device.queue.read_buffer(cpu_buffer),
        dtype=cpu_layout
    )[0]

    # Read output buffer
    output_data = np.frombuffer(
        device.queue.read_buffer(output_buffer),
        dtype=np.uint32
    )

    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nInstructions executed: {final_cpu['instr_count']}")
    print(f"Final PC: 0x{final_cpu['pc'][0]:08x}")
    print(f"CPU running: {final_cpu['running']}")

    print("\nRegister file:")
    print(f"  x0  (zero): 0x{final_cpu['regs'][0][0]:08x} (should be 0x00000000)")
    print(f"  x1  (ra):   0x{final_cpu['regs'][1][0]:08x} (should be 0x00000000)")
    print(f"  x10 (a0):   0x{final_cpu['regs'][10][0]:08x} (should be 0x00100100)")
    print(f"  x11 (a1):   0x{final_cpu['regs'][11][0]:08x} (should be 0x0000002a = 42)")
    print(f"  x12 (a2):   0x{final_cpu['regs'][12][0]:08x} (should be 0x00000017 = 23)")
    print(f"  x13 (a3):   0x{final_cpu['regs'][13][0]:08x} (should be 0x00000041 = 65)")

    print("\nOutput buffer (first 8 words):")
    for i in range(8):
        print(f"  output[{i}] = 0x{output_data[i]:08x}")

    # Verify results
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    passed = True

    # Check critical registers
    checks = [
        ("x0 is zero", final_cpu['regs'][0][0] == 0),
        ("ra = 0", final_cpu['regs'][1][0] == 0),
        ("a0 = 0x00100100", final_cpu['regs'][10][0] == 0x00100100),
        ("a1 = 42", final_cpu['regs'][11][0] == 42),
        ("a2 = 23", final_cpu['regs'][12][0] == 23),
        ("a3 = 65", final_cpu['regs'][13][0] == 65),
        ("instr_count = 6", final_cpu['instr_count'] == 6),
        ("running = 0 (halted)", final_cpu['running'] == 0),
    ]

    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if not result:
            passed = False

    print("\n" + "=" * 60)
    if passed:
        print("ALL TESTS PASSED! GPU RISC-V emulator working!")
    else:
        print("SOME TESTS FAILED - see details above")
    print("=" * 60)

    return 0 if passed else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())