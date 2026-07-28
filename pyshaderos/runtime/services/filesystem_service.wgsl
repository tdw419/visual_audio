// runtime/services/filesystem_service.wgsl
// Complete GPU-native filesystem with atomic operations
#include "../core/os_abi.wgsl"

// Filesystem service kernel
const FILESYSTEM_SERVICE_ID: u32 = 4u; // Define a service ID for the filesystem

// File operations
const FS_READ: u32 = 0u;
const FS_WRITE: u32 = 1u;
const FS_CREATE: u32 = 2u;
const FS_DELETE: u32 = 3u;
const FS_LIST: u32 = 4u;

@compute @workgroup_size(128, 1, 1)
fn main( @builtin(global_invocation_id) global_id: vec3<u32>) {
    let thread_id = global_id.x;
    let operations_per_thread = 8u;
    
    // Each thread processes multiple filesystem operations
    for (var i: u32 = 0u; i < operations_per_thread; i = i + 1u) {
        let op_index = thread_id * operations_per_thread + i;
        if (op_index < 1024u) { // OS_MAX_FILE_OPERATIONS
            let operation = &os_fs_operations[op_index];
            
            // Only process pending operations
            if (atomicLoad(&operation.status) == 0u) {
                // Check if this operation is for the filesystem service
                // (Assuming operation.requester_id could pass the service ID)
                // For now, let's process all pending operations here.

                atomicStore(&operation.status, 1u); // PROCESSING
                
                switch (operation.operation_type) {
                    case FS_READ: { handle_file_read(op_index); }
                    case FS_WRITE: { handle_file_write(op_index); }
                    case FS_CREATE: { handle_file_create(op_index); }
                    // Note: DELETE and LIST operations commented out - functions not yet implemented
                    // case FS_DELETE: { handle_file_delete(op_index); }
                    // case FS_LIST: { handle_directory_list(op_index); }
                    default: {
                        atomicStore(&operation.status, 3u); // ERROR - operation not implemented
                        os_trace_debug_log(thread_id, 0u, 0xFFFFu, operation.operation_type, 0u, 0u, 0u);
                    }
                }
            }
        }
    }
}

