"""
Debug Spatial OS Kernel - Diagnose fetch-execute cycle
"""
import struct
import numpy as np
import wgpu

WGSL_KERNEL = """
struct Pixel {
    r: u32, g: u32, b: u32, a: u32,
}

const STATE_FREE: u32 = 0u;
const STATE_READY: u32 = 1u;
const STATE_RUNNING: u32 = 2u;
const STATE_ZOMBIE: u32 = 3u;

struct Process {
    pid: u32,
    state: u32,
    pc: vec2<u32>,
    base_coord: vec2<u32>,
    registers: array<u32, 8>,
    output_ptr: u32,
}

struct Uniforms {
    vram_width: u32,
    vram_height: u32,
    max_processes: u32,
}

@group(0) @binding(0) var<storage, read> vram: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> process_table: array<Process>;
@group(0) @binding(2) var<storage, read_write> stdout: array<u32>;
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

const OPCODE_LDI: u32 = 0u;
const OPCODE_ADD: u32 = 1u;
const OPCODE_PRT: u32 = 8u;
const OPCODE_HALT: u32 = 9u;

fn get_opcode(r: u32, g: u32, b: u32) -> u32 {
    if (r == 236u && g == 80u && b == 80u) { return OPCODE_LDI; }
    if (r == 80u && g == 236u && b == 120u) { return OPCODE_ADD; }
    if (r == 247u && g == 83u && b == 80u) { return OPCODE_PRT; }
    if (r == 255u && g == 0u && b == 0u) { return OPCODE_HALT; }
    return 1000u;
}

fn fetch_pixel(x: u32, y: u32) -> vec3<u32> {
    let index = y * uniforms.vram_width + x;
    let p = vram[index];
    return vec3<u32>(p.r, p.g, p.b);
}

struct FetchResult {
    op: vec2<u32>,
    pc: vec2<u32>,
}

fn fetch_operand(pc: vec2<u32>) -> FetchResult {
    let px = fetch_pixel(pc.x, pc.y);
    var next_pc = vec2<u32>(pc.x + 1u, pc.y);
    
    // Immediate
    if (px.r == 0u && px.g == 0u && px.b > 0u) {
        return FetchResult(vec2<u32>(0u, px.b - 1u), next_pc);
    }
    // Register
    if (px.r > 40u && px.r == px.g && px.g == px.b) {
        let reg_num = (px.r - 50u) / 25u;
        return FetchResult(vec2<u32>(2u, reg_num), next_pc);
    }
    return FetchResult(vec2<u32>(3u, 0u), next_pc);
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let pid = global_id.x;
    
    if (pid >= uniforms.max_processes) { return; }
    
    var proc = process_table[pid];
    
    // Only execute if READY or RUNNING
    if (proc.state != STATE_READY && proc.state != STATE_RUNNING) {
        return; 
    }
    
    proc.state = STATE_RUNNING;
    
    let px = fetch_pixel(proc.pc.x, proc.pc.y);
    let opcode = get_opcode(px.r, px.g, px.b);
    
    proc.pc.x = proc.pc.x + 1u;
    
    if (opcode == OPCODE_LDI) {
        let f1 = fetch_operand(proc.pc);
        proc.pc = f1.pc;
        let f2 = fetch_operand(proc.pc);
        proc.pc = f2.pc;
        
        if (f1.op.x == 2u) {
            proc.registers[f1.op.y] = f2.op.y;
        }
    } else if (opcode == OPCODE_ADD) {
        let f1 = fetch_operand(proc.pc);
        proc.pc = f1.pc;
        let f2 = fetch_operand(proc.pc);
        proc.pc = f2.pc;
        
        if (f1.op.x == 2u && f2.op.x == 2u) {
            proc.registers[f1.op.y] = proc.registers[f1.op.y] + proc.registers[f2.op.y];
        }
    } else if (opcode == OPCODE_PRT) {
        let f1 = fetch_operand(proc.pc);
        proc.pc = f1.pc;
        
        if (f1.op.x == 2u) {
            let out_idx = pid * 100u + proc.output_ptr;
            stdout[out_idx] = proc.registers[f1.op.y];
            proc.output_ptr = proc.output_ptr + 1u;
        }
    } else if (opcode == OPCODE_HALT) {
        proc.state = STATE_ZOMBIE;
    }
    
    process_table[pid] = proc;
}
"""

