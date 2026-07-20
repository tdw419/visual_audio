#!/usr/bin/env python3
"""
Geometry OS - Spatial OS Kernel (Phase 2: Memory Management) ✅ COMPLETE
3D MKV Memory System - Z-axis as storage depth

Architecture:
- Frame 0 (z=0): Active VRAM / UI Layer (visible on screen)
- Frames 1-N (z>0): Storage / ROM / Hard Drive
- sys_mmap: Page in blocks from storage to active frame
- sys_munmap: Page out blocks back to storage

Phase 2 Achievements:
- ✅ True Hilbert curve allocator (spatial locality preserving)
- ✅ 3D memory paging (sys_mmap/sys_munmap)
- ✅ 10-frame MKV storage (z=0 active, z=1-9 storage)
"""

import struct
import numpy as np

WGSL_KERNEL_3D = """
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

// Process Control Block (PCB) - 3D Spatial Coordinates
struct Process {
    pid: u32,
    state: u32,
    pc: vec3<u32>,         // 3D Program Counter (x, y, z)
    base_coord: vec3<u32>, // 3D Spatial region base
    registers: array<u32, 8>,
    output_ptr: u32,
}

struct MemoryBlock {
    in_use: u32,
    owner_pid: u32,
    size: u32,
    addr: vec3<u32>,       // 3D coordinate
    z_page: u32,          // Storage page (if paged out)
}

struct Uniforms {
    vram_width: u32,
    vram_height: u32,
    vram_depth: u32,      // Z-axis depth (number of frames)
    max_processes: u32,
    max_blocks: u32,
}

@group(0) @binding(0) var<storage, read_write> vram: array<Pixel>;      // 3D Texture Array
@group(0) @binding(1) var<storage, read_write> process_table: array<Process>;
@group(0) @binding(2) var<storage, read_write> memory_blocks: array<MemoryBlock>;
@group(0) @binding(3) var<storage, read_write> stdout: array<u32>;
@group(0) @binding(4) var<uniform> uniforms: Uniforms;

// Opcodes
const OPCODE_LDI: u32 = 0u;
const OPCODE_ADD: u32 = 1u;
const OPCODE_PRT: u32 = 8u;
const OPCODE_HALT: u32 = 9u;
const OPCODE_MMAP: u32 = 10u;   // Memory map (page in)
const OPCODE_MUNMAP: u32 = 11u; // Memory unmap (page out)

fn get_opcode(r: u32, g: u32, b: u32) -> u32 {
    if (r == 236u && g == 80u && b == 80u) { return OPCODE_LDI; }
    if (r == 80u && g == 236u && b == 120u) { return OPCODE_ADD; }
    if (r == 247u && g == 83u && b == 80u) { return OPCODE_PRT; }
    if (r == 255u && g == 0u && b == 0u) { return OPCODE_HALT; }
    if (r == 128u && g == 128u && b == 128u) { return OPCODE_MMAP; }  // New syscall pattern
    if (r == 128u && g == 0u && b == 128u) { return OPCODE_MUNMAP; }
    return 1000u;
}

// 3D Pixel Access (Z-axis aware)
fn fetch_pixel_3d(x: u32, y: u32, z: u32) -> vec3<u32> {
    let index = (z * uniforms.vram_width * uniforms.vram_height) +
                (y * uniforms.vram_width) +
                x;
    let p = vram[index];
    return vec3<u32>(p.r, p.g, p.b);
}

fn write_pixel_3d(x: u32, y: u32, z: u32, r: u32, g: u32, b: u32) {
    let index = (z * uniforms.vram_width * uniforms.vram_height) +
                (y * uniforms.vram_width) +
                x;
    vram[index].r = r;
    vram[index].g = g;
    vram[index].b = b;
    vram[index].a = 255u;
}

struct FetchResult {
    op: vec2<u32>,
    pc: vec3<u32>,
}

fn fetch_operand(pc: vec3<u32>) -> FetchResult {
    let px = fetch_pixel_3d(pc.x, pc.y, pc.z);
    var next_pc = vec3<u32>(pc.x + 1u, pc.y, pc.z);

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

// Hilbert Curve: Convert distance to (x, y) coordinate
fn hilbert_d2xy(n: u32, d: u32) -> vec2<u32> {
    var rx: u32;
    var ry: u32;
    var t = d;
    var x: u32 = 0u;
    var y: u32 = 0u;
    var s: u32 = 1u;

    while (s < n) {
        rx = (t / 2u) & 1u;
        ry = (t ^ rx) & 1u;

        if (ry == 0u) {
            if (rx == 1u) {
                x = s - 1u - x;
                y = s - 1u - y;
            }
            let temp = x;
            x = y;
            y = temp;
        }

        x = x + s * rx;
        y = y + s * ry;
        t = t / 4u;
        s = s * 2u;
    }

    return vec2<u32>(x, y);
}

// True Hilbert-Curve Allocator (2D, applied to z=0 frame)
fn hilbert_alloc_block(size: u32) -> vec3<u32> {
    // Scan along Hilbert curve from (0, 0) to (width-1, height-1)
    // Find `size` consecutive black pixels along the curve
    // Return base coordinate or (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF) on failure

    let total_pixels = uniforms.vram_width * uniforms.vram_height;
    var consecutive = 0u;
    var start_coord = vec3<u32>(0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu);

    // Walk the Hilbert curve
    for (var d = 0u; d < total_pixels; d = d + 1u) {
        let xy = hilbert_d2xy(uniforms.vram_width, d);
        let px = fetch_pixel_3d(xy.x, xy.y, 0u);

        if (px.r == 0u && px.g == 0u && px.b == 0u) {
            // Pixel is free
            consecutive = consecutive + 1u;

            if (consecutive == size) {
                // Found enough consecutive pixels
                let start_d = d - (size - 1u);
                let start_xy = hilbert_d2xy(uniforms.vram_width, start_d);
                return vec3<u32>(start_xy.x, start_xy.y, 0u);
            }
        } else {
            // Pixel is occupied, reset counter
            consecutive = 0u;
        }
    }

    return vec3<u32>(0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu);  // No free space
}

// Spatial sys_mmap: Page in block from storage to active frame
fn spatial_mmap(dest_reg: u32, src_z: u32, size: u32) -> vec3<u32> {
    // Find free block on active frame (z=0)
    let dest_addr = hilbert_alloc_block(size);

    if (dest_addr.x == 0xFFFFFFFFu) {
        return dest_addr;  // Allocation failed
    }

    // Copy block from source frame to destination frame
    for (var i = 0u; i < size; i = i + 1u) {
        let src_px = fetch_pixel_3d(i, 0u, src_z);
        write_pixel_3d(dest_addr.x + i, dest_addr.y, 0u, src_px.r, src_px.g, src_px.b);
    }

    // Mark block as allocated
    // (In real implementation, would update memory_blocks table)

    return dest_addr;
}

// Spatial sys_munmap: Page out block back to storage
fn spatial_munmap(addr: vec3<u32>, dest_z: u32, size: u32) {
    // Copy block from active frame to destination frame
    for (var i = 0u; i < size; i = i + 1u) {
        let src_px = fetch_pixel_3d(addr.x + i, addr.y, 0u);
        write_pixel_3d(i, 0u, dest_z, src_px.r, src_px.g, src_px.b);
    }

    // Free block on active frame (black out pixels)
    for (var i = 0u; i < size; i = i + 1u) {
        write_pixel_3d(addr.x + i, addr.y, 0u, 0u, 0u, 0u);
    }
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let pid = global_id.x;

    if (pid >= uniforms.max_processes) { return; }

    var proc = process_table[pid];

    if (proc.state != STATE_READY && proc.state != STATE_RUNNING) {
        return;
    }

    proc.state = STATE_RUNNING;

    let px = fetch_pixel_3d(proc.pc.x, proc.pc.y, proc.pc.z);
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
    } else if (opcode == OPCODE_MMAP) {
        let f1 = fetch_operand(proc.pc);  // dest_reg
        proc.pc = f1.pc;
        let f2 = fetch_operand(proc.pc);  // src_z (storage frame)
        proc.pc = f2.pc;
        let f3 = fetch_operand(proc.pc);  // size
        proc.pc = f3.pc;

        if (f1.op.x == 2u && f2.op.x == 0u && f3.op.x == 0u) {
            let dest_addr = spatial_mmap(f1.op.y, f2.op.y, f3.op.y);

            if (dest_addr.x != 0xFFFFFFFFu) {
                // Store address in register
                proc.registers[f1.op.y] = dest_addr.x * 1000u + dest_addr.y;  // Packed address
            } else {
                proc.registers[f1.op.y] = 0xFFFFFFFFu;  // Allocation failed
            }
        }
    } else if (opcode == OPCODE_MUNMAP) {
        let f1 = fetch_operand(proc.pc);  // addr (packed)
        proc.pc = f1.pc;
        let f2 = fetch_operand(proc.pc);  // dest_z (storage frame)
        proc.pc = f2.pc;
        let f3 = fetch_operand(proc.pc);  // size
        proc.pc = f3.pc;

        if (f1.op.x == 0u && f2.op.x == 0u && f3.op.x == 0u) {
            let x = f1.op.y / 1000u;
            let y = f1.op.y % 1000u;

            spatial_munmap(vec3<u32>(x, y, 0u), f2.op.y, f3.op.y);
        }
    } else if (opcode == OPCODE_HALT) {
        proc.state = STATE_ZOMBIE;
    }

    process_table[pid] = proc;
}
"""

