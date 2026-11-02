// hilbert_scatter.wgsl - scatter linear RAM bytes to Hilbert-curve pixel
// coordinates, given a precomputed (x,y) LUT (same LUT the CPU path caches).
//
// One invocation per pixel index. Reads 3 bytes from `ram` at pixel_idx*3,
// looks up its (x,y) from `lut`, writes RGB into `out_pixels` (row-major,
// width*height*4 bytes, RGBA8 to match typical GPU texture layout).

struct Dims {
    width: u32,
    height: u32,
    total_pixels: u32,
    _pad: u32,
};

@group(0) @binding(0) var<storage, read> ram: array<u32>;        // packed bytes, 4 per u32
@group(0) @binding(1) var<storage, read> lut: array<u32>;        // packed (x<<16 | y) per pixel_idx
@group(0) @binding(2) var<storage, read_write> out_pixels: array<u32>; // packed RGBA8 per output pixel
@group(0) @binding(3) var<uniform> dims: Dims;

fn read_byte(byte_idx: u32) -> u32 {
    let word = ram[byte_idx / 4u];
    let shift = (byte_idx % 4u) * 8u;
    return (word >> shift) & 0xFFu;
}

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let pixel_idx = gid.x;
    if (pixel_idx >= dims.total_pixels) {
        return;
    }

    let byte_base = pixel_idx * 3u;
    let r = read_byte(byte_base);
    let g = read_byte(byte_base + 1u);
    let b = read_byte(byte_base + 2u);

    let coord = lut[pixel_idx];
    let x = coord >> 16u;
    let y = coord & 0xFFFFu;
    let out_idx = y * dims.width + x;

    let packed = r | (g << 8u) | (b << 16u) | (255u << 24u);
    out_pixels[out_idx] = packed;
}