def main():
    device = wgpu.utils.get_default_device()
    max_processes = 2
    vram_width = 100
    vram_height = 100

    shader = device.create_shader_module(code=WGSL_KERNEL)

    # VRAM - Load processes
    vram_data = np.zeros((vram_height, vram_width, 4), dtype=np.uint8)

    # Process 0: LDI r0 42, PRT r0, HLT at (0, 0)
    vram_data[0, 0] = [236, 80, 80, 255]  # LDI
    vram_data[0, 1] = [50, 50, 50, 255]   # r0
    vram_data[0, 2] = [0, 0, 43, 255]     # 42
    vram_data[0, 3] = [247, 83, 80, 255]  # PRT
    vram_data[0, 4] = [50, 50, 50, 255]   # r0
    vram_data[0, 5] = [255, 0, 0, 255]    # HLT

    # Process 1: LDI r0 100, ADD r0 r0, PRT r0, HLT at (0, 1)
    vram_data[1, 0] = [236, 80, 80, 255]  # LDI
    vram_data[1, 1] = [50, 50, 50, 255]   # r0
    vram_data[1, 2] = [0, 0, 101, 255]    # 100
    vram_data[1, 3] = [80, 236, 120, 255] # ADD
    vram_data[1, 4] = [50, 50, 50, 255]   # r0
    vram_data[1, 5] = [50, 50, 50, 255]   # r0
    vram_data[1, 6] = [247, 83, 80, 255]  # PRT
    vram_data[1, 7] = [50, 50, 50, 255]   # r0
    vram_data[1, 8] = [255, 0, 0, 255]    # HLT

    vram_buffer = device.create_buffer(
        size=len(vram_data.astype(np.uint32).tobytes()),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(vram_buffer, 0, vram_data.astype(np.uint32).tobytes())

    print(f"VRAM Process 0 (row 0):")
    for i in range(6):
        r, g, b, a = vram_data[0, i]
        print(f"  [{i}] ({r}, {g}, {b})")

    print(f"\nVRAM Process 1 (row 1):")
    for i in range(9):
        r, g, b, a = vram_data[1, i]
        print(f"  [{i}] ({r}, {g}, {b})")

    # Process Table
    pt_size = max_processes * 64
    pt_data = bytearray(pt_size)

    # Process 0: PID=0, READY, PC=(0,0), Base=(0,0)
    struct.pack_into('IIIIIIIIIIIIIIII', pt_data, 0,
        0, 1,  # PID=0, READY
        0, 0,  # PC=(0,0)
        0, 0,  # Base=(0,0)
        0,0,0,0,0,0,0,0,  # R0-R7
        0,  # output_ptr
        0   # padding
    )

    # Process 1: PID=1, READY, PC=(0,1), Base=(0,1)
    struct.pack_into('IIIIIIIIIIIIIIII', pt_data, 64,
        1, 1,  # PID=1, READY
        0, 1,  # PC=(0,1)
        0, 1,  # Base=(0,1)
        0,0,0,0,0,0,0,0,  # R0-R7
        0,  # output_ptr
        0   # padding
    )

    print(f"\nProcess Table Initialized:")
    print(f"  Process 0: PID=0, READY, PC=(0,0)")
    print(f"  Process 1: PID=1, READY, PC=(0,1)")

    pt_buffer = device.create_buffer(
        size=pt_size,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    device.queue.write_buffer(pt_buffer, 0, pt_data)

    # STDOUT
    out_buffer = device.create_buffer(
        size=max_processes * 100 * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )

    # Uniforms
    uniform_data = struct.pack('III', vram_width, vram_height, max_processes)
    uniform_buffer = device.create_buffer(
        size=len(uniform_data),
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(uniform_buffer, 0, uniform_data)

    # Pipeline
    bg_layout = device.create_bind_group_layout(entries=[
        {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
        {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
        {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
    ])

    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bg_layout]),
        compute={"module": shader, "entry_point": "main"},
    )

    bind_group = device.create_bind_group(
        layout=bg_layout,
        entries=[
            {"binding": 0, "resource": {"buffer": vram_buffer, "offset": 0, "size": vram_buffer.size}},
            {"binding": 1, "resource": {"buffer": pt_buffer, "offset": 0, "size": pt_buffer.size}},
            {"binding": 2, "resource": {"buffer": out_buffer, "offset": 0, "size": out_buffer.size}},
            {"binding": 3, "resource": {"buffer": uniform_buffer, "offset": 0, "size": len(uniform_data)}},
        ],
    )

    # Execute
    print(f"\nExecuting 10 clock cycles...")
    command_encoder = device.create_command_encoder()
    for i in range(10):
        compute_pass = command_encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(0, bind_group)
        compute_pass.dispatch_workgroups(max_processes)
        compute_pass.end()

        # Read process table after each cycle for debugging
        staging = device.create_buffer(
            size=pt_buffer.size,
            usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
        )

        cmd = device.create_command_encoder()
        cmd.copy_buffer_to_buffer(pt_buffer, 0, staging, 0, pt_buffer.size)
        device.queue.submit([cmd.finish()])

        staging.map_sync(wgpu.MapMode.READ)
        pt_raw = staging.read_mapped()
        staging.unmap()

        print(f"\nCycle {i+1}:")
        for pid in range(max_processes):
            offset = pid * 64
            pid_val, state, pc_x, pc_y, base_x, base_y = struct.unpack('IIIIII', pt_raw[offset:offset+24])
            print(f"  PID {pid}: state={state}, PC=({pc_x},{pc_y}), Base=({base_x},{base_y})")

    device.queue.submit([command_encoder.finish()])

    # Read stdout
    staging = device.create_buffer(
        size=out_buffer.size,
        usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
    )

    cmd = device.create_command_encoder()
    cmd.copy_buffer_to_buffer(out_buffer, 0, staging, 0, out_buffer.size)
    device.queue.submit([cmd.finish()])

    staging.map_sync(wgpu.MapMode.READ)
    out_raw = staging.read_mapped()
    staging.unmap()

    out_vals = struct.unpack(f'{out_buffer.size // 4}I', out_raw)

    print(f"\n--- STDOUT ---")
    for pid in range(max_processes):
        out_region = [v for v in out_vals[pid*100:(pid+1)*100] if v > 0]
        print(f"Process {pid}: {out_region}")

if __name__ == '__main__':
    main()