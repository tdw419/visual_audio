// runtime/services/filesystem_shader.wgsl
// Pure shader-based filesystem - no host I/O!

// --- Core system constants ---
const MAX_FAT_ENTRIES: u32 = 65536u;
const MAX_INODES: u32 = 8192u;
const MAX_DATA_BLOCKS: u32 = 262144u; // 1GB storage (262144 * 4KB blocks)
const INODE_BLOCK_POINTERS: u32 = 256u; // Direct/Indirect block pointers per inode
const MAX_OPEN_FILES: u32 = 1024u;


// --- Data Structures ---

struct FileSystem {
    fat: array<atomic<u32>, MAX_FAT_ENTRIES>,    // File Allocation Table
    inodes: array<Inode, MAX_INODES>,            // File metadata
    free_blocks_bitmap: array<atomic<u32>, MAX_DATA_BLOCKS / 32>, // Bitmap for MAX_DATA_BLOCKS (MAX_DATA_BLOCKS/32 u32s)
    root_directory_inode: atomic<u32>            // Root inode number
}

struct Inode {
    size: atomic<u32>,
    blocks: array<atomic<u32>, INODE_BLOCK_POINTERS>, // Direct/Indirect block pointers
    permissions: atomic<u32>,          // rwx bits
    owner_id: atomic<u32>,
    ctime: atomic<u32>,                // Creation time
    mtime: atomic<u32>,                // Modification time
    inode_type: atomic<u32>            // 0=file, 1=directory, 2=symlink (renamed from 'type')
}

struct FileHandle {
    inode_num: atomic<u32>,
    position: atomic<u32>,
    mode: atomic<u32>,     // 0=read, 1=write, 2=append, 3=create, 4=close
    shader_pid: atomic<u32>, // Owner shader ID
    status: atomic<u32>    // 0=open, 1=closed, 2=error
}


// --- Global Storage Buffers ---

@group(0) @binding(14) var<storage, read_write> filesystem_state: FileSystem; // Bind to index 14
@group(0) @binding(15) var<storage, read_write> fs_data_blocks: array<u32>; // 1GB storage (runtime-sized array)
@group(0) @binding(16) var<storage, read_write> open_files: array<FileHandle, MAX_OPEN_FILES>; // Bind to index 16


// --- Helper Functions (placeholders for now) ---

fn get_system_time() -> u32 {
    // Placeholder for getting system time
    return 0;
}

fn send_data_to_shader(owner_shader: u32, data_ptr: u32, size: u32, op_index: u32) {
    // Placeholder for sending data to a shader's mailbox
}

fn read_from_shared_buffer(op_index: u32, buffer_ptr: u32, size: u32) -> array<u32, 1024> {
    // Placeholder for reading from shared buffer
    return array<u32, 1024>();
}

fn write_data_to_physical_blocks(physical_blocks: array<u32, INODE_BLOCK_POINTERS>, data: array<u32, 1024>, block_offset: u32, write_size: u32) {
    // Placeholder: Write data to the actual data blocks in filesystem_state.data_blocks
}

fn write_data_to_physical_blocks_with_offset(physical_block_num: u32, block_offset: u32, data: array<u32, 1024>, data_start_index: u32, size: u32) {
    // Placeholder to write partial data to a block
}


// --- Filesystem Shader Kernel ---

// Filesystem shader - handles all file operations
@compute @workgroup_size(128, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) { // Changed entry point to main
    let thread_id = global_id.x;
    
    // Each thread handles multiple file operations
    let ops_per_thread = 8u;
    
    for (var i: u32 = 0u; i < ops_per_thread; i = i + 1u) {
        let op_index = thread_id * ops_per_thread + i;
        if (op_index < MAX_OPEN_FILES) { // Max 1024 open file handles
            process_file_operation(op_index);
        }
    }
}

