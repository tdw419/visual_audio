// runtime/core/global_bindings.wgsl
// Unified global bind group (BG0) layout for Pixel OS

// These structs will be included from host_abi.wgsl (for ServiceRequest, ServiceResponse)
// and substrate.wgsl (for ThreadState), as defined in subsequent steps.

// Bindings for Host-Shader ABI communication
@group(0) @binding(0) var<storage, read_write> service_requests: array<u32>; // Content will be ServiceRequest structs
@group(0) @binding(1) var<storage, read_write> service_responses: array<u32>; // Content will be ServiceResponse structs
@group(0) @binding(2) var<storage, read_write> payload_buffer: array<u32>;

// Debugging buffers
@group(0) @binding(3) var<storage, read_write> debug_log: array<u32>;
@group(0) @binding(4) var<storage, read_write> debug_index: atomic<u32>;

// Bytecode VM specific buffers
@group(0) @binding(5) var<storage, read> bytecode_program: array<u32>;
@group(0) @binding(6) var<storage, read_write> vm_vram: array<u32>;
@group(0) @binding(7) var<storage, read_write> vm_thread_state: array<u32>; // Content will be ThreadState structs

// Global OS State
@group(0) @binding(8) var<storage, read_write> global_frame_counter: atomic<u32>;
@group(0) @binding(9) var<storage, read_write> system_flags: atomic<u32>;

// Future bindings will continue from @binding(10) onwards.
