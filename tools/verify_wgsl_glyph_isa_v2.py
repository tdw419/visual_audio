#!/usr/bin/env python3
"""
Verify tools/wgsl_glyph_isa_v2.py against tools/glyph_isa_v2.py's GlyphCPUv2
(ground truth), using the same Turing-complete program from
test_glyph_isa_v2.py::test_turing_complete_features - PUSH, CALL, a
subroutine that shifts a stack-passed value, and RET.
"""

import sys
from pathlib import Path

import numpy as np
import wgpu
import wgpu.utils

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array

PROGRAM = [
    "LDI r1 5",       # 0: r1=5
    "LDI r2 3",       # 1: r2=3
    "AND r1 r2",      # 2: r1=1
    "LDI r2 2",       # 3: r2=2
    "SHL r1 r2",      # 4: r1=4
    "PUSH r1",        # 5: Stack=[4]
    "CALL 1,1",       # 6: Push return PC (x=28, y=0). Jump to x=4, y=1 (idx 9)
    "POP r4",         # 7: Pop modified value from stack into r4
    "HALT",           # 8: Main program halts here
    # Subroutine at (1,1) - idx 9
    "POP r6",         # 9: Pop return address into r6
    "POP r5",         # 10: Pop 4 into r5
    "LDI r7 1",       # 11: r7=1
    "SHL r5 r7",      # 12: r5 = 4 << 1 = 8
    "PUSH r5",        # 13: Push 8 onto stack
    "PUSH r6",        # 14: Push return address back
    "RET",            # 15: Jump back to (x=28, y=0) which is idx 7
] + ["HALT"] * 16


def run_python_ground_truth(opcode_map, image):
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    cpu.registers[31] = 0
    cpu.run(image.copy(), max_instructions=200)
    return cpu


def run_wgsl(opcode_map, image):
    shader_src = build_shader(opcode_map)

    device = wgpu.utils.get_default_device()
    queue = device.queue

    pixel_data = image.astype(np.uint32)
    n_pixels = pixel_data.shape[0] * pixel_data.shape[1]
    # Pack into RGBA32 (Pixel struct = 4 x u32)
    rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
    flat = pixel_data.reshape(n_pixels, 3)
    rgba[:, 0:3] = flat

    image_buffer = device.create_buffer(
        size=rgba.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(image_buffer, 0, rgba.tobytes())

    cpu_state, cpu_dtype = make_cpu_state_array(1)
    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())

    output_buffer_size = 64
    output_buffer = device.create_buffer(
        size=output_buffer_size * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(output_buffer, 0, np.zeros(output_buffer_size, dtype=np.uint32).tobytes())

    uniforms = np.array(
        [(image.shape[1], image.shape[0], output_buffer_size)],
        dtype=np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
                         ('output_buffer_size', np.uint32)]),
    )
    uniform_buffer = device.create_buffer(
        size=uniforms.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, uniforms.tobytes())

    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': image_buffer, 'offset': 0, 'size': rgba.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': output_buffer_size * 4}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': uniforms.nbytes}},
        ],
    )

    shader_module = device.create_shader_module(code=shader_src)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': shader_module, 'entry_point': 'main'},
    )

    running = 1
    for _ in range(200):
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])

        readback = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_dtype)[0]
        running = readback['running']
        if running == 0:
            break

    return readback


def main():
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    image = assembler.assemble(PROGRAM, width_instrs=8)

    print(f"Assembled image: {image.shape}")

    py_cpu = run_python_ground_truth(opcode_map, image)
    print(f"Python ground truth: r1={py_cpu.registers[1]} r4={py_cpu.registers[4]} r31={py_cpu.registers[31]}")

    gpu_cpu = run_wgsl(opcode_map, image)
    r1 = int(gpu_cpu['registers'][1])
    r4 = int(gpu_cpu['registers'][4])
    r31 = int(gpu_cpu['registers'][31])
    print(f"WGSL GPU result:      r1={r1} r4={r4} r31={r31}")

    ok = (r1 == py_cpu.registers[1] == 4) and (r4 == py_cpu.registers[4] == 8)
    print("MATCH" if ok else "MISMATCH")

    opcode_map.close()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
