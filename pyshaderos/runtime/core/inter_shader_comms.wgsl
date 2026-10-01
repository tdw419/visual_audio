// runtime/core/inter_shader_comms.wgsl
// Shader-to-shader communication system

// --- Start common_types.wgsl inline ---
// Common data structures and constants shared across all Pixel OS WGSL shaders

// --- Core System Constants ---
const SCREEN_WIDTH: u32 = 1920u;
const SCREEN_HEIGHT: u32 = 1080u;
const VRAM_SIZE: u32 = SCREEN_WIDTH * SCREEN_HEIGHT;
const MAX_PROCESSES: u32 = 256u;
const MAX_MEMORY_PAGES: u32 = 65536u; // Each Page is 4KB, so 256MB total
const MAX_SHADERS: u32 = 64u; // Max number of active shaders/services


// --- Process Management ---
struct Process {
    pid: u32,
    state: u32, // 0=ready, 1=running, 2=blocked, 3=exited
    page_table_ptr: u32, // Pointer to page table in memory_pages buffer
    registers: array<u32, 16>, // x86 registers (EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI, EIP, EFLAGS, etc.)
    priority: u32,
    shader_id: u32 // The ID of the shader executing this process
}

// --- Memory Management ---
struct Page {
    physical_addr: u32, // Physical address of the 4KB page
    permissions: u32,   // R/W/X flags
    owner_pid: u32
}

// --- X86 Emulation State ---
struct X86State {
    // x86 registers (atomic for parallel access)
    eax: atomic<u32>, ebx: atomic<u32>, ecx: atomic<u32>, edx: atomic<u32>,
    esi: atomic<u32>, edi: atomic<u32>, esp: atomic<u32>, ebp: atomic<u32>,
    eip: atomic<u32>, eflags: atomic<u32>,
    
    // Memory and stack (packed into u32s)
    memory: array<u32, 1048576>, // 4MB RAM (1M u32s) for x86 emulator
    stack: array<u32, 65536>,    // 256KB stack (65536 u32s)
    
    // Instruction stream
    instructions: array<u32, 131072>, // 512KB code (131072 u32s)
    instruction_count: atomic<u32>, // Number of u32 instructions
    
    // System call communication buffer
    syscall_buffer: array<u32, 1024>, // Buffer for syscall args/results
    syscall_count: atomic<u32> // Number of pending syscalls
}

// --- Inter-Shader Communication ---
struct AtomicShaderMessage {
    sender: atomic<u32>,
    receiver: atomic<u32>,
    message_type: atomic<u32>,
    data: array<atomic<u32>, 16>, // 16 u32s of data
    sequence: atomic<u32>
}

struct RingBuffer {
    messages: array<AtomicShaderMessage, 1024>, // Max 1024 messages
    head: atomic<u32>,
    tail: atomic<u32>,
    capacity: atomic<u32>
}

struct ShaderMailbox {
    inbox: RingBuffer,
    outbox: RingBuffer,
    shader_id: atomic<u32>,
    priority: atomic<u32>
}

// --- Rendering Pipeline ---
struct RenderCommand {
    command_type: u32, // 0=clear, 1=rect, 2=triangle, 3=text, 4=image
    params: array<u32, 16>, // General purpose parameters
    layer: u32,
    shader_id: u32 // Shader that issued the command
}

struct RenderQueue {
    commands: array<RenderCommand, 4096>, // Max 4096 commands per frame
    command_count: atomic<u32>,
    layers: array<u32, 32>, // Z-ordering layers
    current_frame: atomic<u32> // Current frame number
}

// --- Networking ---
const MAX_PACKETS: u32 = 8192u;
const MAX_SOCKETS: u32 = 1024u;
const MAX_ROUTES: u32 = 256u;
const MAX_DNS_ENTRIES: u32 = 1024u;
const PACKET_DATA_SIZE_U32: u32 = 1536u / 4u; // 1536 bytes max (384 u32s)

