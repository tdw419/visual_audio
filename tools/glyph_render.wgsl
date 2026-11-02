// glyph_render.wgsl
// GPU render shader for multi-window rendering
// Reads WCB rows from data_memory and outputs a composited image based on Z-order

@group(0) @binding(0) var<storage, read> data_memory: array<i32>;
@group(0) @binding(1) var<storage, read_write> out_image: array<u32>;

const SCREEN_W: u32 = 800u;
const SCREEN_H: u32 = 600u;
const WCB_BASE: u32 = 100u;
const WCB_STRIDE: u32 = 16u;
const MAX_WINDOWS: u32 = 4u;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let x = global_id.x;
    let y = global_id.y;
    
    if (x >= SCREEN_W || y >= SCREEN_H) {
        return;
    }
    
    // Background color: dark gray (RGBA format for Python PIL)
    var out_color: u32 = 0xFF222222u;
    var highest_z: i32 = -1;
    
    for (var i: u32 = 0u; i < MAX_WINDOWS; i = i + 1u) {
        let base = WCB_BASE + i * WCB_STRIDE;
        let state = data_memory[base + 0u];
        if (state == 0) {
            continue;
        }
        let visible = data_memory[base + 8u];
        if (visible == 0) {
            continue;
        }
        
        let wx = data_memory[base + 1u];
        let wy = data_memory[base + 2u];
        let ww = data_memory[base + 3u];
        let wh = data_memory[base + 4u];
        let wz = data_memory[base + 5u];
        
        if (i32(x) >= wx && i32(x) < wx + ww && i32(y) >= wy && i32(y) < wy + wh) {
            if (wz > highest_z) {
                highest_z = wz;
                // Generate color based on WCB index (AABBGGRR little endian for PIL RGBA is AABBGGRR? Wait, PIL RGBA frombytes expects R, G, B, A order in memory.
                // A 32-bit uint in WGSL is written to memory in little endian.
                // So memory byte order for 0xFF0000FF is FF (byte 0), 00, 00, FF.
                // If we want RED (255, 0, 0, 255), memory should be 0xFF, 0x00, 0x00, 0xFF.
                // As a little-endian u32: 0xFF0000FF.
                if (i == 0u) {
                    out_color = 0xFF0000FFu; // RED
                } else if (i == 1u) {
                    out_color = 0xFF00FF00u; // GREEN
                } else if (i == 2u) {
                    out_color = 0xFFFF0000u; // BLUE
                } else {
                    out_color = 0xFF00FFFFu; // YELLOW
                }
            }
        }
    }
    
    let pixel_idx = y * SCREEN_W + x;
    out_image[pixel_idx] = out_color;
}
