/* 
 * PATCH AND COPY COMPILER SHADER (Geometry OS) v2
 *
 * This WGSL compute shader runs natively on the GPU. It reads opcode templates
 * from a read-only atlas, patches them with operands using the official 
 * GlyphCPUv2 4-pixel instruction format, and writes an executable pixel program
 * into the VRAM buffer. 
 *
 * It compiles code *without* the host CPU.
 */

struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

// 1. Storage Buffers
@group(0) @binding(0) var<storage, read> template_atlas: array<Pixel>;       // ROM: Base Opcode Colors
@group(0) @binding(1) var<storage, read_write> vram: array<Pixel>;           // RAM: Target executable space
@group(0) @binding(2) var<storage, read_write> write_head: array<vec2<u32>>; // Compiler PC (Where to write next)

struct Uniforms {
    vram_width: u32,
    vram_height: u32,
    atlas_width: u32,
}
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

// ATLAS INDICES (Must match the Python runner's provided atlas order)
const OP_LDI: u32 = 0u;
const OP_ADD: u32 = 1u;
const OP_CMP: u32 = 2u;
const OP_JZ: u32 = 3u;
const OP_PRT: u32 = 4u;
const OP_JMP: u32 = 5u;
const OP_HALT: u32 = 6u;

const UNUSED_REG: u32 = 255u;

// Helper: Read a pixel from the VRAM
fn get_vram_index(x: u32, y: u32) -> u32 {
    return y * uniforms.vram_width + x;
}

// Helper: Write a pixel to the VRAM
fn emit_pixel(compiler_id: u32, r: u32, g: u32, b: u32) {
    let x = write_head[compiler_id].x;
    let y = write_head[compiler_id].y;
    
    let index = get_vram_index(x, y);
    vram[index].r = r;
    vram[index].g = g;
    vram[index].b = b;
    vram[index].a = 255u;
    
    // Advance Compiler Write Head with 2D wrapping
    var new_head = write_head[compiler_id];
    new_head.x = new_head.x + 1u;
    if (new_head.x >= uniforms.vram_width) {
        new_head.x = 0u;
        new_head.y = new_head.y + 1u;
    }
    write_head[compiler_id] = new_head;
}

// Emit a full 4-pixel Glyph ISA v2 instruction
fn emit_instr(compiler_id: u32, opcode: u32, rs1: u32, rs2: u32, rd: u32, imm: u32) {
    // 1. Opcode pixel
    let base_opcode = template_atlas[opcode];
    emit_pixel(compiler_id, base_opcode.r, base_opcode.g, base_opcode.b);
    
    // 2. Registers pixel
    emit_pixel(compiler_id, rs1, rs2, rd);
    
    // 3. Immediate Low24 pixel
    let low24 = imm & 0xFFFFFFu;
    let r_low = (low24 >> 16u) & 0xFFu;
    let g_low = (low24 >> 8u) & 0xFFu;
    let b_low = low24 & 0xFFu;
    emit_pixel(compiler_id, r_low, g_low, b_low);
    
    // 4. Immediate High24 pixel
    let high24 = (imm >> 24u) & 0xFFFFFFu;
    let r_high = (high24 >> 16u) & 0xFFu;
    let g_high = (high24 >> 8u) & 0xFFu;
    let b_high = high24 & 0xFFu;
    emit_pixel(compiler_id, r_high, g_high, b_high);
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let compiler_id = global_id.x;
    
    // Only thread 0 compiles the program for now
    if (compiler_id != 0u) {
        return;
    }
    
    // Reset write head to start of VRAM
    write_head[compiler_id] = vec2<u32>(0u, 0u);
    
    /* 
     * COMPILATION TARGET (Loop Demo):
     * 0. LDI r5 0       ; counter = 0
     * 1. LDI r1 5       ; limit = 5
     * 2. CMP r5 r1      ; r0 = (counter == limit)
     * 3. JZ to HALT     ; if equal, jump to instruction 8
     * 4. PRT r5         ; print counter
     * 5. LDI r2 1       ; r2 = 1
     * 6. ADD r5 r2      ; counter += 1
     * 7. JMP to CMP     ; jump back to instruction 2
     * 8. HALT
     *
     * In Glyph v2, instructions are 4 pixels wide.
     * instr 2 -> x = 2*4 = 8, y = 0. Packed imm = (0 << 16) | 8 = 8.
     * instr 8 -> x = 8*4 = 32, y = 0. Packed imm = (0 << 16) | 32 = 32.
     */
    
    // 0. LDI r5, 0
    emit_instr(compiler_id, OP_LDI, UNUSED_REG, UNUSED_REG, 5u, 0u);

    // 1. LDI r1, 5
    emit_instr(compiler_id, OP_LDI, UNUSED_REG, UNUSED_REG, 1u, 5u);
    
    // 2. CMP r5, r1
    emit_instr(compiler_id, OP_CMP, UNUSED_REG, 1u, 5u, 0u);
    
    // 3. JZ 8, 0 (Jump to HALT at instr 8)
    emit_instr(compiler_id, OP_JZ, UNUSED_REG, UNUSED_REG, UNUSED_REG, 8u);
    
    // 4. PRT r5
    emit_instr(compiler_id, OP_PRT, UNUSED_REG, UNUSED_REG, 5u, 0u);
    
    // 5. LDI r2, 1
    emit_instr(compiler_id, OP_LDI, UNUSED_REG, UNUSED_REG, 2u, 1u);
    
    // 6. ADD r5, r2
    emit_instr(compiler_id, OP_ADD, UNUSED_REG, 2u, 5u, 0u);
    
    // 7. JMP 2, 0 (Jump to CMP at instr 2)
    emit_instr(compiler_id, OP_JMP, UNUSED_REG, UNUSED_REG, UNUSED_REG, 2u);
    
    // 8. HALT
    emit_instr(compiler_id, OP_HALT, UNUSED_REG, UNUSED_REG, UNUSED_REG, 0u);
}
