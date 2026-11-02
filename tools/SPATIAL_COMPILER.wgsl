/* 
 * SPATIAL COMPILER SHADER (Geometry OS - VLM Integration)
 *
 * This WGSL compute shader applies VLM-generated patches directly to VRAM.
 * It reads patch operations from a buffer and executes them natively on GPU.
 *
 * Architecture:
 *   VLM Observer (CPU) → Patch Buffer → Spatial Compiler (GPU) → VRAM Update
 */

struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

// Patch operation types
const OP_NOP: u32 = 0u;           // No operation
const OP_WRITE_PIXEL: u32 = 1u;    // Write single pixel at (x, y)
const OP_COPY_BLOCK: u32 = 2u;     // Copy block from src to dest
const OP_FILL_RECT: u32 = 3u;      // Fill rectangular region
const OP_CLEAR_REGION: u32 = 4u;   // Clear region to black

// Individual patch operation
struct PatchOp {
    op_type: u32,      // Operation type
    x: u32,            // Target X coordinate
    y: u32,            // Target Y coordinate
    z: u32,            // Target Z coordinate (frame index)
    r: u32,            // Red channel (for WRITE_PIXEL)
    g: u32,            // Green channel
    b: u32,            // Blue channel
    width: u32,        // Width (for COPY_BLOCK, FILL_RECT)
    height: u32,       // Height
    src_x: u32,        // Source X (for COPY_BLOCK)
    src_y: u32,        // Source Y
    src_z: u32,        // Source Z
}

// Buffers
@group(0) @binding(0) var<storage, read> patch_ops: array<PatchOp>;    // Patch operations
@group(0) @binding(1) var<storage, read_write> vram: array<Pixel>;    // 3D VRAM
@group(0) @binding(2) var<storage, read> op_count: array<u32>;        // Number of operations

struct Uniforms {
    vram_width: u32,
    vram_height: u32,
    vram_depth: u32,
}
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

// Helper: Convert 3D coordinate to linear index
fn vram_index(x: u32, y: u32, z: u32) -> u32 {
    return (z * uniforms.vram_width * uniforms.vram_height) +
           (y * uniforms.vram_width) +
           x;
}

// Helper: Read pixel from VRAM
fn read_pixel(x: u32, y: u32, z: u32) -> Pixel {
    let idx = vram_index(x, y, z);
    return vram[idx];
}

// Helper: Write pixel to VRAM
fn write_pixel(x: u32, y: u32, z: u32, r: u32, g: u32, b: u32) {
    let idx = vram_index(x, y, z);
    vram[idx].r = r;
    vram[idx].g = g;
    vram[idx].b = b;
    vram[idx].a = 255u;
}

// Operation: Write single pixel
fn op_write_pixel(op: PatchOp) {
    write_pixel(op.x, op.y, op.z, op.r, op.g, op.b);
}

// Operation: Copy rectangular block
fn op_copy_block(op: PatchOp) {
    for (var dy = 0u; dy < op.height; dy = dy + 1u) {
        for (var dx = 0u; dx < op.width; dx = dx + 1u) {
            let src_px = read_pixel(op.src_x + dx, op.src_y + dy, op.src_z);
            write_pixel(op.x + dx, op.y + dy, op.z, src_px.r, src_px.g, src_px.b);
        }
    }
}

// Operation: Fill rectangular region
fn op_fill_rect(op: PatchOp) {
    for (var dy = 0u; dy < op.height; dy = dy + 1u) {
        for (var dx = 0u; dx < op.width; dx = dx + 1u) {
            write_pixel(op.x + dx, op.y + dy, op.z, op.r, op.g, op.b);
        }
    }
}

// Operation: Clear region to black
fn op_clear_region(op: PatchOp) {
    for (var dy = 0u; dy < op.height; dy = dy + 1u) {
        for (var dx = 0u; dx < op.width; dx = dx + 1u) {
            write_pixel(op.x + dx, op.y + dy, op.z, 0u, 0u, 0u);
        }
    }
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let op_idx = global_id.x;
    let total_ops = op_count[0];
    
    // Bounds check
    if (op_idx >= total_ops) {
        return;
    }
    
    let op = patch_ops[op_idx];
    
    // Execute operation
    switch (op.op_type) {
        case OP_WRITE_PIXEL: {
            op_write_pixel(op);
        }
        case OP_COPY_BLOCK: {
            op_copy_block(op);
        }
        case OP_FILL_RECT: {
            op_fill_rect(op);
        }
        case OP_CLEAR_REGION: {
            op_clear_region(op);
        }
        default: {
            // OP_NOP - do nothing
        }
    }
}