// runtime/services/syscall_logger.wgsl
#include "../core/os_abi.wgsl"

const SYSCALL_LOGGER_SERVICE_ID: u32 = 1u; // Define a service ID for syscall_logger

// Global constants from os_abi.wgsl
// OS_MAX_REQUESTS, OS_MAX_RESPONSES, OS_DEBUG_ENTRIES
// os_service_requests, os_service_responses, os_debug_entries, os_debug_index

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    // This shader runs on a single workgroup (gid.x == 0u)
    if (gid.x != 0u) { return; }

    // Iterate through potential service requests
    for (var i: u32 = 0u; i < OS_MAX_REQUESTS; i = i + 1u) {
        let request_entry = &os_service_requests[i];

        // Check if this request is for our service and is pending
        // Using a magic value for 'service_id' for now, this needs a proper enum later
        if (request_entry.arg0 == SYSCALL_LOGGER_SERVICE_ID && request_entry.opcode == 0u) { // opcode 0 could mean "log this"
            // Log the syscall details
            os_debug_log(request_entry.opcode, request_entry.arg0, request_entry.arg1);
            os_debug_log(request_entry.arg2, request_entry.arg3, 0u); // Log remaining args

            // Write a response
            // The slot for response usually matches the request slot
            let response_entry = &os_service_responses[i];
            response_entry.status = 1u; // Success
            response_entry.value0 = request_entry.opcode;
            response_entry.value1 = request_entry.arg0;
            response_entry.value2 = i; // Echo back the request index

            // Clear the request to mark it as processed
            request_entry.opcode = 0xFFFFu; // Mark as consumed (or use a status flag)
        }
    }
}
