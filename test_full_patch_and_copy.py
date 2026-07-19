"""
Patch-and-Copy: Full End-to-End Test

This test completes the loop:
1. Spatial compiler generates program code
2. Spatial CPUs execute the generated code
3. Result is read back

Expected: Program computes 42 + 10 = 52
"""
import wgpu
import struct
import numpy as np
import sys

# Load the spatial compiler shader
with open('tools/PATCH_AND_COPY.wgsl', 'r') as f:
    COMPILER_SHADER = f.read()

# Load the spatial execution shader
with open('tools/wgsl_spatial_glyph_working.py', 'r') as f:
    exec_shader_py = f.read()
    import re
    match = re.search(r'WGSL_SHADER_MINIMAL = """(.+?)"""', exec_shader_py, re.DOTALL)
    if match:
        EXECUTION_SHADER = match.group(1)
    else:
        print("ERROR: Could not extract WGSL_SHADER_MINIMAL")
        sys.exit(1)

def test_full_patch_and_copy():
    print("=" * 70)
    print("PATCH-AND-COPY: FULL END-TO-END TEST")
    print("=" * 70)

    device = wgpu.utils.get_default_device()

    # ============================================================
    # PHASE 1: SPATIAL COMPILATION
    # ============================================================
    print("\n[PHASE 1] Spatial Compiling (GPU writes its own code)")

    # Create template atlas
    atlas_data = np.array([
        [236, 80, 80, 255],   # LDI
        [80, 236, 120, 255],  # ADD
        [247, 83, 80, 255],   # PRT
        [255, 0, 0, 255],     # HLT
    ], dtype=np.uint32)

    atlas_buffer = device.create_buffer(
        size=len(atlas_data) * 16,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(atlas_buffer, 0, atlas_data.tobytes())

    # Create VRAM (will become ROM for execution)
    vram_width = 10
    vram_height = 5
    vram_size = vram_width * vram_height
    vram_data = np.zeros((vram_size, 4), dtype=np.uint32)

    vram_buffer = device.create_buffer(
        size=len(vram_data) * 16,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    device.queue.write_buffer(vram_buffer, 0, vram_data.tobytes())

    # Create write head
    write_head_data = struct.pack('II', 0, 0)
    write_head_buffer = device.create_buffer(
        size=8,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    device.queue.write_buffer(write_head_buffer, 0, write_head_data)

    # Create uniforms
    uniform_data = struct.pack('III', vram_width, vram_height, len(atlas_data))
    uniform_buffer = device.create_buffer(
        size=12,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(uniform_buffer, 0, uniform_data)

    # Build compiler pipeline
    compiler_bind_group_layout = device.create_bind_group_layout(
        entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
        ]
    )

    compiler_pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[compiler_bind_group_layout])
    compiler_shader_module = device.create_shader_module(code=COMPILER_SHADER)
    compiler_pipeline = device.create_compute_pipeline(
        layout=compiler_pipeline_layout,
        compute={"module": compiler_shader_module, "entry_point": "main"},
    )

    compiler_bind_group = device.create_bind_group(
        layout=compiler_pipeline.get_bind_group_layout(0),
        entries=[
            {"binding": 0, "resource": {"buffer": atlas_buffer, "offset": 0, "size": atlas_buffer.size}},
            {"binding": 1, "resource": {"buffer": vram_buffer, "offset": 0, "size": vram_buffer.size}},
            {"binding": 2, "resource": {"buffer": write_head_buffer, "offset": 0, "size": write_head_buffer.size}},
            {"binding": 3, "resource": {"buffer": uniform_buffer, "offset": 0, "size": 12}},
        ],
    )

    # Execute compiler
    command_encoder = device.create_command_encoder()
    compute_pass = command_encoder.begin_compute_pass()
    compute_pass.set_pipeline(compiler_pipeline)
    compute_pass.set_bind_group(0, compiler_bind_group)
    compute_pass.dispatch_workgroups(1)
    compute_pass.end()
    device.queue.submit([command_encoder.finish()])

    print(f"  ✓ Compiler executed")

    # ============================================================
    # PHASE 2: SPATIAL EXECUTION
    # ============================================================
    print("\n[PHASE 2] Spatial Execution (GPUs execute GPU-generated code)")

    # Create CPU instances
    num_cpus = 1
    cpu_size = 1072
    cpu_data = bytearray(num_cpus * cpu_size)
    struct.pack_into('II', cpu_data, 0, 0, 0)  # PC at (0, 0)
    struct.pack_into('I', cpu_data, 1064, 1)  # running = 1
    struct.pack_into('I', cpu_data, 1068, 0)  # output_ptr = 0

    cpus_buffer = device.create_buffer(
        size=len(cpu_data),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    device.queue.write_buffer(cpus_buffer, 0, cpu_data)

    # Create output buffer
    output_buffer = device.create_buffer(
        size=40 * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )

    # Create execution uniforms
    exec_uniform_data = struct.pack('II', vram_width, 40)
    exec_uniform_buffer = device.create_buffer(
        size=8,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(exec_uniform_buffer, 0, exec_uniform_data)

    # Build execution pipeline
    exec_bind_group_layout = device.create_bind_group_layout(
        entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
        ]
    )

    exec_pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[exec_bind_group_layout])
    exec_shader_module = device.create_shader_module(code=EXECUTION_SHADER)
    exec_pipeline = device.create_compute_pipeline(
        layout=exec_pipeline_layout,
        compute={"module": exec_shader_module, "entry_point": "main"},
    )

    exec_bind_group = device.create_bind_group(
        layout=exec_pipeline.get_bind_group_layout(0),
        entries=[
            {"binding": 0, "resource": {"buffer": vram_buffer, "offset": 0, "size": vram_buffer.size}},  # VRAM is now ROM!
            {"binding": 1, "resource": {"buffer": cpus_buffer, "offset": 0, "size": cpus_buffer.size}},
            {"binding": 2, "resource": {"buffer": output_buffer, "offset": 0, "size": output_buffer.size}},
            {"binding": 3, "resource": {"buffer": exec_uniform_buffer, "offset": 0, "size": 8}},
        ],
    )

    # Execute CPUs
    command_encoder = device.create_command_encoder()
    for _ in range(50):  # Enough dispatches to execute the full program
        compute_pass = command_encoder.begin_compute_pass()
        compute_pass.set_pipeline(exec_pipeline)
        compute_pass.set_bind_group(0, exec_bind_group)
        compute_pass.dispatch_workgroups(num_cpus)
        compute_pass.end()
    device.queue.submit([command_encoder.finish()])

    print(f"  ✓ Executed {num_cpus} spatial CPU for 50 dispatches")

    # ============================================================
    # PHASE 3: READ RESULTS
    # ============================================================
    print("\n[PHASE 3] Reading Results")

    # Read output
    output_staging = device.create_buffer(
        size=output_buffer.size,
        usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
    )

    command_encoder = device.create_command_encoder()
    command_encoder.copy_buffer_to_buffer(output_buffer, 0, output_staging, 0, output_buffer.size)
    device.queue.submit([command_encoder.finish()])

    output_staging.map_sync(wgpu.MapMode.READ)
    output_data = output_staging.read_mapped()
    output_staging.unmap()

    values = struct.unpack(f'{output_buffer.size // 4}I', output_data)

    # Filter out zeros (PRT writes at different offset)
    # Output is written immediately, no index offset
    result = values[0] if values[0] != 0 else None

    print(f"\n{'=' * 70}")
    print(f"RESULT")
    print(f"{'=' * 70}")

    expected_result = 52  # 42 + 10

    if result == expected_result:
        print(f"\n🎉 SUCCESS: GPU executed GPU-generated code!")
        print(f"   Expected: {expected_result} (42 + 10)")
        print(f"   Got: {result}")
        print(f"\n   The GPU wrote code. The GPU executed that code.")
        print(f"   The host CPU was never involved in the program content.")
        print(f"\n   This is the Patch-and-Copy architecture in action.")
        return True
    else:
        print(f"\n✗ FAILED: Unexpected result")
        print(f"   Expected: {expected_result}")
        print(f"   Got: {result}")
        print(f"   Full output: {values[:10]}")
        return False

if __name__ == '__main__':
    success = test_full_patch_and_copy()
    sys.exit(0 if success else 1)