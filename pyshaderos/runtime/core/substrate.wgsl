// substrate.wgsl
#include "os_abi.wgsl"

@compute @workgroup_size(64)
fn main( @builtin(global_invocation_id) gid: vec3<u32>) {
    // Bump frame counter once per dispatch
    if (gid.x == 0u) {
        let frame = atomicAdd(&os_frame_counter, 1u);
        // os_trace_debug_log(gid.x, 0u, 0xDEADu, frame, 0u, 0u, 0u); // Log frame bump
    }
}