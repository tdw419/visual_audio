"""
Trace full execution with PC persistence test
"""
import wgpu
import struct
import numpy as np

WGSL_FULL_TRACE = """
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
    cpu.pc = advance_pc(cpu.pc);

    // Write trace: opcode or (0,0,0) for no match
    let trace_offset = global_id.x * 100u + cpu.output_ptr;
    if (trace_offset < 100u) {
        output[trace_offset] = pixel.r;
        output[trace_offset + 1u] = pixel.g;
        output[trace_offset + 2u] = pixel.b;
    }
    cpu.output_ptr = cpu.output_ptr + 3u;

    // Opcodes
    if (pixel.r == 236u && pixel.g == 80u && pixel.b == 80u) {
        // LDI
        let reg_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let reg_num = (reg_pixel.r - 50u) / 25u;

        let val_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let val = val_pixel.b - 1u;

        cpu.registers[reg_num] = val;

    } else if (pixel.r == 80u && pixel.g == 236u && pixel.b == 120u) {
        // ADD
        let reg1_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let reg1 = (reg1_pixel.r - 50u) / 25u;

        let reg2_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let reg2 = (reg2_pixel.r - 50u) / 25u;

        cpu.registers[reg1] = cpu.registers[reg1] + cpu.registers[reg2];

    } else if (pixel.r == 247u && pixel.g == 83u && pixel.b == 80u) {
        // PRT
        let reg_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc = advance_pc(cpu.pc);
        let reg_num = (reg_pixel.r - 50u) / 25u;

        let prt_offset = global_id.x * 100u + 98u;
        output[prt_offset] = cpu.registers[reg_num];
        cpu.running = 0u;

    } else if (pixel.r == 255u && pixel.g == 0u && pixel.b == 0u) {
        // HALT
        cpu.running = 0u;
    }

    cpus[global_id.x] = cpu;
}
"""

device = wgpu.utils.get_default_device()

# Load dense image
from PIL import Image
img = Image.open("glass_stratum_demo_dense.png")
rgba = np.array(img)
if rgba.shape[2] == 3:
    rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, dtype=rgba.dtype)])
flat_data = rgba.reshape(-1, 4)

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
    size=400 * 4,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)

uniform_data = struct.pack('II', 10, 100)
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
shader_module = device.create_shader_module(code=WGSL_FULL_TRACE)

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

# Run 20 dispatches
command_encoder = device.create_command_encoder()
for _ in range(20):
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

print("Opcode trace over 20 dispatches:")
opcode_names = {
    (236, 80, 80): "LDI",
    (80, 236, 120): "ADD",
    (151, 244, 80): "SUB",
    (247, 83, 80): "PRT",
    (255, 0, 0): "HLT",
}

for i in range(20):
    idx = i * 3
    r, g, b = values[idx], values[idx+1], values[idx+2]
    name = opcode_names.get((r,g,b), f"({r},{g},{b})")
    print(f"  Dispatch {i+1:2d}: {name}")

# Check PRT output at offset 98
print(f"\nPRT output: {values[98]}")