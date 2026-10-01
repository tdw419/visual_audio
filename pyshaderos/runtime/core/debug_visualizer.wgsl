// runtime/core/debug_visualizer.wgsl
#include "os_abi.wgsl"

// Helper function to get a color based on opcode type
fn get_opcode_color(opcode: u32) -> u32 {
    switch (opcode) {
        case 0u: { return 0x0000FF00; } // NOP - Green
        case 1u: { return 0x00FF0000; } // WRITE_CONST - Red
        case 2u: { return 0x000000FF; } // SYSCALL - Blue
        // Add more opcodes as they are defined in vm_bytecode_kernel.wgsl
        default: { return 0x00AAAAAA; } // Gray for unknown
    }
}

@compute @workgroup_size(64, 1, 1)
fn main( @builtin(global_invocation_id) global_id: vec3<u32>) {
    let thread_id = global_id.x;
    
    // Process debug traces and create visualization
    for (var i: u32 = 0u; i < 1024u; i = i + 1u) {
        let trace_index = thread_id * 1024u + i;
        if (trace_index < OS_MAX_DEBUG_TRACES) {
            let trace = os_debug_traces[trace_index];
            
            // Map thread activity to screen pixels
            let pixel_x = (trace.thread_id % 64u) * 30u; // Assuming a small number of threads visible
            let pixel_y = (trace.pc % 384u) / 384u * OS_DISPLAY_HEIGHT; // Example: Map PC to Y within display height
            let pixel_index = pixel_y * OS_DISPLAY_WIDTH + pixel_x;
            
            if (pixel_index < OS_FRAMEBUFFER_SIZE) {
                // Color code by opcode type
                let color = get_opcode_color(trace.opcode);
                os_visual_debug_data[pixel_index] = color;
            }
        }
    }
}
