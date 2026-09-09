// glyph_interact.wgsl
// GPU interaction shader for the spatial window coordinator (WC007).
//
// Consumes one mouse event from the `events` buffer and mutates the WCB
// spatial rows in `data_memory`:
//   - type 1 (click): hit-test (x, y) -> raise the topmost window's Z to max_z + 1
//   - type 2 (drag):  hit-test (x, y) -> move the topmost window there by (dx, dy)
//
// The render shader (glyph_render.wgsl) reflects these mutations on the
// next frame — interaction and display are both GPU-side. A Python
// semantic mirror (test_window_interaction.py) verifies the mutation
// logic byte-for-byte against real GPU execution.

@group(0) @binding(0) var<storage, read_write> data_memory: array<i32>;
@group(0) @binding(1) var<storage, read> events: array<i32>;

const WCB_BASE: u32 = 100u;
const WCB_STRIDE: u32 = 16u;
const MAX_WINDOWS: u32 = 4u;

// Event layout: [type, x, y, dx, dy, reserved, reserved, reserved]
//   type 0 = no-op, 1 = click, 2 = drag
const EV_TYPE: u32 = 0u;
const EV_X: u32 = 1u;
const EV_Y: u32 = 2u;
const EV_DX: u32 = 3u;
const EV_DY: u32 = 4u;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    if (global_id.x != 0u) {
        return;
    }

    let ev_type = events[EV_TYPE];
    if (ev_type == 0) {
        return;
    }

    if (ev_type == 1) {
        // --- Click: raise the topmost window at (x, y) to the front. ---
        let mx = events[EV_X];
        let my = events[EV_Y];

        var hit: i32 = -1;
        var hit_z: i32 = -1;
        for (var i: u32 = 0u; i < MAX_WINDOWS; i = i + 1u) {
            let base = WCB_BASE + i * WCB_STRIDE;
            if (data_memory[base + 0u] == 0) { continue; }
            if (data_memory[base + 8u] == 0) { continue; }
            let wx = data_memory[base + 1u];
            let wy = data_memory[base + 2u];
            let ww = data_memory[base + 3u];
            let wh = data_memory[base + 4u];
            let wz = data_memory[base + 5u];
            if (mx >= wx && mx < wx + ww && my >= wy && my < wy + wh) {
                if (wz > hit_z) {
                    hit_z = wz;
                    hit = i32(i);
                }
            }
        }

        if (hit >= 0) {
            var max_z: i32 = 0;
            for (var j: u32 = 0u; j < MAX_WINDOWS; j = j + 1u) {
                let b = WCB_BASE + j * WCB_STRIDE;
                if (data_memory[b + 0u] == 0) { continue; }
                let z = data_memory[b + 5u];
                if (z > max_z) { max_z = z; }
            }
            let hb = WCB_BASE + u32(hit) * WCB_STRIDE;
            data_memory[hb + 5u] = max_z + 1;
        }
    } else if (ev_type == 2) {
        // --- Drag: move the topmost window at (x, y) by (dx, dy). ---
        let ax = events[EV_X];
        let ay = events[EV_Y];
        let ddx = events[EV_DX];
        let ddy = events[EV_DY];

        var hit: i32 = -1;
        var hit_z: i32 = -1;
        for (var i: u32 = 0u; i < MAX_WINDOWS; i = i + 1u) {
            let base = WCB_BASE + i * WCB_STRIDE;
            if (data_memory[base + 0u] == 0) { continue; }
            if (data_memory[base + 8u] == 0) { continue; }
            let wx = data_memory[base + 1u];
            let wy = data_memory[base + 2u];
            let ww = data_memory[base + 3u];
            let wh = data_memory[base + 4u];
            let wz = data_memory[base + 5u];
            if (ax >= wx && ax < wx + ww && ay >= wy && ay < wy + wh) {
                if (wz > hit_z) {
                    hit_z = wz;
                    hit = i32(i);
                }
            }
        }

        if (hit >= 0) {
            let hb = WCB_BASE + u32(hit) * WCB_STRIDE;
            data_memory[hb + 1u] = data_memory[hb + 1u] + ddx;
            data_memory[hb + 2u] = data_memory[hb + 2u] + ddy;
        }
    }
}
