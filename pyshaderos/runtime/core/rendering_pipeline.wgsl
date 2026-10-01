// runtime/core/rendering_pipeline.wgsl
// Complete rendering pipeline in WGSL - no Python rendering!

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


// Global storage for render queue and framebuffer
@group(0) @binding(8) var<storage, read_write> render_queue: RenderQueue; // Bind to index 8
@group(0) @binding(9) var<storage, read_write> final_framebuffer: array<u32, VRAM_SIZE>; // Bind to index 9
@group(0) @binding(10) var font_texture: texture_2d<f32>; // Bind to index 10


// --- Helper Functions (placeholders) ---

fn unpack_color(color: u32) -> vec4<f32> {
    return vec4<f32>(
        f32(color & 0xFFu) / 255.0,
        f32((color >> 8) & 0xFFu) / 255.0,
        f32((color >> 16) & 0xFFu) / 255.0,
        f32((color >> 24) & 0xFFu) / 255.0
    );
}

fn pack_color(color_f: vec4<f32>) -> u32 {
    let r = u32(color_f.r * 255.0);
    let g = u32(color_f.g * 255.0);
    let b = u32(color_f.b * 255.0);
    let a = u32(color_f.a * 255.0);
    return (a << 24) | (b << 16) | (g << 8) | r;
}

fn point_in_triangle(p: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, p3: vec2<f32>) -> bool {
    // Barycentric coordinate check (placeholder)
    return true;
}

fn read_x86_memory(addr: u32) -> u32 {
    // Placeholder for reading from x86 memory
    return 0;
}


// --- Main Rendering Kernel ---

// Main rendering kernel - processes all render commands
@compute @workgroup_size(256, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) { // Changed entry point to main
    let pixel_index = global_id.x;
    let total_pixels = SCREEN_WIDTH * SCREEN_HEIGHT;
    
    if (pixel_index >= total_pixels) { return; }
    
    let coord = vec2<u32>(pixel_index % SCREEN_WIDTH, pixel_index / SCREEN_WIDTH);
    var final_color = vec4<f32>(0.0, 0.0, 0.0, 1.0); // Start with black
    
    // Process all render commands for this pixel
    let command_count = atomicLoad(&render_queue.command_count);
    
    for (var cmd_index: u32 = 0u; cmd_index < command_count; cmd_index = cmd_index + 1u) {
        let command = render_queue.commands[cmd_index];
        let pixel_color = process_render_command(command, coord);
        
        // Blend based on command type and layer
        final_color = blend_colors(final_color, pixel_color, command);
    }
    
    // Write final color to framebuffer
    final_framebuffer[pixel_index] = pack_color(final_color);
}

fn process_render_command(command: RenderCommand, coord: vec2<u32>) -> vec4<f32> {
    switch (command.command_type) {
        case 0u: { // CLEAR
            return unpack_color(command.params[0]);
        }
        case 1u: { // RECT
            let x = command.params[0];
            let y = command.params[1];
            let width = command.params[2];
            let height = command.params[3];
            let color = unpack_color(command.params[4]);
            
            if (coord.x >= x && coord.x < x + width &&
                coord.y >= y && coord.y < y + height) {
                return color;
            }
        }
        case 2u: { // TRIANGLE
            let p1 = vec2<f32>(f32(command.params[0]), f32(command.params[1]));
            let p2 = vec2<f32>(f32(command.params[2]), f32(command.params[3]));
            let p3 = vec2<f32>(f32(command.params[4]), f32(command.params[5]));
            let color = unpack_color(command.params[6]);
            
            if (point_in_triangle(vec2<f32>(coord), p1, p2, p3)) {
                return color;
            }
        }
        case 3u: { // TEXT
            return render_text(command, coord);
        }
        default: {
            return vec4<f32>(0.0);
        }
    }
    return vec4<f32>(0.0);
}

fn blend_colors(current: vec4<f32>, new: vec4<f32>, command: RenderCommand) -> vec4<f32> {
    // Simple alpha blending for now
    return mix(current, new, new.a);
}

fn render_text(command: RenderCommand, coord: vec2<u32>) -> vec4<f32> {
    let text_x = command.params[0];
    let text_y = command.params[1];
    let font_size = command.params[2]; // Scale factor
    let color = unpack_color(command.params[3]);
    let text_start_addr = command.params[4]; // Pointer to text string
    
    // Calculate character position within the text block
    let char_x_in_text_block = coord.x - text_x;
    let char_y_in_text_block = coord.y - text_y;

    let char_width_scaled = 8u * font_size;
    let char_height_scaled = 16u * font_size;

    if (char_x_in_text_block >= 0u && char_x_in_text_block < char_width_scaled * 256u && // Max 256 chars
        char_y_in_text_block >= 0u && char_y_in_text_block < char_height_scaled) {

        let char_index_in_string = char_x_in_text_block / char_width_scaled;
        
        // This is a placeholder for reading characters from x86 memory
        // and sampling from a font texture.
        // For now, it will draw a colored rectangle for where the text would be
        if (char_index_in_string < 256u) { // Assume max 256 chars
            return color; // Just draw the text color
        }
    }
    
    return vec4<f32>(0.0);
}
