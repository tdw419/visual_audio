// runtime/core/abi.wgsl
// Application Binary Interface (ABI) for Host-Shader communication

// --- Host Service IDs ---
const SERVICE_FILESYSTEM: u32 = 1u;
const SERVICE_NETWORK: u32 = 2u;
const SERVICE_RELOAD: u32 = 3u;
const SERVICE_PIPELINE: u32 = 4u;
const SERVICE_DEBUG: u32 = 5u;
const SERVICE_TIME: u32 = 6u;
const SERVICE_RANDOM: u32 = 7u;

// --- Filesystem Opcodes ---
const FS_OPEN: u32 = 0u;
const FS_READ: u32 = 1u;
const FS_WRITE: u32 = 2u;
const FS_CLOSE: u32 = 3u;

// --- Shader Reload Opcodes ---
const RELOAD_SHADER: u32 = 0u;
const COMPILE_SHADER: u32 = 1u;

// --- Debug Opcodes ---
const DEBUG_LOG: u32 = 0u;
const DEBUG_BREAKPOINT: u32 = 1u;


// --- Service Request Struct ---
struct ServiceRequest {
    id: u32,          // Request ID (for matching with response)
    service: u32,     // Which host service to call (e.g., FILESYSTEM, NETWORK)
    opcode: u32,      // Specific operation (e.g., FS_READ, NET_SEND)
    arg0: u32,        // General purpose arguments
    arg1: u32,
    arg2: u32,
    payload_offset: u32, // Offset into shared_payload_buffer for request data
    payload_len: u32,    // Length of request data
    status: atomic<u32>  // 0=pending, 1=processing, 2=done_ok, 3=done_error
}

// --- Service Response Struct ---
struct ServiceResponse {
    id: u32,          // Matching request ID
    status: atomic<u32>, // 0=pending, 1=ok, 2=error
    result0: u32,     // General purpose results
    result1: u32,
    payload_offset: u32, // Offset into shared_payload_buffer for response data
    payload_len: u32     // Length of response data
}

// --- Shared Buffers for ABI ---
// These are globally bound at specific indices so shaders can find them

// @group(1) @binding(0) var<storage, read_write> service_requests: array<ServiceRequest, 256>; // Max 256 concurrent requests
// @group(1) @binding(1) var<storage, read_write> service_responses: array<ServiceResponse, 256>; // Max 256 concurrent responses
// @group(1) @binding(2) var<storage, read_write> shared_payload_buffer: array<u32>; // Large buffer for request/response payloads
// @group(1) @binding(3) var<storage, read_write> debug_log_buffer: array<u32>; // Buffer for shader debug logs
// @group(1) @binding(4) var<uniform> control_flags: u32; // Host control flags (e.g., DEBUG_MODE)
