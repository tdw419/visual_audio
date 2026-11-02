#!/usr/bin/env python3
"""
Geometry OS - Spatial OS Kernel (Phase 1: Process Management)

Implements the first stage of the infinite 2D kernel map.
The GPU manages a spatial process table and executes processes
within their assigned 20x20 pixel spatial bounds.
"""

import struct
import asyncio
import numpy as np

WGSL_KERNEL = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

const STATE_FREE: u32 = 0u;
const STATE_READY: u32 = 1u;
const STATE_RUNNING: u32 = 2u;
const STATE_ZOMBIE: u32 = 3u;

// Process Control Block (PCB) - Spatial Representation
struct Process {
    pid: u32,
    state: u32,
    pc: vec2<u32>,        
    base_coord: vec2<u32>, // Top-left of the 20x20 spatial allocation
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

// SPATIAL SCHEDULER & EXECUTION CORE
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let pid = global_id.x;
    
    if (pid >= uniforms.max_processes) { return; }
    
    var proc = process_table[pid];
    
    // Context Switch / Scheduler Logic
    if (proc.state != STATE_READY && proc.state != STATE_RUNNING) {
        return; 
    }
    
    proc.state = STATE_RUNNING;
    
    // Execute 1 spatial instruction per clock cycle
    let px = fetch_pixel(proc.pc.x, proc.pc.y);
    let opcode = get_opcode(px.r, px.g, px.b);
    
    // Advance PC after fetching opcode (now points to first operand)
    proc.pc.x = proc.pc.x + 1u;
    
    if (opcode == OPCODE_LDI) {
        // Fetch dest register
        let f1 = fetch_operand(proc.pc);
        proc.pc = f1.pc;  // Advance past dest register
        
        // Fetch immediate value
        let f2 = fetch_operand(proc.pc);
        proc.pc = f2.pc;  // Advance past immediate
        
        if (f1.op.x == 2u) { 
            // f1.op.y is register number, f2.op.y is immediate value
            proc.registers[f1.op.y] = f2.op.y; 
        }
    } else if (opcode == OPCODE_ADD) {
        // Fetch dest register
        let f1 = fetch_operand(proc.pc);
        proc.pc = f1.pc;
        
        // Fetch source register
        let f2 = fetch_operand(proc.pc);
        proc.pc = f2.pc;
        
        if (f1.op.x == 2u && f2.op.x == 2u) {
            proc.registers[f1.op.y] = proc.registers[f1.op.y] + proc.registers[f2.op.y];
        }
    } else if (opcode == OPCODE_PRT) {
        // Fetch source register
        let f1 = fetch_operand(proc.pc);
        proc.pc = f1.pc;
        
        if (f1.op.x == 2u) {
            // Write to process stdout region
            let out_idx = pid * 100u + proc.output_ptr;
            stdout[out_idx] = proc.registers[f1.op.y];
            proc.output_ptr = proc.output_ptr + 1u;
        }
    } else if (opcode == OPCODE_HALT) {
        proc.state = STATE_ZOMBIE; // Spatial Syscall: sys_kill_process
    }
    