fn process_file_operation(op_index: u32) {
    let file_handle = &open_files[op_index];
    let inode_num = atomicLoad(&file_handle.inode_num);
    
    if (inode_num != 0xFFFFFFFFu) { // Valid handle
        let mode = atomicLoad(&file_handle.mode);
        
        switch (mode) {
            case 0u: { // READ
                handle_file_read(op_index, inode_num);
            }
            case 1u: { // WRITE
                handle_file_write(op_index, inode_num);
            }
            case 2u: { // APPEND
                handle_file_append(op_index, inode_num);
            }
            case 3u: { // CREATE
                handle_file_create(op_index, inode_num);
            }
            case 4u: { // CLOSE
                handle_file_close(op_index, inode_num);
            }
            default: {
                // Unknown operation
            }
        }
    }
}

// Handles a file read operation for a given open file handle.
//
// Parameters:
//   op_index: The index of the file handle in the global `open_files` array.
//   inode_num: The index of the file's inode in the global `filesystem_state.inodes` array.
fn handle_file_read(op_index: u32, inode_num: u32) {
    let file_handle = &open_files[op_index];
    let inode = &filesystem_state.inodes[inode_num];
    let position = atomicLoad(&file_handle.position);
    let file_size = atomicLoad(&inode.size);
    let owner_shader = atomicLoad(&file_handle.shader_pid);

    if (position < file_size) {
        let bytes_to_read = min(file_size - position, 4096u); // Read up to 4KB at a time

        let block_index_in_inode = position / 4096u;
        let block_offset_in_data = position % 4096u;

        let physical_block_num = atomicLoad(&inode.blocks[block_index_in_inode]);

        if (physical_block_num != 0xFFFFFFFFu) {
            // Read data from the data block
            let data_start_index = physical_block_num * 1024u; // 1024 u32s per 4KB block
            var read_data: array<u32, 1024>; // Temporary buffer for 4KB

            for (var i: u32 = 0u; i < bytes_to_read / 4u; i = i + 1u) {
                read_data[i] = fs_data_blocks[data_start_index + (block_offset_in_data / 4u) + i];
            }

            // Send data to the requesting shader (via inter-shader comms)
            send_data_to_shader(owner_shader, 0, bytes_to_read, op_index); // Placeholder data_ptr
            
            // Update position
            atomicStore(&file_handle.position, position + bytes_to_read);
        } else {
            // Error: Invalid block pointer
            atomicStore(&file_handle.status, 2u); // Error status
        }
    } else {
        // End of file
        atomicStore(&file_handle.status, 1u); // Closed status (or EOF)
    }
}

// Handles a file write operation for a given open file handle.
//
// Parameters:
//   op_index: The index of the file handle in the global `open_files` array.
//   inode_num: The index of the file's inode in the global `filesystem_state.inodes` array.
fn handle_file_write(op_index: u32, inode_num: u32) {
    let file_handle = &open_files[op_index];
    let inode = &filesystem_state.inodes[inode_num];
    let position = atomicLoad(&file_handle.position);
    let file_size = atomicLoad(&inode.size);
    
    // Get write data (e.g., from a shared buffer communicated by the owner shader)
    let data_to_write_buf_len = 1024u; // Assuming max 4KB write at a time
    let data_to_write = read_from_shared_buffer(op_index, 0, data_to_write_buf_len); // Placeholder arguments
    let write_size_bytes = data_to_write_buf_len * 4u; // Convert u32 array length to bytes
    
    if (write_size_bytes > 0u) {
        // Calculate blocks needed
        let current_block_index = position / 4096u;
        let num_blocks_for_write = (write_size_bytes + (position % 4096u) + 4095u) / 4096u; // Number of blocks touched by write
        
        var allocated_blocks_for_write: array<u32, INODE_BLOCK_POINTERS>; // Max blocks per inode

        // Allocate new blocks if necessary
        for (var i: u32 = 0u; i < num_blocks_for_write; i = i + 1u) {
            let block_num_in_inode = current_block_index + i;
            if (block_num_in_inode < INODE_BLOCK_POINTERS) { // Check against max block pointers per inode
                var physical_block_num = atomicLoad(&inode.blocks[block_num_in_inode]);
                if (physical_block_num == 0xFFFFFFFFu) { // Need to allocate a new block
                    physical_block_num = allocate_data_block();
                    if (physical_block_num != 0xFFFFFFFFu) {
                        atomicStore(&inode.blocks[block_num_in_inode], physical_block_num);
                    } else {
                        // Error: No free blocks
                        atomicStore(&file_handle.status, 2u); // Error status
                        return;
                    }
                }
                allocated_blocks_for_write[i] = physical_block_num;

                // Write data to the actual data blocks, handling partial block writes
                let offset_in_current_block = (position + i * 4096u) % 4096u;
                let data_offset_in_write_data = (i * 4096u) - (position % 4096u);
                
                write_data_to_physical_blocks_with_offset(physical_block_num, offset_in_current_block, data_to_write, data_offset_in_write_data / 4u, min(4096u - offset_in_current_block, write_size_bytes - (i * 4096u)));
            } else {
                // Error: File too large for direct blocks (need indirect blocks)
                atomicStore(&file_handle.status, 2u); // Error status
                return;
            }
        }
        
        // Update file size and modification time
        atomicStore(&inode.size, max(file_size, position + write_size_bytes));
        atomicStore(&inode.mtime, get_system_time());
        atomicStore(&file_handle.position, position + write_size_bytes);
    }
}

