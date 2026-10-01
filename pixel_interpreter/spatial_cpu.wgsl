// spatial_cpu.wgsl
// GPU-Native Execution Substrate for Geometry OS

@group(0) @binding(0) var tex_current: texture_2d<f32>;
@group(0) @binding(1) var tex_next: texture_storage_2d<rgba8unorm, write>;

// Optional: a write-intent buffer if we want strict deterministic parallel routing,
// but for a single execution head, thread (0,0) can just do sequential writes to a storage buffer.
// Here we implement the pure 2D ping-pong texture approach.

fn get_pixel(x: i32, y: i32) -> vec4<f32> {
    return textureLoad(tex_current, vec2<i32>(x, y), 0);
}

fn pack_pixel(val: vec4<f32>) -> vec4<f32> {
    return val; // In WGSL rgba8unorm handles 0.0-1.0 float mapping (i.e. byte / 255.0)
}

fn to_byte(f: f32) -> u32 {
    return u32(f * 255.0 + 0.5);
}

fn to_float(b: u32) -> f32 {
    return f32(b) / 255.0;
}

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let x = i32(global_id.x);
    let y = i32(global_id.y);
    
    if (x >= 256 || y >= 256) {
        return;
    }

    // Default: propagate current state to next state
    var current_val = get_pixel(x, y);
    var next_val = current_val;

    // -------------------------------------------------------------------------
    // Execution Head Logic (Master Core at 0,0)
    // -------------------------------------------------------------------------
    // In a multi-head CA, every pixel could theoretically evaluate this,
    // but for the CPU bootstrap, (0,0) manages the global PC.
    let state_pixel = get_pixel(0, 0);
    let pc_x = i32(to_byte(state_pixel.r));
    let pc_y = i32(to_byte(state_pixel.g));
    let halt_flag = to_byte(state_pixel.b);
    let direction = to_byte(state_pixel.a);

    let acc_pixel = get_pixel(1, 0);
    var acc = to_byte(acc_pixel.r) | (to_byte(acc_pixel.g) << 8) | (to_byte(acc_pixel.b) << 16) | (to_byte(acc_pixel.a) << 24);

    if (halt_flag == 0u) {
        let inst = get_pixel(pc_x, pc_y);
        let opcode = to_byte(inst.r);
        let src_a = to_byte(inst.g);
        let src_b = to_byte(inst.b);
        let dst = to_byte(inst.a);

        var next_pc_x = pc_x;
        var next_pc_y = pc_y;
        var next_halt = halt_flag;
        var next_dir = direction;
        
        var write_target_x = -1;
        var write_target_y = -1;
        var write_val = vec4<f32>(0.0);

        // Advance PC based on direction
        if (direction == 0u) { next_pc_x = (pc_x + 1) % 256; }
        else if (direction == 1u) { next_pc_y = (pc_y + 1) % 256; }
        else if (direction == 2u) { next_pc_x = (pc_x - 1 + 256) % 256; }
        else if (direction == 3u) { next_pc_y = (pc_y - 1 + 256) % 256; }

        // Core ISA Evaluation
        switch opcode {
            case 0u: { /* NOP */ }
            case 1u: { acc = dst; } // SET
            case 2u: { acc = acc + src_b; } // ADD
            case 3u: { acc = acc - src_b; } // SUB
            case 4u: { // LOAD
                let mem_val = get_pixel(i32(src_a), i32(src_b));
                acc = to_byte(mem_val.r);
            }
            case 5u: { // STORE
                write_target_x = i32(src_a);
                write_target_y = i32(src_b);
                write_val = vec4<f32>(to_float(acc & 0xFFu), 0.0, 0.0, 1.0);
            }
            case 6u: { // JMP
                next_pc_x = i32(src_a);
                next_pc_y = i32(src_b);
            }
            case 7u: { // JZ
                if (acc == 0u) {
                    next_pc_x = i32(src_a);
                    next_pc_y = i32(src_b);
                }
            }
            case 13u: { // LOAD_COORD
                let mx = to_byte(get_pixel(i32(src_a), 0).r);
                let my = to_byte(get_pixel(i32(src_b), 0).r);
                acc = mx | (my << 8);
            }
            case 24u: { next_dir = 0u; } // DIR_RIGHT
            case 25u: { next_dir = 1u; } // DIR_DOWN
            case 26u: { next_dir = 2u; } // DIR_LEFT
            case 27u: { next_dir = 3u; } // DIR_UP
            case 28u: { // CH_READ
                let mx = i32(acc >> 8u) & 0xFF;
                let my = i32(acc & 0xFFu);
                let p = get_pixel(mx, my);
                if (dst == 0u) { acc = to_byte(p.r); }
                else if (dst == 1u) { acc = to_byte(p.g); }
                else if (dst == 2u) { acc = to_byte(p.b); }
                else if (dst == 3u) { acc = to_byte(p.a); }
            }
            case 29u: { // CH_WRITE
                let mx = i32((acc >> 8u) & 0xFFu);
                let my = i32(acc & 0xFFu);
                let val = get_pixel(i32(src_a), i32(src_b)).r;
                
                write_target_x = mx;
                write_target_y = my;
                write_val = get_pixel(mx, my);
                
                let ch = dst % 4u;
                if (ch == 0u) { write_val.r = val; }
                else if (ch == 1u) { write_val.g = val; }
                else if (ch == 2u) { write_val.b = val; }
                else if (ch == 3u) { write_val.a = val; }
            }
            case 255u: { next_halt = 1u; } // HALT
            default: {}
        }

        // Apply mutations if this specific pixel thread is the target
        if (x == 0 && y == 0) {
            next_val = vec4<f32>(to_float(u32(next_pc_x)), to_float(u32(next_pc_y)), to_float(next_halt), to_float(next_dir));
        } else if (x == 1 && y == 0) {
            next_val = vec4<f32>(to_float(acc & 0xFFu), to_float((acc >> 8u) & 0xFFu), to_float((acc >> 16u) & 0xFFu), to_float((acc >> 24u) & 0xFFu));
        } else if (x == write_target_x && y == write_target_y) {
            next_val = write_val;
        }
    }

    textureStore(tex_next, vec2<i32>(x, y), next_val);
}
