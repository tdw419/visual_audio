// file_metadata.wgsl
// GPU shader to query File_Metadata table using spatial lookup

// 288-byte metadata row unpacked into u32s
struct FileMetadata {
    path: array<u32, 64>, // 256 bytes (64 * 4)
    offset_low: u32,      // 8 bytes (offset)
    offset_high: u32,
    size: u32,            // 4 bytes (size)
    mode_uid_gid_type: array<u32, 4>, // 16 bytes
    reserved: u32,        // 4 bytes
}

// Bounding box for the file_metadata table in the pixel grid
struct TableBounds {
    x_min: u32,
    y_min: u32,
    x_max: u32,
    y_max: u32,
    row_count: u32,
    row_length_bytes: u32, // 288
}

// Storage bindings
@group(0) @binding(0) var<storage, read> pixel_buffer: array<u32>;
@group(0) @binding(1) var<uniform> table_bounds: TableBounds;
@group(0) @binding(2) var<storage, read> target_path: array<u32, 64>;
@group(0) @binding(3) var<storage, read_write> query_result: FileMetadata;
@group(0) @binding(4) var<storage, read_write> result_found: atomic<u32>;

// Utility to read a 32-bit word from the RGB 3-byte pixel buffer.
fn read_u32_from_pixels(byte_offset: u32) -> u32 {
    let pixel_idx1 = byte_offset / 3u;
    return pixel_buffer[pixel_idx1]; 
}

fn compare_paths(a: array<u32, 64>, b: array<u32, 64>) -> bool {
    for (var i = 0u; i < 64u; i = i + 1u) {
        if (a[i] != b[i]) {
            return false;
        }
    }
    return true;
}

@compute @workgroup_size(64)
fn find_file_metadata(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let row_idx = global_id.x;
    if (row_idx >= table_bounds.row_count) {
        return;
    }
    
    let byte_offset = row_idx * table_bounds.row_length_bytes;
    
    var current_path: array<u32, 64>;
    for (var i = 0u; i < 64u; i = i + 1u) {
        current_path[i] = read_u32_from_pixels(byte_offset + (i * 4u));
    }
    
    if (compare_paths(current_path, target_path)) {
        atomicStore(&result_found, 1u);
        
        var fm: FileMetadata;
        fm.path = current_path;
        fm.offset_low = read_u32_from_pixels(byte_offset + 256u);
        fm.offset_high = read_u32_from_pixels(byte_offset + 260u);
        fm.size = read_u32_from_pixels(byte_offset + 264u);
        
        query_result = fm;
    }
}
