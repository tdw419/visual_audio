"""
Debug WGSL shader to test output mechanism.
"""

import wgpu
import struct
import numpy as np
import asyncio

WGSL_SHADER_DEBUG = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

struct SpatialCPU {
    pc: vec2<u32>,
    registers: array<u32, 8>,
    memory: array<u32, 256>,
    running: u32,
    output_ptr: u32,
}

struct Uniforms {
    image_width: u32,
    output_buffer_size: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> cpus: array<SpatialCPU>;
@group(0) @binding(2) var<storage, read_write> output: array<u32>;
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    // DEBUG: Always write some output
    output[global_id.x * 100u + 0u] = 42u;
    output[global_id.x * 100u + 1u] = global_id.x;
    output[global_id.x * 100u + 2u] = uniforms.image_width;
}
"""

device = wgpu.utils.get_default_device()

# Create bind group layout
bind_group_layout = device.create_bind_group_layout(
    entries=[
        {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
        {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
    ]
)

pipeline_layout = device.create_pipeline_layout(
    bind_group_layouts=[bind_group_layout]
)

# Create shader module
shader_module = device.create_shader_module(code=WGSL_SHADER_DEBUG)

# Create compute pipeline
compute_pipeline = device.create_compute_pipeline(
    layout=pipeline_layout,
    compute={
        "module": shader_module,
        "entry_point": "main",
    },
)

print("✓ Debug shader compiled")

# Create buffers
from PIL import Image
img = Image.open("demo_glyph_simple.png")
rgba = np.array(img)
if rgba.shape[2] == 3:
    rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, dtype=rgba.dtype)])
flat_data = rgba.reshape(-1, 4)

rom_buffer = device.create_buffer(
    size=len(flat_data) * 4,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
)
device.queue.write_buffer(rom_buffer, 0, flat_data.tobytes())

num_cpus = 10
cpu_size = 1072
cpu_data = bytearray(num_cpus * cpu_size)
for i in range(num_cpus):
    offset = i * cpu_size
    struct.pack_into('II', cpu_data, offset, 0, 0)
    struct.pack_into('I', cpu_data, offset + 1064, 1)
    struct.pack_into('I', cpu_data, offset + 1068, 0)

cpus_buffer = device.create_buffer(
    size=len(cpu_data),
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)
device.queue.write_buffer(cpus_buffer, 0, cpu_data)

output_buffer = device.create_buffer(
    size=1024 * 4,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)

uniform_data = struct.pack('II', 16, 102)
uniform_buffer = device.create_buffer(
    size=8,
    usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
)
device.queue.write_buffer(uniform_buffer, 0, uniform_data)

# Create bind group
bind_group = device.create_bind_group(
    layout=compute_pipeline.get_bind_group_layout(0),
    entries=[
        {"binding": 0, "resource": {"buffer": rom_buffer, "offset": 0, "size": rom_buffer.size}},
        {"binding": 1, "resource": {"buffer": cpus_buffer, "offset": 0, "size": cpus_buffer.size}},
        {"binding": 2, "resource": {"buffer": output_buffer, "offset": 0, "size": output_buffer.size}},
        {"binding": 3, "resource": {"buffer": uniform_buffer, "offset": 0, "size": 8}},
    ],
)

# Execute
command_encoder = device.create_command_encoder()
compute_pass = command_encoder.begin_compute_pass()
compute_pass.set_pipeline(compute_pipeline)
compute_pass.set_bind_group(0, bind_group)
compute_pass.dispatch_workgroups(num_cpus)
compute_pass.end()
device.queue.submit([command_encoder.finish()])

# Read output
staging_buffer = device.create_buffer(
    size=output_buffer.size,
    usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
)

command_encoder = device.create_command_encoder()
command_encoder.copy_buffer_to_buffer(output_buffer, 0, staging_buffer, 0, output_buffer.size)
device.queue.submit([command_encoder.finish()])

staging_buffer.map_sync(wgpu.MapMode.READ)
output_data = staging_buffer.read_mapped()
staging_buffer.unmap()

values = struct.unpack(f'{output_buffer.size // 4}I', output_data)
non_zero = [v for v in values if v > 0]

print(f"Output values: {non_zero[:30]}")  # First 30 non-zero values