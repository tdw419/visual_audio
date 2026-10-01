"""
Test LDI opcode execution in isolation
"""
import wgpu
import struct
import numpy as np

WGSL_LDI_ONLY = """
struct Pixel {
    r: u32, g: u32, b: u32, a: u32,
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

fn advance_pc(pc: vec2<u32>) -> vec2<u32> {
    var new_pc = pc;
    new_pc.x = new_pc.x + 1u;
    if (new_pc.x >= uniforms.image_width) {
        new_pc.x = 0u;
        new_pc.y = new_pc.y + 1u;
    }
    return new_pc;
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var cpu = cpus[global_id.x];
    if (cpu.running == 0u) { return; }

    let pixel = load_pixel(cpu.pc.x, cpu.pc.y);

    // Debug: write current pixel to output
    let trace_offset = global_id.x * 10u + cpu.output_ptr;
    if (cpu.output_ptr < 10u) {
        output[trace_offset] = pixel.r;
        output[trace_offset + 1u] = pixel.g;
        output[trace_offset + 2u] = pixel.b;
        cpu.output_ptr = cpu.output_ptr + 3u;
    }

    // Opcodes
    if (pixel.r == 236u && pixel.g == 80u && pixel.b == 80u) {
        // LDI: load immediate
        // Next pixel is register, next is value
        let reg_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let reg_num = (reg_pixel.r - 50u) / 25u;

        let val_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let val = val_pixel.b - 1u;

        cpu.registers[reg_num] = val;
        output[trace_offset + 3u] = 999u; // Debug: executed LDI
    }

    // Always advance PC
    cpu.pc = advance_pc(cpu.pc);

    cpus[global_id.x] = cpu;
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

rom_buffer = device.create_buffer(
    size=len(flat_data) * 4,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
)
device.queue.write_buffer(rom_buffer, 0, flat_data.tobytes())

num_cpus = 1
cpu_size = 1072
cpu_data = bytearray(num_cpus * cpu_size)
struct.pack_into('II', cpu_data, 0, 0, 0)  # PC at (0,0)
struct.pack_into('I', cpu_data, 1064, 1)  # running = 1
struct.pack_into('I', cpu_data, 1068, 0)  # output_ptr = 0

cpus_buffer = device.create_buffer(
    size=len(cpu_data),
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)
device.queue.write_buffer(cpus_buffer, 0, cpu_data)

output_buffer = device.create_buffer(
    size=40 * 4,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)

uniform_data = struct.pack('II', 3, 10)
uniform_buffer = device.create_buffer(
    size=8,
    usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
)
device.queue.write_buffer(uniform_buffer, 0, uniform_data)

bind_group_layout = device.create_bind_group_layout(
    entries=[
        {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
        {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
    ]
)

pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
shader_module = device.create_shader_module(code=WGSL_LDI_ONLY)

compute_pipeline = device.create_compute_pipeline(
    layout=pipeline_layout,
    compute={"module": shader_module, "entry_point": "main"},
)

bind_group = device.create_bind_group(
    layout=compute_pipeline.get_bind_group_layout(0),
    entries=[
        {"binding": 0, "resource": {"buffer": rom_buffer, "offset": 0, "size": rom_buffer.size}},
        {"binding": 1, "resource": {"buffer": cpus_buffer, "offset": 0, "size": cpus_buffer.size}},
        {"binding": 2, "resource": {"buffer": output_buffer, "offset": 0, "size": output_buffer.size}},
        {"binding": 3, "resource": {"buffer": uniform_buffer, "offset": 0, "size": 8}},
    ],
)

# Run 3 dispatches (one for each token)
command_encoder = device.create_command_encoder()
for _ in range(3):
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

print("Test image: 3x1 with LDI r0 5")
print("Expected execution:")
print("  Dispatch 1: Read (236,80,80)=LDI, should execute, write 999")
print("  Dispatch 2: Read (50,50,50) as operand (no trace because output_ptr=3)")
print("  Dispatch 3: Read (0,0,6) as operand")
print()
print("Actual output trace (RGB,999 flag):")
for i in range(3):
    r, g, b, flag = values[i*4], values[i*4+1], values[i*4+2], values[i*4+3]
    print(f"  Dispatch {i+1}: RGB=({r},{g},{b}), LDI_executed={flag == 999}")