struct Packet {
    data: array<atomic<u32>, PACKET_DATA_SIZE_U32>, // Raw packet data (packed u32s)
    size_bytes: atomic<u32>, // Actual size in bytes
    protocol: atomic<u32>,             // 0=TCP, 1=UDP, 2=ICMP (u32 for simplicity)
    src_ip: atomic<u32>,
    dst_ip: atomic<u32>,
    src_port: atomic<u32>,
    dst_port: atomic<u32>,
    flags: atomic<u32>,
    timestamp: atomic<u32>
}

struct Socket {
    protocol: atomic<u32>,
    local_ip: atomic<u32>,
    local_port: atomic<u32>,
    remote_ip: atomic<u32>,
    remote_port: atomic<u32>,
    state: atomic<u32>,       // 0=closed, 1=listening, 2=connected (u32 for simplicity)
    receive_buffer: array<atomic<u32>, 65536 / 4>, // 64KB receive buffer (u32s)
    send_buffer: array<atomic<u32>, 65536 / 4>,    // 64KB send buffer (u32s)
    owner_shader: atomic<u32>,
    mailbox_slot: atomic<u32>
}

struct Route {
    network: atomic<u32>,
    netmask: atomic<u32>,
    gateway: atomic<u32>,
    interface: atomic<u32> // u32 for simplicity
}

struct DNSEntry {
    hostname_addr: u32, // Pointer to hostname string in shared memory (packed u32s)
    ip_address: atomic<u32>,
    ttl: atomic<u32>
}

struct NetworkPortal {
    packets: array<Packet, MAX_PACKETS>,
    packet_count: atomic<u32>,
    sockets: array<Socket, MAX_SOCKETS>,
    routing_table: array<Route, MAX_ROUTES>,
    dns_cache: array<DNSEntry, MAX_DNS_ENTRIES>,
    portal_state: atomic<u32>
}

struct NetworkServiceDescriptor {
    service_id: atomic<u32>,
    shader_bindings: array<u32, 8>,
    packet_handlers: array<u32, 16>,
    encryption_keys: array<u32, 16>, // 16 u32s for encryption keys
    portal_active: atomic<u32>
}

// --- Filesystem ---
const MAX_FAT_ENTRIES: u32 = 65536u; // 256MB FAT
const MAX_INODES: u32 = 8192u;       // Max 8192 files/directories
const MAX_DATA_BLOCKS: u32 = 262144u; // 1GB storage (262144 * 4KB blocks)
const INODE_BLOCK_POINTERS: u32 = 256u; // Direct/Indirect block pointers per inode
const MAX_OPEN_FILES: u32 = 1024u;   // Max 1024 open file handles

struct FileSystem {
    fat: array<atomic<u32>, MAX_FAT_ENTRIES>,    // File Allocation Table
    inodes: array<Inode, MAX_INODES>,            // File metadata
    data_blocks: array<u32, MAX_DATA_BLOCKS * 1024>, // 1GB storage (u32 array, 1024 u32s per 4KB block)
    free_blocks_bitmap: array<atomic<u32>, MAX_DATA_BLOCKS / 32>, // Bitmap for MAX_DATA_BLOCKS (MAX_DATA_BLOCKS/32 u32s)
    root_directory_inode: atomic<u32>            // Root inode number
}

struct Inode {
    size: atomic<u32>,
    blocks: array<atomic<u32>, INODE_BLOCK_POINTERS>, // Direct/Indirect block pointers
    permissions: atomic<u32>,          // rwx bits
    owner_id: atomic<u32>,
    ctime: atomic<u32>,                // Creation time
    mtime: atomic<u32>,                // Modification time    type: atomic<u32>                  // 0=file, 1=directory, 2=symlink
}

struct FileHandle {
    inode_num: atomic<u32>,
    position: atomic<u32>,
    mode: atomic<u32>,     // 0=read, 1=write, 2=append, 3=create, 4=close
    shader_pid: atomic<u32>, // Owner shader ID
    status: atomic<u32>    // 0=open, 1=closed, 2=error
}
// --- End common_types.wgsl inline ---


// --- Global Storage Buffers ---

// Global storage for mailboxes and shared atomic buffer
@group(0) @binding(6) var<storage, read_write> shader_mailboxes: array<ShaderMailbox, MAX_SHADERS>; // Bind to index 6
@group(0) @binding(7) var<storage, read_write> shared_atomic_buffer: array<atomic<u32>, 131072>; // Bind to index 7


