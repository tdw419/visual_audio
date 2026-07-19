"""
Debug buffer size issue
"""
import wgpu
import struct
import numpy as np

WGSL_MINIMAL = """
struct Pixel {
    r: u32, g: u32, b: u32, a: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
}
"""

device = wgpu.utils.get_default_device()

# Create test image: 3x1 with LDI r0 5
test_img = np.array([
    [[236, 80, 80, 255]],  # LDI
    [[50, 50, 50, 255]],   # r0
    [[0, 0, 6, 255]],      # 5
], dtype=np.uint8)
flat_data = test_img.reshape(-1, 4)

print(f"flat_data shape: {flat_data.shape}")
print(f"flat_data size (bytes): {len(flat_data.tobytes())}")

rom_buffer = device.create_buffer(
    size=len(flat_data) * 4,  # 3 * 4 * 4 = 48
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
)
device.queue.write_buffer(rom_buffer, 0, flat_data.tobytes())

print(f"ROM buffer size: {rom_buffer.size}")

bind_group_layout = device.create_bind_group_layout(
    entries=[{"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}}]
)
pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
shader_module = device.create_shader_module(code=WGSL_MINIMAL)

compute_pipeline = device.create_compute_pipeline(
    layout=pipeline_layout,
    compute={"module": shader_module, "entry_point": "main"},
)

# Bind with EXACT size
bind_group = device.create_bind_group(
    layout=compute_pipeline.get_bind_group_layout(0),
    entries=[{"binding": 0, "resource": {"buffer": rom_buffer, "offset": 0, "size": rom_buffer.size}}],
)

command_encoder = device.create_command_encoder()
compute_pass = command_encoder.begin_compute_pass()
compute_pass.set_pipeline(compute_pipeline)
compute_pass.set_bind_group(0, bind_group)
compute_pass.dispatch_workgroups(1)
compute_pass.end()
try:
    device.queue.submit([command_encoder.finish()])
    print("✓ Command submitted successfully")
except Exception as e:
    print(f"✗ Command failed: {e}")