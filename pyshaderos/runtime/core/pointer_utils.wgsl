// runtime/core/pointer_utils.wgsl
// Utility functions to assist in migrating from storage pointers to indices and offsets.
// Created as part of Phase 1.2 of the Storage Pointer Architecture Refactor.

#include "os_abi.wgsl"

// NOTE ON STRUCT-RETURNING FUNCTIONS
//
// The original plan suggested creating helper functions like:
//   fn get_file_handle(index: u32) -> FileHandle { ... }
//
// However, WGSL 1.0 does not support returning struct types from functions.
// The correct refactoring pattern, as shown in Phase 2.1 of the plan, is to
// pass indices/offsets to functions and then access the global storage arrays
// directly from within the function body.
//
// For example:
//   fn my_function(handle_index: u32) {
//       let file_handle = os_fs_file_handles[handle_index];
//       // ... use file_handle
//   }
//
// Therefore, this utility file will only contain simple, non-struct-returning helpers.


// --- Payload Buffer Accessors ---

// Write a u32 value to the global payload buffer at a specific offset.
fn write_payload_data_u32(offset: u32, value: u32) {
    if (offset < os_system_flags[OS_FLAG_PAYLOAD_BUFFER_SIZE_U32]) {
        os_payload_buffer[offset] = value;
    }
}

// Read a u32 value from the global payload buffer at a specific offset.
fn read_payload_data_u32(offset: u32) -> u32 {
    if (offset < os_system_flags[OS_FLAG_PAYLOAD_BUFFER_SIZE_U32]) {
        return os_payload_buffer[offset];
    }
    return 0u;
}

// Write an f32 value to the global payload buffer at a specific offset.
fn write_payload_data_f32(offset: u32, value: f32) {
    if (offset < os_system_flags[OS_FLAG_PAYLOAD_BUFFER_SIZE_U32]) {
        os_payload_buffer[offset] = bitcast<u32>(value);
    }
}

// Read an f32 value from the global payload buffer at a specific offset.
fn read_payload_data_f32(offset: u32) -> f32 {
    if (offset < os_system_flags[OS_FLAG_PAYLOAD_BUFFER_SIZE_U32]) {
        return bitcast<f32>(os_payload_buffer[offset]);
    }
    return 0.0;
}
