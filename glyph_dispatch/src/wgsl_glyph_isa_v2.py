"""
WGSL GPU-native port of glyph_isa_v2.py's Spatial ISA v1.0.

Unlike tools/wgsl_spatial_glyph_engine.py and tools/wgsl_spatial_glyph_working.py
(an older, incompatible ad-hoc instruction encoding), this shader faithfully
implements glyph_isa_v2's actual fixed-width format:

    Every instruction is a 1x4 horizontal pixel block:
        Pixel 0 (Opcode):    RGB identifying the opcode (see OpcodeMapV2)
        Pixel 1 (Registers): R=rs1, G=rs2, B=rd  (0xFF = UNUSED_REGISTER)
        Pixel 2 (Imm-Low):   lower 24 bits of immediate/coordinate
        Pixel 3 (Imm-High):  upper 24 bits (only low 8 bits used here -
                              WGSL registers are u32, unlike Python's
                              unbounded ints, so the immediate is carried
                              as a single u32 rather than the full 48-bit
                              range _pack_immediate supports. No opcode in
                              the current ISA needs more than 32 bits.)

    LD/ST/PUSH/POP/CALL/RET read and write the SAME image buffer that
    holds the program - this is self-modifying-code-capable memory, not
    a separate scratch region, exactly matching GlyphCPUv2._mem_read/write.

Opcode colors are pulled from OpcodeMapV2 at generation time (see
generate_wgsl_opcode_table() below) rather than hand-copied, so this file
never silently drifts from whatever tools/glyph_isa_v2.py currently
resolves - regenerate the constant block if wordbase.db content changes
the original 10 opcodes' colors.
"""

import numpy as np

from tools.glyph_isa_v2 import OpcodeMapV2, INSTR_WIDTH, UNUSED_REGISTER

_OPCODE_ORDER = [
    'HALT', 'LDI', 'ADD', 'SUB', 'CMP', 'JMP', 'JZ', 'PRT', 'LD', 'ST',
    'AND', 'OR', 'XOR', 'SHL', 'SHR', 'PUSH', 'POP', 'CALL', 'RET', 'SYSCALL'
]


def generate_wgsl_opcode_table(opcode_map: OpcodeMapV2):
    """Emit the WGSL const block + get_opcode_from_color() check lines for
    every opcode currently in OpcodeMapV2, so the shader always matches
    the live map rather than a hand-copied snapshot."""
    consts = []
    checks = []
    for i, op in enumerate(_OPCODE_ORDER):
        consts.append("const OPCODE_%s: u32 = %du;" % (op, i))
        r, g, b = opcode_map.opcode_to_rgb(op)
        checks.append(
            "    if (r == %du && g == %du && b == %du) { return OPCODE_%s; }" % (r, g, b, op)
        )
    return "\n".join(consts), "\n".join(checks)


_SHADER_TEMPLATE = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

struct SpatialCPU {
    pc: vec2<u32>,             // 2D program counter (x always a multiple of 4)
    registers: array<u32, 32>, // r0-r31; r31 doubles as the stack pointer
    running: u32,
    output_ptr: u32,
}

struct Uniforms {
    image_width: u32,
    image_height: u32,
    output_buffer_size: u32,
}

// image is BOTH the program ROM and read/write scratch memory (LD/ST/
// PUSH/POP/CALL/RET all operate on it) - matching GlyphCPUv2 exactly.
@group(0) @binding(0) var<storage, read_write> image: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> cpus: array<SpatialCPU>;
@group(0) @binding(2) var<storage, read_write> output: array<u32>;
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

__OPCODE_CONSTS__
const UNUSED_REGISTER: u32 = 255u;
const INSTR_WIDTH: u32 = 4u;

fn get_opcode_from_color(r: u32, g: u32, b: u32) -> u32 {
__OPCODE_CHECKS__
    return 1000u; // Unknown opcode
}

fn load_pixel(x: u32, y: u32) -> vec3<u32> {
    let index = y * uniforms.image_width + x;
    let p = image[index];
    return vec3<u32>(p.r, p.g, p.b);
}

fn store_pixel(x: u32, y: u32, val: vec3<u32>) {
    let index = y * uniforms.image_width + x;
    image[index].r = val.x;
    image[index].g = val.y;
    image[index].b = val.z;
}

