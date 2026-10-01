"""
Isolate the problematic WGSL code from the full shader.
"""

import wgpu

device = wgpu.utils.get_default_device()

def test_shader(name, shader_code, bind_group_layout_entries):
    """Test a shader and report results."""
    try:
        bind_group_layout = device.create_bind_group_layout(
            entries=bind_group_layout_entries
        )

        pipeline_layout = device.create_pipeline_layout(
            bind_group_layouts=[bind_group_layout]
        )

        shader_module = device.create_shader_module(code=shader_code)

        compute_pipeline = device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={
                "module": shader_module,
                "entry_point": "main",
            },
        )

        print(f"✓ {name}")
        return True
    except Exception as e:
        print(f"✗ {name}: {e}")
        return False

# Test with 8 registers like the real shader
test6 = """
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

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> cpus: array<SpatialCPU>;
@group(0) @binding(2) var<storage, read_write> output: array<u32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var cpu = cpus[global_id.x];
    output[global_id.x] = cpu.registers[0] + 1u;
    cpus[global_id.x] = cpu;
}
"""

# Test with full CPU state manipulation
test10 = """
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

fn load_pixel(x: u32, y: u32) -> vec3<u32> {
    let index = y * uniforms.image_width + x;
    let pixel = rom[index];
    return vec3<u32>(pixel.r, pixel.g, pixel.b);
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var cpu = cpus[global_id.x];
    if (cpu.running == 0u) { return; }

    let pixel = load_pixel(cpu.pc.x, cpu.pc.y);
    cpu.pc.x = cpu.pc.x + 1u;

    if (pixel.r == 236u && pixel.g == 80u && pixel.b == 80u) {
        cpu.registers[0] = 5u;
    }

    cpus[global_id.x] = cpu;
}
"""

bind_entries_3buf = [
    {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
    {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
    {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
]

bind_entries_full = [
    {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
    {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
    {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
    {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
]

print("Testing shader complexity...")

test_shader("Test 6: 8 registers + 256 memory", test6, bind_entries_3buf)
test_shader("Test 10: Full CPU state with load_pixel", test10, bind_entries_full)

print("\nDone!")