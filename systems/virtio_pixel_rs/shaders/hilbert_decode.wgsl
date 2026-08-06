// Hilbert curve pixel decoder (WGSL compute shader)
// Maps byte_index → pixel coordinates → RGB values
// Replaces CPU-side hilbert_d2xy() and pixel extraction

// Hilbert curve: map d (0 to n²-1) to (x, y) coordinates
fn hilbert_d2xy(n: u32, d: u32) -> vec2<u32> {
    var x: u32 = 0u;
    var y: u32 = 0u;
    var s: u32 = 1u;
    var rx: u32;
    var ry: u32;
    var t: u32 = d;

    while (s < n) {
        rx = (t >> 1u) & 1u;
        ry = (t ^ rx) & 1u;

        // Rotate/flip quadrant
        if (ry == 0u) {
            if (rx == 1u) {
                x = s - 1u - x;
                y = s - 1u - y;
            }
            let temp_x = x;
            x = y;
            y = temp_x;
        }

        x += s * rx;
        y += s * ry;
        t >>= 2u;
        s <<= 1u;
    }

    return vec2<u32>(x, y);
}

// Decode RGB pixel to byte value (Ubuntu disk encoding)
// Ubuntu disk uses the encode_ubuntu_spatial.py encoding:
// Each byte is stored as a single RGB pixel where:
// - R channel = byte value
// - G channel = 0 (unused)
// - B channel = 0 (unused)
fn decode_pixel_to_byte(pixel: vec4<f32>) -> u32 {
    let r = u32(pixel.r * 255.0);
    // For Ubuntu disk, only the R channel contains data
    // G and B are always 0 in this encoding
    return r;
}

// Compute shader workgroup layout
// Each workgroup processes 256 bytes (16x16 Hilbert block)
@group(0) @binding(0) var frame_texture: texture_2d<f32>;
@group(0) @binding(1) var<storage, read_write> output_buffer: array<u32>;

struct DecodeParams {
    frame_index: u32,      // Which MKV frame to read from
    start_byte: u32,       // Starting byte index for this dispatch
    num_bytes: u32,        // Number of bytes to decode
    frame_size: u32,       // Frame size (4096)
};

@group(0) @binding(2) var<uniform> params: DecodeParams;

// Each work item decodes one byte
@compute @workgroup_size(16, 16, 1)
fn decode_hilbert_bytes(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let byte_idx = global_id.x + global_id.y * 256u + params.start_byte;

    if (byte_idx >= params.start_byte + params.num_bytes) {
        return; // Out of bounds
    }

    // Use Hilbert curve mapping (verified for spatial consistency)
    let hilbert_coord = hilbert_d2xy(params.frame_size, byte_idx);
    let pixel_coord = vec2<i32>(i32(hilbert_coord.x), i32(hilbert_coord.y));

    // Sample texture at Hilbert coordinate
    let pixel = textureLoad(frame_texture, pixel_coord, 0);

    // Decode pixel to byte
    let decoded_byte = decode_pixel_to_byte(pixel);

    // Write to output buffer
    output_buffer[byte_idx - params.start_byte] = decoded_byte;
}