    // Write back context
    process_table[pid] = proc;
}
"""

class SpatialOS:
    def __init__(self):
        self.wgpu = __import__('wgpu')
        self.device = self.wgpu.utils.get_default_device()
        self.max_processes = 10
        self.vram_width = 100
        self.vram_height = 100

    def init_kernel(self):
        self.shader = self.device.create_shader_module(code=WGSL_KERNEL)
        
        # VRAM Buffer (Infinite Map)
        vram_data = np.zeros((self.vram_height, self.vram_width, 4), dtype=np.uint8)
        
        # We manually inject two process codes into VRAM via Patch-and-Copy format
        # Process 0: LDI r0 42, PRT r0, HLT (placed at 0, 20)
        vram_data[20, 0] = [236, 80, 80, 255] # LDI
        vram_data[20, 1] = [50, 50, 50, 255]  # r0
        vram_data[20, 2] = [0, 0, 43, 255]    # 42
        vram_data[20, 3] = [247, 83, 80, 255] # PRT
        vram_data[20, 4] = [50, 50, 50, 255]  # r0
        vram_data[20, 5] = [255, 0, 0, 255]   # HLT
        
        # Process 1: LDI r0 100, ADD r0 r0, PRT r0, HLT (placed at 0, 40)
        vram_data[40, 0] = [236, 80, 80, 255] # LDI
        vram_data[40, 1] = [50, 50, 50, 255]  # r0
        vram_data[40, 2] = [0, 0, 101, 255]   # 100
        vram_data[40, 3] = [80, 236, 120, 255]# ADD
        vram_data[40, 4] = [50, 50, 50, 255]  # r0
        vram_data[40, 5] = [50, 50, 50, 255]  # r0
        vram_data[40, 6] = [247, 83, 80, 255] # PRT
        vram_data[40, 7] = [50, 50, 50, 255]  # r0
        vram_data[40, 8] = [255, 0, 0, 255]   # HLT
        
        # Convert to u32 for GPU upload (shader Pixel struct uses u32 channels)
        vram_data_u32 = vram_data.astype(np.uint32)
        
        self.vram_buf = self.device.create_buffer_with_data(
            data=vram_data_u32.tobytes(),
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST
        )
        
        # Process Table Buffer (Struct Size = 64 bytes)
        pt_size = self.max_processes * 64
        pt_data = bytearray(pt_size)
        
        # sys_spawn_process(pid=0, x=0, y=20)
        struct.pack_into('IIIIIIIIIIIIIIII', pt_data, 0 * 64, 
            0, 1, 0, 20, 0, 20, 0,0,0,0,0,0,0,0, 0, 0) # pid, state=1(READY), pc.x, pc.y, base.x, base.y, r0-r7, out_ptr, padding
            
        # sys_spawn_process(pid=1, x=0, y=40)
        struct.pack_into('IIIIIIIIIIIIIIII', pt_data, 1 * 64, 
            1, 1, 0, 40, 0, 40, 0,0,0,0,0,0,0,0, 0, 0)
            
        self.pt_buf = self.device.create_buffer_with_data(
            data=pt_data,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_SRC
        )
        
        # STDOUT Buffer
        self.out_buf = self.device.create_buffer(
            size=self.max_processes * 100 * 4,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_SRC
        )
        
        # Uniforms
        uniform_data = struct.pack('III', self.vram_width, self.vram_height, self.max_processes)
        self.un_buf = self.device.create_buffer_with_data(
            data=uniform_data, usage=self.wgpu.BufferUsage.UNIFORM
        )
        
        bg_layout = self.device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.read_only_storage}},
            {"binding": 1, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.storage}},
            {"binding": 2, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.storage}},
            {"binding": 3, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.uniform}},
        ])
        
        self.pipeline = self.device.create_compute_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[bg_layout]),
            compute={"module": self.shader, "entry_point": "main"}
        )
        
        self.bg = self.device.create_bind_group(
            layout=bg_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": self.vram_buf, "offset": 0, "size": self.vram_buf.size}},
                {"binding": 1, "resource": {"buffer": self.pt_buf, "offset": 0, "size": self.pt_buf.size}},
                {"binding": 2, "resource": {"buffer": self.out_buf, "offset": 0, "size": self.out_buf.size}},
                {"binding": 3, "resource": {"buffer": self.un_buf, "offset": 0, "size": self.un_buf.size}},
            ]
        )

    def tick(self, clock_cycles=10):
        command_encoder = self.device.create_command_encoder()
        for _ in range(clock_cycles):
            compute_pass = command_encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.pipeline)
            compute_pass.set_bind_group(0, self.bg)
            compute_pass.dispatch_workgroups(self.max_processes)
            compute_pass.end()
        self.device.queue.submit([command_encoder.finish()])
        
    def read_stdout(self):
        data = self.device.queue.read_buffer(self.out_buf)
        vals = struct.unpack(f'{self.out_buf.size // 4}I', data)
        
        print("--- SPATIAL OS STDOUT ---")
        for pid in range(2):
            out_vals = [v for v in vals[pid*100 : (pid+1)*100] if v > 0]
            print(f"Process {pid} [Region 0,{pid*20}]: Output {out_vals}")
            
if __name__ == '__main__':
    print("Booting Spatial OS Kernel (Phase 1)...")
    os_kernel = SpatialOS()
    os_kernel.init_kernel()
    
    print("Dispatching Spatial Scheduler...")
    os_kernel.tick(10) # Run 10 clock cycles
    
    os_kernel.read_stdout()
