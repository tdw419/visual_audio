// runtime/core/host_abi.wgsl
#include "global_bindings.wgsl" // Include the global bindings

// Communication contract between GPU shaders and CPU host
struct ServiceRequest {
    id: u32, service: u32, opcode: u32, 
    arg0: u32, arg1: u32, arg2: u32,
    payload_offset: u32, payload_len: u32,
    status: atomic<u32>  // 0=pending, 1=processing, 2=complete
}

struct ServiceResponse {
    id: u32, status: atomic<u32>,
    result0: u32, result1: u32,
    payload_offset: u32, payload_len: u32
}

// Helper function to allocate a request slot
// A real allocator would be more sophisticated, this is a simple example
fn alloc_request_slot() -> u32 {
    for (var i: u32 = 0u; i < arrayLength(&service_requests); i = i + 1u) {
        // Atomically compare_exchange_weak from 2 (Complete) to 0 (Pending)
        // This ensures only one thread picks up a completed slot at a time
        // If it's already 0 (Pending) or 1 (Processing), we skip.
        let old_status = atomicCompareExchangeWeak(&service_requests[i].status, 2u, 0u).old_value;
        if (old_status == 2u || old_status == 0u) { // Old value was 2 (complete) or 0 (free), so we claimed it as 0 (pending)
            // It was either 2 (old_status was 2, now 0), or already 0 (we made it 0 again)
            // Either way, we can use this slot.
            atomicStore(&service_requests[i].status, 0u); // Ensure it's pending
            return i;
        }
    }
    return 0xFFFFFFFFu; // No free slot
}

// Helper function to write debug log entry
fn debug_log(code: u32, arg0: u32, arg1: u32, arg2: u32) {
    let index = atomicAdd(&debug_index, 1u);
    // Ensure we don't go out of bounds (simplified, no wrap around for now)
    if (index < arrayLength(&debug_log) / 4u) { // 4 u32s per log entry
        let offset = index * 4u;
        debug_log[offset] = code;
        debug_log[offset + 1u] = arg0;
        debug_log[offset + 2u] = arg1;
        debug_log[offset + 3u] = arg2;
    }
}