// --- Helper Functions (placeholders) ---

fn deliver_atomic_message(message: AtomicShaderMessage) { }
fn route_message_to_handler(msg_type: u32, message: AtomicShaderMessage) { }
fn execute_x86_shader_call(function_id: u32, message: AtomicShaderMessage) { }
fn execute_filesystem_call(function_id: u32, message: AtomicShaderMessage) { }
fn execute_network_call(function_id: u32, message: AtomicShaderMessage) { }
fn trigger_x86_interrupt(irq_num: u32, data: u32) { }
fn pack_mouse_data(data: array<u32, 16>) -> u32 { return 0; } // Changed to u32 array for data
fn create_service_message(msg_type: u32, target_shader: u32, data: array<u32, 16>) -> AtomicShaderMessage {
    return AtomicShaderMessage(atomic<u32>(0), atomic<u32>(target_shader), atomic<u32>(msg_type), array<atomic<u32>, 16>(data), atomic<u32>(0)); // Dummy sender/sequence, convert data to array of atomic
}
fn deliver_to_mailbox(receiver_id: u32, message: AtomicShaderMessage) { } // Placeholder


// --- Main Router Kernel ---

// Optimized message router - zero contention
@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) { // Changed entry point to main
    let router_id = global_id.x;
    // let total_routers = 64u; // Not used directly, can be derived from workgroup_size
    
    // Each router handles a slice of mailboxes
    let mailboxes_per_router = MAX_SHADERS / 64u; // Assuming workgroup_size is 64
    let start_mailbox = router_id * mailboxes_per_router;
    
    for (var i: u32 = 0u; i < mailboxes_per_router; i = i + 1u) {
        let mailbox_id = start_mailbox + i;
        if (mailbox_id < MAX_SHADERS) { // Max 64 shaders
            process_mailbox(mailbox_id);
        }
    }
}

// Processes all messages in the inbox and outbox for a given mailbox.
//
// Parameters:
//   mailbox_id: The index of the shader mailbox to process.
fn process_mailbox(mailbox_id: u32) {
    // Process inbox (messages to this shader)
    process_inbox(mailbox_id);
    
    // Process outbox (messages from this shader)  
    process_outbox(mailbox_id);
}

// Processes incoming messages for a specific shader's mailbox.
//
// Parameters:
//   mailbox_id: The index of the mailbox whose inbox should be processed.
fn process_inbox(mailbox_id: u32) {
    let inbox = &shader_mailboxes[mailbox_id].inbox;
    let head = atomicLoad(&inbox.head);
    let tail = atomicLoad(&inbox.tail);
    
    if (head != tail) {
        // We have messages to deliver
        let message = inbox.messages[tail];
        let receiver = atomicLoad(&message.receiver);
        
        if (receiver == mailbox_id) {
            // This message is for us - deliver immediately
            deliver_atomic_message(message);
            
            // Advance tail (only this router touches this mailbox)
            atomicStore(&inbox.tail, (tail + 1u) % 1024u);
        }
    }
}

// Processes outgoing messages from a specific shader's mailbox.
//
// Parameters:
//   mailbox_id: The index of the mailbox whose outbox should be processed.
fn process_outbox(mailbox_id: u32) {
    let outbox = &shader_mailboxes[mailbox_id].outbox;
    // Placeholder for processing outgoing messages from this shader
}

fn handle_inter_shader_call(message: AtomicShaderMessage, sender: u32) {
    // Shader can "call" another shader directly
    let target_shader = atomicLoad(&message.data[0]);
    let function_id = atomicLoad(&message.data[1]);
    
    // Execute cross-shader call
    switch (target_shader) {
        case 1u: { // X86_EMULATOR_SHADER
            execute_x86_shader_call(function_id, message);
        }
        case 2u: { // FILESYSTEM_SHADER  
            execute_filesystem_call(function_id, message);
        }
        case 3u: { // NETWORK_SHADER
            execute_network_call(function_id, message);
        }
        default: {
            // Unhandled target shader
        }
    }
}