// Linear-wrap scalar address -> pixel coordinate (scanline order),
// matching GlyphCPUv2._addr_to_xy.
fn addr_to_xy(addr: u32) -> vec2<u32> {
    let total = uniforms.image_width * uniforms.image_height;
    let wrapped = addr % total;
    return vec2<u32>(wrapped % uniforms.image_width, wrapped / uniforms.image_width);
}

fn mem_read(addr: u32) -> u32 {
    let xy = addr_to_xy(addr);
    let p = load_pixel(xy.x, xy.y);
    return (p.x << 16u) | (p.y << 8u) | p.z;
}

fn mem_write(addr: u32, value: u32) {
    let xy = addr_to_xy(addr);
    let v = value & 0xFFFFFFu;
    store_pixel(xy.x, xy.y, vec3<u32>((v >> 16u) & 0xFFu, (v >> 8u) & 0xFFu, v & 0xFFu));
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let cpu_id = global_id.x;
    if (cpu_id >= arrayLength(&cpus)) {
        return;
    }

    var cpu = cpus[cpu_id];
    if (cpu.running == 0u) {
        return;
    }

    let x = cpu.pc.x;
    let y = cpu.pc.y;

    if (y >= uniforms.image_height || x >= uniforms.image_width) {
        cpu.running = 0u;
        cpus[cpu_id] = cpu;
        return;
    }

    let opcode_px = load_pixel(x, y);
    let reg_px = load_pixel(x + 1u, y);
    let low_px = load_pixel(x + 2u, y);
    let high_px = load_pixel(x + 3u, y);

    let opcode = get_opcode_from_color(opcode_px.x, opcode_px.y, opcode_px.z);

    let rs1 = reg_px.x;
    let rs2 = reg_px.y;
    let rd = reg_px.z;

    // Immediate: low 24 bits from low_px, next 8 bits from high_px's top
    // byte - a u32-sized subset of Python's full 48-bit pack (see module
    // docstring). Sufficient for every opcode in this ISA.
    let low24 = (low_px.x << 16u) | (low_px.y << 8u) | low_px.z;
    let imm = (high_px.z << 24u) | low24;

    var next_pc = vec2<u32>(x + INSTR_WIDTH, y);

    if (opcode == OPCODE_LDI) {
        cpu.registers[rd] = imm;
    } else if (opcode == OPCODE_ADD) {
        cpu.registers[rd] = cpu.registers[rd] + cpu.registers[rs2];
    } else if (opcode == OPCODE_SUB) {
        cpu.registers[rd] = cpu.registers[rd] - cpu.registers[rs2];
    } else if (opcode == OPCODE_AND) {
        cpu.registers[rd] = cpu.registers[rd] & cpu.registers[rs2];
    } else if (opcode == OPCODE_OR) {
        cpu.registers[rd] = cpu.registers[rd] | cpu.registers[rs2];
    } else if (opcode == OPCODE_XOR) {
        cpu.registers[rd] = cpu.registers[rd] ^ cpu.registers[rs2];
    } else if (opcode == OPCODE_SHL) {
        cpu.registers[rd] = cpu.registers[rd] << cpu.registers[rs2];
    } else if (opcode == OPCODE_SHR) {
        cpu.registers[rd] = cpu.registers[rd] >> cpu.registers[rs2];
    } else if (opcode == OPCODE_CMP) {
        if (cpu.registers[rd] == cpu.registers[rs2]) {
            cpu.registers[0] = 1u;
        } else {
            cpu.registers[0] = 0u;
        }
    } else if (opcode == OPCODE_LD) {
        let addr = cpu.registers[rs2];
        cpu.registers[rd] = mem_read(addr);
    } else if (opcode == OPCODE_ST) {
        // ST rd rs2 -> store rs2 into the pixel at address rd (rd is the
        // ADDRESS register here, not a destination - matches GlyphCPUv2).
        let addr = cpu.registers[rd];
        mem_write(addr, cpu.registers[rs2]);
    } else if (opcode == OPCODE_PUSH) {
        cpu.registers[31] = cpu.registers[31] - 1u;
        mem_write(cpu.registers[31], cpu.registers[rd]);
    } else if (opcode == OPCODE_POP) {
        cpu.registers[rd] = mem_read(cpu.registers[31]);
        cpu.registers[31] = cpu.registers[31] + 1u;
    } else if (opcode == OPCODE_PRT) {
        let idx = cpu.output_ptr;
        if (idx < uniforms.output_buffer_size) {
            output[cpu_id * uniforms.output_buffer_size + idx] = cpu.registers[rd];
        }
        cpu.output_ptr = cpu.output_ptr + 1u;
    } else if (opcode == OPCODE_CALL) {
        // Push the (already pixel-unit) return address, then jump to the
        // instruction-index-encoded target (tx * INSTR_WIDTH), exactly
        // matching the asymmetry in GlyphCPUv2: the *saved* return PC is
        // stored in raw pixel units, but the jump *target* in imm is an
        // instruction index that must be scaled by INSTR_WIDTH.
        cpu.registers[31] = cpu.registers[31] - 1u;
        let packed_pc = (next_pc.y << 16u) | (next_pc.x & 0xFFFFu);
        mem_write(cpu.registers[31], packed_pc);

        let tx = imm & 0xFFFFu;
        let ty = (imm >> 16u) & 0xFFFFu;
        next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
    } else if (opcode == OPCODE_RET) {
        let packed_pc = mem_read(cpu.registers[31]);
        cpu.registers[31] = cpu.registers[31] + 1u;
        let tx = packed_pc & 0xFFFFu;
        let ty = (packed_pc >> 16u) & 0xFFFFu;
        // Unlike CALL's jump target, the saved return address is already
        // in raw pixel units - no INSTR_WIDTH scaling here.
        next_pc = vec2<u32>(tx, ty);
    } else if (opcode == OPCODE_JMP) {
        let tx = imm & 0xFFFFu;
        let ty = (imm >> 16u) & 0xFFFFu;
        next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
    } else if (opcode == OPCODE_JZ) {
        // Despite the name, this jumps when the CMP flag (r0) is nonzero
        // (i.e. "jump if equal") - matches GlyphCPUv2's own comment.
        if (cpu.registers[0] != 0u) {
            let tx = imm & 0xFFFFu;
            let ty = (imm >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_SYSCALL) {
        let syscall_num = imm;
        if (syscall_num == 1u) { // WRITE
            let addr = cpu.registers[1];
            let length = cpu.registers[2];
            var i: u32 = 0u;
            loop {
                if (i >= length) { break; }
                let val = mem_read(addr + i);
                let idx = cpu.output_ptr;
                if (idx < uniforms.output_buffer_size) {
                    output[cpu_id * uniforms.output_buffer_size + idx] = val;
                }
                cpu.output_ptr = cpu.output_ptr + 1u;
                i = i + 1u;
            }
            cpu.registers[rd] = 0u;
        } else if (syscall_num == 2u) { // READ
            let addr = cpu.registers[1];
            let length = cpu.registers[2];
            var i: u32 = 0u;
            loop {
                if (i >= length) { break; }
                mem_write(addr + i, 0u);
                i = i + 1u;
            }
            cpu.registers[rd] = 0u;
        } else if (syscall_num == 3u || syscall_num == 4u || syscall_num == 6u) { // FILE_WRITE, FILE_READ, DEBUG
            cpu.registers[rd] = 0u;
        } else if (syscall_num == 5u) { // EXIT
            cpu.registers[rd] = cpu.registers[1]; // Return status
            cpu.running = 0u;
            cpus[cpu_id] = cpu;
            return;
        } else if (syscall_num >= 16u && syscall_num <= 255u) { // GeOS MMIO
            cpu.registers[rd] = 0u;
        } else { // Unknown
            cpu.registers[rd] = 4294967295u; // -1 as u32
        }
    } else if (opcode == OPCODE_HALT) {
        cpu.running = 0u;
        cpus[cpu_id] = cpu;
        return;
    }

    cpu.pc = next_pc;
    cpus[cpu_id] = cpu;
}
"""


def build_shader(opcode_map: OpcodeMapV2) -> str:
    consts, checks = generate_wgsl_opcode_table(opcode_map)
    src = _SHADER_TEMPLATE.replace("__OPCODE_CONSTS__", consts)
    src = src.replace("__OPCODE_CHECKS__", checks)
    return src


def make_cpu_state_array(n_cpus: int = 1):
    """One SpatialCPU per lane: pc(2) + registers(32) + running(1) + output_ptr(1) = 36 u32."""
    dtype = np.dtype([
        ('pc', np.uint32, 2),
        ('registers', np.uint32, 32),
        ('running', np.uint32),
        ('output_ptr', np.uint32),
    ])
    cpus = np.zeros(n_cpus, dtype=dtype)
    cpus['running'] = 1
    return cpus, dtype