// File operations
fn handle_file_read(op_index: u32) {
    let operation = &os_fs_operations[op_index];
    let handle_id = operation.file_handle_id;
    if (handle_id >= 1024u) { // OS_MAX_FILE_HANDLES
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let file_handle = &os_fs_file_handles[handle_id];
    let file_id = atomicLoad(&file_handle.file_id);
    let position = atomicLoad(&file_handle.position);
    let mode = atomicLoad(&file_handle.mode);
    
    // Check read permissions
    if ((mode & 1u) == 0u) { // 1u for read bit
        atomicStore(&operation.status, 3u); // ERROR - not readable
        return;
    }
    
    if (file_id >= OS_MAX_FILES) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let file = &os_fs_metadata[file_id];
    let file_size = atomicLoad(&file.size);
    
    // Calculate block information
    let start_offset_in_file = operation.params[0]; // Offset to start reading from file
    let read_size = operation.params[1]; // Size to read
    let result_payload_offset = operation.result_buffer; // Offset in os_payload_buffer for result
    
    // Validate read bounds
    if (start_offset_in_file + read_size > file_size) {
        atomicStore(&operation.status, 3u); // ERROR - read out of bounds
        return;
    }
    
    // Read data blocks
    let blocks_to_read = (read_size + OS_BLOCK_SIZE - 1u) / OS_BLOCK_SIZE;
    
    for (var i: u32 = 0u; i < blocks_to_read; i = i + 1u) {
        let block_idx_in_file = (start_offset_in_file / OS_BLOCK_SIZE) + i;
        if (block_idx_in_file >= 256u) { // Direct block limit
            // Should not happen if file_size is correct
            atomicStore(&operation.status, 3u); // ERROR
            return;
        }
        let block_ptr = atomicLoad(&file.blocks[block_idx_in_file]);
        if (block_ptr == 0xFFFFFFFFu) { // Invalid block pointer
            atomicStore(&operation.status, 3u); // ERROR
            return;
        }

        let block_start_u32_idx = block_ptr * (OS_BLOCK_SIZE / 4u);
        let current_block_offset_u32 = (start_offset_in_file % OS_BLOCK_SIZE) / 4u; // Offset into current block for first read

        let bytes_to_copy_in_block = min(read_size - (i * OS_BLOCK_SIZE), OS_BLOCK_SIZE - (start_offset_in_file % OS_BLOCK_SIZE));
        let u32s_to_copy_in_block = (bytes_to_copy_in_block + 3u) / 4u; // Round up to full u32s

        for (var j: u32 = 0u; j < u32s_to_copy_in_block; j = j + 1u) {
            let src_idx = block_start_u32_idx + current_block_offset_u32 + j;
            let dst_idx = result_payload_offset + (i * (OS_BLOCK_SIZE / 4u)) + j; // Destination in payload buffer

            // Direct access - bounds checked by GPU
            os_payload_buffer[dst_idx] = os_fs_data_blocks[src_idx];
        }
    }
    
    atomicStore(&file_handle.position, position + read_size);
    atomicStore(&file.accessed_time, get_system_time());
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_file_write(op_index: u32) {
    let operation = &os_fs_operations[op_index];
    let handle_id = operation.file_handle_id;
    if (handle_id >= 1024u) { // OS_MAX_FILE_HANDLES
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let file_handle = &os_fs_file_handles[handle_id];
    let file_id = atomicLoad(&file_handle.file_id);
    let position = atomicLoad(&file_handle.position);
    let mode = atomicLoad(&file_handle.mode);
    
    // Check write permissions
    if ((mode & 2u) == 0u) { // 2u for write bit
        atomicStore(&operation.status, 3u); // ERROR - not writable
        return;
    }
    
    if (file_id >= OS_MAX_FILES) {
        atomicStore(&operation.status, 3u); // ERROR
        return;
    }
    
    let file = &os_fs_metadata[file_id];
    var file_size = atomicLoad(&file.size);
    
    // Get write data
    let write_size = operation.params[0]; // Size to write
    let data_payload_offset = operation.params[1]; // Offset in os_payload_buffer for data
    
    // Calculate block information
    let start_offset_in_file = position;
    let end_offset_in_file = position + write_size;

    let start_block_idx = start_offset_in_file / OS_BLOCK_SIZE;
    let end_block_idx = (end_offset_in_file + OS_BLOCK_SIZE - 1u) / OS_BLOCK_SIZE;
    let blocks_needed = end_block_idx - start_block_idx;

    // Allocate blocks if needed
    for (var i: u32 = 0u; i < blocks_needed; i = i + 1u) {
        let current_block_idx_in_file = start_block_idx + i;
        let existing_block_ptr = atomicLoad(&file.blocks[current_block_idx_in_file]);
        
        if (existing_block_ptr == 0xFFFFFFFFu) { // Need to allocate a new block
            let new_block_ptr = allocate_block();
            if (new_block_ptr == 0xFFFFFFFFu) {
                atomicStore(&operation.status, 3u); // ERROR - no space
                return;
            }
            atomicStore(&file.blocks[current_block_idx_in_file], new_block_ptr);
        }
    }
    
    // Write data blocks in parallel
    for (var i: u32 = 0u; i < blocks_needed; i = i + 1u) {
        let current_block_idx_in_file = start_block_idx + i;
        let block_ptr = atomicLoad(&file.blocks[current_block_idx_in_file]);
        
        if (block_ptr < OS_MAX_BLOCKS) {
            let block_start_u32_idx = block_ptr * (OS_BLOCK_SIZE / 4u);
            
            let bytes_to_copy_in_block = min(write_size - (i * OS_BLOCK_SIZE), OS_BLOCK_SIZE);
            let u32s_to_copy_in_block = (bytes_to_copy_in_block + 3u) / 4u;

            let current_write_offset_in_block_u32 = (start_offset_in_file % OS_BLOCK_SIZE) / 4u;

            for (var j: u32 = 0u; j < u32s_to_copy_in_block; j = j + 1u) {
                let src_idx = data_payload_offset + (i * (OS_BLOCK_SIZE / 4u)) + j; // Source from payload buffer
                let dst_idx = block_start_u32_idx + current_write_offset_in_block_u32 + j;

                // Direct access - bounds checked by GPU
                os_fs_data_blocks[dst_idx] = os_payload_buffer[src_idx];
            }
        }
    }
    
    // Update file size and metadata
    atomicStore(&file.size, max(file_size, end_offset_in_file));
    atomicStore(&file.modified_time, get_system_time());
    atomicStore(&file_handle.position, position + write_size);
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

fn handle_file_create(op_index: u32) {
    let operation = &os_fs_operations[op_index];
    let name_hash = operation.params[0];
    let size = operation.params[1];
    let permissions = operation.params[2];
    let is_directory = operation.params[3];
    let owner_shader = operation.requester_id; // requester_id is current thread for now
    
    // Find free file entry
    let file_id = allocate_inode();
    if (file_id == 0xFFFFFFFFu) {
        atomicStore(&operation.status, 3u); // ERROR - no free entries
        return;
    }
    
    // Allocate blocks for file
    let blocks_needed = (size + OS_BLOCK_SIZE - 1u) / OS_BLOCK_SIZE;
    if (blocks_needed > 256u) { // Exceeds direct block limit
        atomicStore(&operation.status, 3u); // ERROR - file too large
        return;
    }

    var allocated_blocks_ptrs: array<u32, 256>;
    for (var i: u32 = 0u; i < blocks_needed; i = i + 1u) {
        let block_ptr = allocate_block();
        if (block_ptr == 0xFFFFFFFFu) {
            // Roll back allocated blocks and inode
            for (var j: u32 = 0u; j < i; j = j + 1u) {
                free_block(allocated_blocks_ptrs[j]);
            }
            free_inode(file_id);
            atomicStore(&operation.status, 3u); // ERROR - no space
            return;
        }
        allocated_blocks_ptrs[i] = block_ptr;
    }
    
    // Initialize file entry
    let file = &os_fs_metadata[file_id];
    atomicStore(&file.size, size);
    for (var i: u32 = 0u; i < blocks_needed; i = i + 1u) {
        atomicStore(&file.blocks[i], allocated_blocks_ptrs[i]);
    }
    for (var i: u32 = blocks_needed; i < 256u; i = i + 1u) {
        atomicStore(&file.blocks[i], 0xFFFFFFFFu); // Mark unused blocks as invalid
    }

    atomicStore(&file.permissions, permissions);
    atomicStore(&file.owner_shader, owner_shader);
    atomicStore(&file.created_time, get_system_time());
    atomicStore(&file.modified_time, get_system_time());
    atomicStore(&file.accessed_time, get_system_time());
    atomicStore(&file.is_directory, is_directory);
    atomicStore(&file.ref_count, 1u);
    
    // Add to directory
    let parent_dir = operation.params[4]; // Parent directory ID
    add_directory_entry(parent_dir, file_id, name_hash, is_directory);
    
    atomicStore(&operation.status, 2u); // COMPLETE
}

// Helper functions for filesystem
fn allocate_block() -> u32 {
    // Atomically find and claim a free block
    for (var i: u32 = 0u; i < OS_MAX_BLOCKS / 32u; i = i + 1u) { // Iterate through u32s in bitmap
        let current_word = atomicLoad(&os_fs_free_blocks_bitmap[i]);
        if (current_word != 0xFFFFFFFFu) { // If not all bits are set (i.e., there's a free block)
            for (var bit_idx: u32 = 0u; bit_idx < 32u; bit_idx = bit_idx + 1u) {
                let mask = 1u << bit_idx;
                if ((current_word & mask) == 0u) { // If this bit is 0 (block is free)
                    let old_word = atomicOr(&os_fs_free_blocks_bitmap[i], mask);
                    if ((old_word & mask) == 0u) { // If we successfully set the bit (claimed the block)
                        return (i * 32u) + bit_idx; // Return the block index
                    }
                }
            }
        }
    }
    return 0xFFFFFFFFu; // No free blocks
}

fn free_block(block_id: u32) {
    if (block_id == 0xFFFFFFFFu || block_id >= OS_MAX_BLOCKS) { return; }
    let word_idx = block_id / 32u;
    let bit_idx = block_id % 32u;
    let mask = 1u << bit_idx;
    atomicAnd(&os_fs_free_blocks_bitmap[word_idx], ~mask); // Clear the bit to free the block
}

fn allocate_inode() -> u32 {
    // Atomically find and claim a free inode
    for (var i: u32 = 0u; i < OS_MAX_FILES / 32u; i = i + 1u) { // Iterate through u32s in bitmap
        let current_word = atomicLoad(&os_fs_free_inodes_bitmap[i]);
        if (current_word != 0xFFFFFFFFu) { // If not all bits are set (i.e., there's a free inode)
            for (var bit_idx: u32 = 0u; bit_idx < 32u; bit_idx = bit_idx + 1u) {
                let mask = 1u << bit_idx;
                if ((current_word & mask) == 0u) { // If this bit is 0 (inode is free)
                    let old_word = atomicOr(&os_fs_free_inodes_bitmap[i], mask);
                    if ((old_word & mask) == 0u) { // If we successfully set the bit (claimed the inode)
                        return (i * 32u) + bit_idx; // Return the inode index
                    }
                }
            }
        }
    }
    return 0xFFFFFFFFu; // No free inodes
}

fn free_inode(inode_id: u32) {
    if (inode_id == 0xFFFFFFFFu || inode_id >= OS_MAX_FILES) { return; }
    let word_idx = inode_id / 32u;
    let bit_idx = inode_id % 32u;
    let mask = 1u << bit_idx;
    atomicAnd(&os_fs_free_inodes_bitmap[word_idx], ~mask); // Clear the bit to free the inode
}
