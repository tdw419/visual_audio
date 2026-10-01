// Minimal compute shader used as the proof payload for pixel-encoded SPIR-V:
// doubles every u32 in `data`. Compiled offline to SPIR-V (see
// examples/spirv_from_pixels.rs), then that SPIR-V is pixel-encoded and
// decoded back at runtime instead of ever being WGSL-compiled again.
@group(0) @binding(0)
var<storage, read_write> data: array<u32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    data[gid.x] = data[gid.x] * 2u;
}
