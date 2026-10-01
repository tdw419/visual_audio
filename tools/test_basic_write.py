"""
Test basic output write
"""
import wgpu
import struct

WGSL_MINIMAL_WRITE = """
@group(0) @binding(0) var<storage, read_write> output: array<u32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    output[global_id.x] = 42u;
}
"""

device = wgpu.utils.get_default_device()

output_buffer = device.create_buffer(
    size=40 * 4,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)

bind_group_layout = device.create_bind_group_layout(
    entries=[{"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}]
)
pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
shader_module = device.create_shader_module(code=WGSL_MINIMAL_WRITE)

compute_pipeline = device.create_compute_pipeline(
    layout=pipeline_layout,
    compute={"module": shader_module, "entry_point": "main"},
)

bind_group = device.create_bind_group(
    layout=compute_pipeline.get_bind_group_layout(0),
    entries=[{"binding": 0, "resource": {"buffer": output_buffer, "offset": 0, "size": output_buffer.size}}],
)

command_encoder = device.create_command_encoder()
compute_pass = command_encoder.begin_compute_pass()
compute_pass.set_pipeline(compute_pipeline)
compute_pass.set_bind_group(0, bind_group)
compute_pass.dispatch_workgroups(10)
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
print(f"Output values: {values[:10]}")
print(f"Expected: [42, 42, 42, 42, 42, 42, 42, 42, 42, 42]")
print(f"Success: {all(v == 42 for v in values[:10])}")