// Handles a file append operation by seeking to the end of the file and writing.
//
// Parameters:
//   op_index: The index of the file handle in the global `open_files` array.
//   inode_num: The index of the file's inode in the global `filesystem_state.inodes` array.
fn handle_file_append(op_index: u32, inode_num: u32) {
    let file_handle = &open_files[op_index];
    let inode = &filesystem_state.inodes[inode_num];
    // Placeholder: Seek to end of file and then write
    atomicStore(&file_handle.position, atomicLoad(&inode.size));
    handle_file_write(op_index, inode_num);
}

// Handles a file creation operation.
//
// Parameters:
//   op_index: The index of the file handle in the global `open_files` array.
//   inode_num: The index of the file's inode in the global `filesystem_state.inodes` array.
fn handle_file_create(op_index: u32, inode_num: u32) {
    let file_handle = &open_files[op_index];
    let inode = &filesystem_state.inodes[inode_num];
    // Placeholder: Initialize a new inode
    // Assign a free inode
    // Initialize inode fields (size=0, permissions, owner, times, type)
    // For now, assume inode is already assigned and initialized.
    atomicStore(&inode.size, 0u);
    atomicStore(&inode.ctime, get_system_time());
    atomicStore(&inode.mtime, get_system_time());
    atomicStore(&inode.inode_type, 0u); // Regular file
    atomicStore(&file_handle.status, 0u); // Open status
}

// Handles a file close operation.
//
// Parameters:
//   op_index: The index of the file handle in the global `open_files` array.
//   inode_num: The index of the file's inode in the global `filesystem_state.inodes` array.
fn handle_file_close(op_index: u32, inode_num: u32) {
    let file_handle = &open_files[op_index];
    let inode = &filesystem_state.inodes[inode_num];
    // Placeholder: Release file handle
    atomicStore(&file_handle.status, 1u); // Closed
    atomicStore(&file_handle.inode_num, 0xFFFFFFFFu); // Mark handle as free
}

fn allocate_data_block() -> u32 {
    // Lock-free block allocation using atomic operations on bitmap
    for (var i: u32 = 0u; i < MAX_DATA_BLOCKS / 32u; i = i + 1u) { // Iterate through u32s in bitmap
        var word = atomicLoad(&filesystem_state.free_blocks_bitmap[i]);
        if (word != 0xFFFFFFFFu) { // Check if there's any free bit in this word
            for (var bit_index: u32 = 0u; bit_index < 32u; bit_index = bit_index + 1u) {
                if ((word & (1u << bit_index)) == 0u) { // Found a free bit
                    // Try to atomically set the bit
                    let old_word = atomicAnd(&filesystem_state.free_blocks_bitmap[i], ~(1u << bit_index));
                    if ((old_word & (1u << bit_index)) == 0u) { // Successfully allocated
                        return i * 32u + bit_index;
                    }
                }
            }
        }
    }
    return 0xFFFFFFFFu; // No free blocks
}