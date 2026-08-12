// Spatial checksum: parallel tree reduction over a PixelRTS-encoded storage buffer.
//
// Byte encoding matches pixelrts_v2_converter.py: id_val = byte + 16, packed into
// the low 3 bytes of a u32 (r=bits16-23, g=bits8-15, b=bits0-7). This shader reads
// that same packed u32 layout directly from a storage buffer (one u32 per pixel),
// so a real .rts.png's raw pixel bytes can be reinterpreted straight into it.

@group(0) @binding(0) var memory_texture: texture_2d<u32>;
@group(0) @binding(1) var<storage, read_write> block_sums: array<u32>;

struct Params {
    grid_size: u32,   // width == height of the spatial grid
}
@group(0) @binding(2) var<uniform> params: Params;

var<workgroup> shared_sums: array<u32, 256>;

@compute @workgroup_size(16, 16)
fn parallel_checksum(
    @builtin(global_invocation_id) global_id: vec3<u32>,
    @builtin(local_invocation_id) local_id: vec3<u32>,
    @builtin(workgroup_id) group_id: vec3<u32>
) {
    let local_idx = local_id.y * 16u + local_id.x;
    let grid = params.grid_size;

    var byte_val: u32 = 0u;
    if (global_id.x < grid && global_id.y < grid) {
        let pixel = textureLoad(memory_texture, vec2<i32>(global_id.xy), 0);
        let packed = pixel.r;
        // Undo pixelrts_v2_converter.py's id_val = byte + 16 offset packed as (r<<16 | g<<8 | b)
        let id_val = packed & 0x00FFFFFFu;
        byte_val = id_val - 16u;
    }

    shared_sums[local_idx] = byte_val;
    workgroupBarrier();

    for (var stride = 128u; stride > 0u; stride >>= 1u) {
        if (local_idx < stride) {
            shared_sums[local_idx] += shared_sums[local_idx + stride];
        }
        workgroupBarrier();
    }

    if (local_idx == 0u) {
        let groups_per_row = (grid + 15u) / 16u;
        let block_idx = group_id.y * groups_per_row + group_id.x;
        block_sums[block_idx] = shared_sums[0];
    }
}
