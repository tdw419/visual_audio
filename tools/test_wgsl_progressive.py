"""
Progressive WGSL shader tests to isolate Naga crash.
"""

import wgpu

device = wgpu.utils.get_default_device()

def test_shader(name, shader_code, bind_group_layout_entries):
    """Test a shader and report results."""
    try:
        # Create bind group layout
        bind_group_layout = device.create_bind_group_layout(
            entries=bind_group_layout_entries
        )

        pipeline_layout = device.create_pipeline_layout(
            bind_group_layouts=[bind_group_layout]
        )

        # Create shader module
        shader_module = device.create_shader_module(code=shader_code)

        # Create compute pipeline
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

# Test 1: Basic shader
test1 = """
@group(0) @binding(0) var<storage, read> input: array<u32>;
@group(0) @binding(1) var<storage, read_write> output: array<u32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    output[global_id.x] = input[global_id.x] + 1u;
}
"""

# Test 2: With struct
test2 = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> output: array<u32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let pixel = rom[global_id.x];
    output[global_id.x] = pixel.r + pixel.g + pixel.b;
}
"""

# Test 3: With helper function
test3 = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> output: array<u32>;

fn get_opcode(pixel: Pixel) -> u32 {
    if (pixel.r == 236u) { return 0u; }
    return 1u;
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let pixel = rom[global_id.x];
    output[global_id.x] = get_opcode(pixel);
}
"""

# Test 4: With multiple conditions
test4 = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> output: array<u32>;

fn get_opcode(pixel: Pixel) -> u32 {
    if (pixel.r == 236u && pixel.g == 80u) { return 0u; }
    if (pixel.r == 80u && pixel.g == 236u) { return 1u; }
    return 2u;
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let pixel = rom[global_id.x];
    output[global_id.x] = get_opcode(pixel);
}
"""

# Test 5: With CPU struct
test5 = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

struct SpatialCPU {
    pc: vec2<u32>,
    registers: array<u32, 2>,
    running: u32,
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

bind_entries_simple = [
    {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
    {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
]

bind_entries_complex = [
    {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
    {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
    {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
]

print("Testing progressive WGSL shaders...")

test_shader("Test 1: Basic", test1, bind_entries_simple)
test_shader("Test 2: With Pixel struct", test2, bind_entries_simple)
test_shader("Test 3: With helper function", test3, bind_entries_simple)
test_shader("Test 4: Multiple conditions", test4, bind_entries_simple)
test_shader("Test 5: With CPU struct", test5, bind_entries_complex)

print("\nDone!")