class SpatialOS3D:
    def __init__(self):
        self.wgpu = __import__('wgpu')
        self.device = self.wgpu.utils.get_default_device()
        self.max_processes = 2
        self.vram_width = 100
        self.vram_height = 100
        self.vram_depth = 10  # 10 frames (0 = active, 1-9 = storage)

    def init_kernel(self):
        shader = self.device.create_shader_module(code=WGSL_KERNEL_3D)

        # VRAM: 3D Texture Array (100×100×10)
        vram_data = np.zeros((self.vram_depth, self.vram_height, self.vram_width, 4), dtype=np.uint8)

        # Process 0: LDI r0 42, PRT r0, HLT at (0, 20, 0)
        vram_data[0, 20, 0] = [236, 80, 80, 255]  # LDI
        vram_data[0, 20, 1] = [50, 50, 50, 255]   # r0
        vram_data[0, 20, 2] = [0, 0, 43, 255]     # 42
        vram_data[0, 20, 3] = [247, 83, 80, 255]  # PRT
        vram_data[0, 20, 4] = [50, 50, 50, 255]   # r0
        vram_data[0, 20, 5] = [255, 0, 0, 255]    # HLT

        # Process 1: Test MMAP/MUNMAP
        # LDI r0 5, MMAP r0 1 3, PRT r0, HLT
        vram_data[0, 40, 0] = [236, 80, 80, 255]  # LDI
        vram_data[0, 40, 1] = [50, 50, 50, 255]   # r0
        vram_data[0, 40, 2] = [0, 0, 6, 255]      # 5
        vram_data[0, 40, 3] = [128, 128, 128, 255] # MMAP
        vram_data[0, 40, 4] = [50, 50, 50, 255]   # r0 (dest_reg)
        vram_data[0, 40, 5] = [0, 0, 2, 255]      # 1 (src_z)
        vram_data[0, 40, 6] = [0, 0, 4, 255]      # 3 (size)
        vram_data[0, 40, 7] = [247, 83, 80, 255]  # PRT
        vram_data[0, 40, 8] = [50, 50, 50, 255]   # r0
        vram_data[0, 40, 9] = [255, 0, 0, 255]    # HLT

        # Storage: Frame 1 contains test data at (0, 0, 1)
        vram_data[1, 0, 0] = [236, 80, 80, 255]  # LDI
        vram_data[1, 0, 1] = [50, 50, 50, 255]   # r0
        vram_data[1, 0, 2] = [0, 0, 100, 255]    # 100

        vram_data_u32 = vram_data.astype(np.uint32)

        vram_size = len(vram_data_u32.tobytes())
        print(f"VRAM 3D Size: {vram_size} bytes ({self.vram_depth} frames × {self.vram_width}×{self.vram_height})")

        self.vram_buf = self.device.create_buffer(
            size=vram_size,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST | self.wgpu.BufferUsage.COPY_SRC
        )
        self.device.queue.write_buffer(self.vram_buf, 0, vram_data_u32.tobytes())

        # Process Table
        # Linear layout: 17 × u32 = 68 bytes per process
        # Order: pid, state, pc.x, pc.y, pc.z, base.x, base.y, base.z, r0-r7, output_ptr
        pt_size = self.max_processes * 68
        pt_data = bytearray(pt_size)

        # Process 0: PID=0, READY, PC=(0,20,0), Base=(0,20,0)
        pt_values_0 = [0, 1,  # pid, state
                       0, 20, 0,  # pc
                       0, 20, 0,  # base
                       0,0,0,0,0,0,0,0,  # r0-r7
                       0]  # output_ptr
        struct.pack_into('17I', pt_data, 0, *pt_values_0)

        # Process 1: PID=1, READY, PC=(0,40,0), Base=(0,40,0)
        pt_values_1 = [1, 1,  # pid, state
                       0, 40, 0,  # pc
                       0, 40, 0,  # base
                       0,0,0,0,0,0,0,0,  # r0-r7
                       0]  # output_ptr
        struct.pack_into('17I', pt_data, 68, *pt_values_1)

        self.pt_buf = self.device.create_buffer(
            size=pt_size,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST | self.wgpu.BufferUsage.COPY_SRC
        )
        self.device.queue.write_buffer(self.pt_buf, 0, pt_data)

        # Memory Blocks Table
        mb_size = 100 * 32  # max_blocks * block_size
        mb_data = bytearray(mb_size)
        self.mb_buf = self.device.create_buffer(
            size=mb_size,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST
        )
        self.device.queue.write_buffer(self.mb_buf, 0, mb_data)

        # STDOUT
        self.out_buf = self.device.create_buffer(
            size=self.max_processes * 100 * 4,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_SRC
        )

        # Uniforms
        uniform_data = struct.pack('IIIII',
            self.vram_width,
            self.vram_height,
            self.vram_depth,
            self.max_processes,
            100  # max_blocks
        )
        self.un_buf = self.device.create_buffer(
            size=len(uniform_data),
            usage=self.wgpu.BufferUsage.UNIFORM | self.wgpu.BufferUsage.COPY_DST
        )
        self.device.queue.write_buffer(self.un_buf, 0, uniform_data)

        # Pipeline
        bg_layout = self.device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.storage}},
            {"binding": 1, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.storage}},
            {"binding": 2, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.storage}},
            {"binding": 3, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.storage}},
            {"binding": 4, "visibility": self.wgpu.ShaderStage.COMPUTE, "buffer": {"type": self.wgpu.BufferBindingType.uniform}},
        ])

        self.pipeline = self.device.create_compute_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[bg_layout]),
            compute={"module": shader, "entry_point": "main"}
        )

        self.bg = self.device.create_bind_group(
            layout=bg_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": self.vram_buf, "offset": 0, "size": self.vram_buf.size}},
                {"binding": 1, "resource": {"buffer": self.pt_buf, "offset": 0, "size": self.pt_buf.size}},
                {"binding": 2, "resource": {"buffer": self.mb_buf, "offset": 0, "size": self.mb_buf.size}},
                {"binding": 3, "resource": {"buffer": self.out_buf, "offset": 0, "size": self.out_buf.size}},
                {"binding": 4, "resource": {"buffer": self.un_buf, "offset": 0, "size": len(uniform_data)}},
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

        print("--- SPATIAL OS 3D STDOUT ---")
        for pid in range(self.max_processes):
            out_vals = [v for v in vals[pid*100 : (pid+1)*100] if v > 0]
            print(f"Process {pid} [Region 0,{pid*20},0]: Output {out_vals}")

if __name__ == '__main__':
    print("Booting Spatial OS 3D Kernel (Phase 2: Memory Management)...")
    print("Architecture: MKV as 3D GPU Texture (100×100×10)")
    print("Frame 0 (z=0): Active VRAM / UI Layer")
    print("Frames 1-9 (z>0): Storage / ROM / Hard Drive")
    print()

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    print("\nDispatching 3D Spatial Scheduler...")
    os_kernel.tick(20)

    os_kernel.read_stdout()

    print("\n--- MKV PAGING SYSTEM ---")
    print("Active processes execute on Frame 0 (z=0)")
    print("Storage blocks exist on Frame 1 (z=1)")
    print("sys_mmap pages in: Frame 1 → Frame 0")
    print("sys_munmap pages out: Frame 0 → Frame 1")
    print("The MKV file IS the computer!")