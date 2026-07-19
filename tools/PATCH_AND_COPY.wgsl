/* 
 * PATCH AND COPY COMPILER SHADER (Geometry OS)
 *
 * This WGSL compute shader runs natively on the GPU. It reads opcode templates
 * from a read-only atlas, patches them with operands using bitwise operations,
 * and writes an executable pixel program into the VRAM buffer. 
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

/* 
 * ATLAS ENCODING CONSTANTS
 * Assuming atlas is 1D array of base opcodes for simplicity
 * 0 = LDI (236, 80, 80)
 * 1 = ADD (80, 236, 120)
 * 2 = PRT (247, 83, 80)
 * 3 = HLT (255, 0, 0)
 */
const TEMPLATE_LDI: u32 = 0u;
const TEMPLATE_ADD: u32 = 1u;
const TEMPLATE_PRT: u32 = 2u;
const TEMPLATE_HLT: u32 = 3u;

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

// Emits a raw base opcode from the atlas
fn emit_opcode(compiler_id: u32, opcode_index: u32) {
    let base_opcode = template_atlas[opcode_index];
    emit_pixel(compiler_id, base_opcode.r, base_opcode.g, base_opcode.b);
}

/*
 * PATCHING LOGIC
 * Register encoding: r=g=b=50 + (25 * reg_num)
 * Immediate encoding: r=0, g=0, b=val+1
 */
fn emit_register(compiler_id: u32, reg_num: u32) {
    // Patching: Base value 50 | (reg_num * 25)
    let val = 50u + (reg_num * 25u); 
    emit_pixel(compiler_id, val, val, val);
}

fn emit_immediate(compiler_id: u32, value: u32) {
    emit_pixel(compiler_id, 0u, 0u, value + 1u);
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
     * COMPILATION TARGET:
     * LDI r3 42
     * LDI r1 10
     * ADD r3 r1
     * PRT r3
     * HLT
     *
     * The GPU will literally emit this program spatially pixel-by-pixel.
     */
    
    // 1. LDI r3 42
    emit_opcode(compiler_id, TEMPLATE_LDI);
    emit_register(compiler_id, 3u); // Patches to r3
    emit_immediate(compiler_id, 42u); // Patches to 42

    // 2. LDI r1 10
    emit_opcode(compiler_id, TEMPLATE_LDI);
    emit_register(compiler_id, 1u);
    emit_immediate(compiler_id, 10u);
    
    // 3. ADD r3 r1
    emit_opcode(compiler_id, TEMPLATE_ADD);
    emit_register(compiler_id, 3u);
    emit_register(compiler_id, 1u);
    
    // 4. PRT r3
    emit_opcode(compiler_id, TEMPLATE_PRT);
    emit_register(compiler_id, 3u);
    
    // 5. HLT
    emit_opcode(compiler_id, TEMPLATE_HLT);
}
