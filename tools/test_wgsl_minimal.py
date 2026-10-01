"""
Minimal WGSL test to debug Naga compilation issue.
"""

import wgpu

print("Testing minimal WGSL compilation...")

# Minimal shader
minimal_shader = """
@group(0) @binding(0) var<storage, read> input: array<u32>;
@group(0) @binding(1) var<storage, read_write> output: array<u32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let idx = global_id.x;
    if (idx < arrayLength(&output)) {
        output[idx] = input[idx] + 1u;
    }
}
"""

device = wgpu.utils.get_default_device()

# Create bind group layout
bind_group_layout = device.create_bind_group_layout(
    entries=[
        {
            "binding": 0,
            "visibility": wgpu.ShaderStage.COMPUTE,
            "buffer": {
                "type": wgpu.BufferBindingType.read_only_storage,
            },
        },
        {
            "binding": 1,
            "visibility": wgpu.ShaderStage.COMPUTE,
            "buffer": {
                "type": wgpu.BufferBindingType.storage,
            },
        },
    ]
)

pipeline_layout = device.create_pipeline_layout(
    bind_group_layouts=[bind_group_layout]
)

# Create shader module
print("Creating shader module...")
shader_module = device.create_shader_module(code=minimal_shader)

# Create compute pipeline
print("Creating compute pipeline...")
compute_pipeline = device.create_compute_pipeline(
    layout=pipeline_layout,
    compute={
        "module": shader_module,
        "entry_point": "main",
    },
)

print("✓ Minimal WGSL test passed!")
print("  Device:", device.adapter.info.vendor)
print("  Backend:", device.adapter.info.backend_type)