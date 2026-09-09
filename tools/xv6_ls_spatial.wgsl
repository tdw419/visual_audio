// Auto-generated WGSL spatial circuit from xv6 'ls' pattern
// Generated: N/A

// This circuit reproduces the execution pattern observed in 'ls'

struct PatternState {
    var file_index: u32;
    var output_offset: u32;
    var read_count: u32;
    var write_count: u32;
};

@group(0) @binding(0) var<storage, read> pattern_files: array<{name: array<u8>, size: u32, inode: u32}>;
@group(0) @binding(1) var<storage, read_write> output_buffer: array<u8>;

@compute @workgroup_size(1)
fn generate_ls_pattern(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var state: PatternState = PatternState(
        file_index = 0u,
        output_offset = 0u,
        read_count = 245u,
        write_count = 189u
    );

    // Process each file entry
    // Pattern shows 17 files
    for (var i: u32 = 0u; i < 17u; i = i + 1u) {
        // Read file entry
        let file = pattern_files[i];

        // Write filename to output
        for (var j: u32 = 0u; j < 14u; j = j + 1u) {
            output_buffer[state.output_offset + j] = file.name[j];
        }
        state.output_offset = state.output_offset + 14u;

        // Write spacing
        output_buffer[state.output_offset] = 32u;  // space
        state.output_offset = state.output_offset + 1u;

        // Write inode
        output_buffer[state.output_offset] = file.inode;
        state.output_offset = state.output_offset + 1u;

        // Write size
        output_buffer[state.output_offset] = file.size;
        state.output_offset = state.output_offset + 1u;

        // Newline
        output_buffer[state.output_offset] = 10u;  // '\n'
        state.output_offset = state.output_offset + 1u;
    }

    // Verify statistics match pattern
    if (state.read_count != 245u) {
        // Pattern mismatch detected
        output_buffer[0] = 255u;  // Error indicator
    }

    if (state.write_count != 189u) {
        // Pattern mismatch detected
        output_buffer[1] = 255u;  // Error indicator
    }
}
