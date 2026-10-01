

// runtime/core/os_abi.wgsl
// Global OS ABI — all shaders must match these bindings.

const OS_MAX_REQUESTS: u32 = 1024u;
const OS_MAX_RESPONSES: u32 = 1024u;
const OS_DEBUG_ENTRIES: u32 = 2048u;
const OS_VM_VRAM_SIZE: u32 = 1024u * 1024u; // 1M u32 = 4MB
const OS_VM_THREADS: u32 = 1024u;

const OS_DISPLAY_WIDTH: u32 = 1920u;
const OS_DISPLAY_HEIGHT: u32 = 1080u;
const OS_FRAMEBUFFER_SIZE: u32 = OS_DISPLAY_WIDTH * OS_DISPLAY_HEIGHT; // Each pixel is a u32 (RGBA)

// ---- Shared structs ----

struct ServiceRequest {
    opcode: u32,
    arg0: u32,
    arg1: u32,
    arg2: u32,
    arg3: u32
}

struct ServiceResponse {
    status: u32,
    value0: u32,
    value1: u32,
    value2: u32
}

struct DebugEntry {
    tid: u32,
    pc: u32,
    code: u32,
    value: u32
}

// VM thread state (very simple for now)
struct VMThreadState {
    pc: u32,
    regs: array<u32, 8>,
    flags: u32,
    is_active: u32
}

// ---- Debug Trace Struct ----
struct DebugTrace {
    thread_id: u32,
    pc: u32,
    opcode: u32,
    // timestamp: u32, // Placeholder, might need a global u64 counter
    data: array<u32, 4> // General purpose data
}
const OS_MAX_DEBUG_TRACES: u32 = 65536u;


// ---- Global bindings (group(0)) ----

// OS service request/response queues
@group(0) @binding(0)
var<storage, read_write> os_service_requests: array<ServiceRequest, OS_MAX_REQUESTS>;

@group(0) @binding(1)
var<storage, read_write> os_service_responses: array<ServiceResponse, OS_MAX_RESPONSES>;

@group(0) @binding(2)
var<storage, read_write> os_payload_buffer: array<u32>; // generic payload region

// Debug log
@group(0) @binding(3)
var<storage, read_write> os_debug_entries: array<DebugEntry, OS_DEBUG_ENTRIES>;

@group(0) @binding(4)
var<storage, read_write> os_debug_index: atomic<u32>;

// VM bytecode + state
@group(0) @binding(5)
var<storage, read> os_vm_bytecode: array<u32>;

@group(0) @binding(6)
var<storage, read_write> os_vm_vram: array<u32, OS_VM_VRAM_SIZE>;

@group(0) @binding(7)
var<storage, read_write> os_vm_threads: array<VMThreadState, OS_VM_THREADS>;

// Global frame + flags
@group(0) @binding(8)
var<storage, read_write> os_frame_counter: atomic<u32>;

const OS_FLAG_PAYLOAD_BUFFER_SIZE_U32: u32 = 0u;

@group(0) @binding(9)
var<storage, read_write> os_system_flags: array<u32, 16>;

// Framebuffer bindings for the Window Compositor
@group(0) @binding(10)
var<storage, read_write> os_compositor_framebuffer: array<u32, OS_FRAMEBUFFER_SIZE>;

@group(0) @binding(11)
var<storage, read_write> os_display_framebuffer: array<u32, OS_FRAMEBUFFER_SIZE>;

// Debug Visualization Bindings
@group(0) @binding(12)
var<storage, read_write> os_debug_traces: array<DebugTrace, OS_MAX_DEBUG_TRACES>;

@group(0) @binding(13)
var<storage, read_write> os_visual_debug_data: array<u32, OS_FRAMEBUFFER_SIZE>;

// ---- Filesystem Service Constants ----
const OS_MAX_FILES = 65536u;
const OS_MAX_BLOCKS = 262144u; // 1GB storage (4KB blocks)
const OS_BLOCK_SIZE = 4096u;
const OS_FILENAME_MAX = 256u;
const OS_MAX_PATH_DEPTH = 32u;

// ---- Filesystem Service Structs ----
struct FileEntry {
    name: array<u32, 8>, // 32 chars max (8 u32s)
    size: atomic<u32>,
    blocks: array<atomic<u32>, 256>, // Direct block pointers
    permissions: atomic<u32>,
    owner_shader: atomic<u32>,
    created_time: atomic<u32>,
    modified_time: atomic<u32>,
    accessed_time: atomic<u32>,
    parent_dir: atomic<u32>,
    is_directory: atomic<u32>,
    ref_count: atomic<u32>
}

struct DirectoryEntry {
    file_id: atomic<u32>,
    name_hash: u32,
    entry_type: u32 // 0=file, 1=directory
}

struct FileHandle {
    file_id: atomic<u32>,
    position: atomic<u32>,
    mode: atomic<u32>, // 0=read, 1=write, 2=append
    owner_shader: atomic<u32>
}

struct FileOperation {
    operation_type: u32, // 0=read, 1=write, 2=create, 3=delete, 4=list
    requester_id: u32,
    file_handle_id: u32,
    params: array<u32, 8>,
    result_buffer: u32, // Pointer to a buffer in os_payload_buffer for result
    status: atomic<u32> // 0=pending, 1=processing, 2=complete, 3=error
}

// ---- Filesystem Service Bindings ----
@group(0) @binding(14)
var<storage, read_write> os_fs_metadata: array<FileEntry, OS_MAX_FILES>;

@group(0) @binding(15)
var<storage, read_write> os_fs_data_blocks: array<u32>; // Runtime-sized array (total size in u32s)

@group(0) @binding(16)
var<storage, read_write> os_fs_directory_entries: array<DirectoryEntry, OS_MAX_FILES>; // Assuming 1:1 with files for now

@group(0) @binding(17)
var<storage, read_write> os_fs_file_handles: array<FileHandle, 1024>;

@group(0) @binding(18)
var<storage, read_write> os_fs_operations: array<FileOperation, 1024>;

@group(0) @binding(19)
var<storage, read_write> os_fs_free_blocks_bitmap: array<atomic<u32>, OS_MAX_BLOCKS / 32u>; // Bitmap of free blocks

@group(0) @binding(20)
var<storage, read_write> os_fs_free_inodes_bitmap: array<atomic<u32>, OS_MAX_FILES / 32u>; // Bitmap of free inodes

// ---- Window System Constants ----
const OS_MAX_WINDOWS = 256u;
const OS_TITLE_MAX_LENGTH = 32u;
const OS_WINDOW_EVENTS_MAX = 1024u;
const OS_MAX_RENDER_COMMANDS = 4096u;

// ---- Window System Structs ----
struct Window {
    id: atomic<u32>,
    x: atomic<u32>,
    y: atomic<u32>,
    width: atomic<u32>,
    height: atomic<u32>,
    title: array<atomic<u32>, 8>, // 32 chars max (8 u32s)
    pixel_buffer_offset: atomic<u32>, // Offset to pixel data in os_payload_buffer
    z_order: atomic<u32>,
    flags: atomic<u32>, // 0x1=visible, 0x2=minimized, 0x4= maximized, 0x8=focused
    owner_shader: atomic<u32>,
    parent_window: atomic<u32>, // For dialog windows
    class_id: atomic<u32> // Window class for styling
}

struct WindowEvent {
    event_type: u32, // 0x1=mouse_click, 0x2=mouse_move, 0x4=key_press, 0x8=key_release, 0x10=resize
    target_window: u32,
    x: u32,
    y: u32,
    button: u32, // Mouse button or key code
    modifiers: u32, // Shift, Ctrl, Alt
    timestamp: u32
}

struct RenderCommand {
    command_type: u32, // 0x1=clear, 0x2=rect, 0x3=text, 0x4=image, 0x5=triangle
    window_id: u32,
    params: array<u32, 8>,
    color: u32, // RGBA packed
    layer: u32
}

// ---- Window System Bindings ----
@group(0) @binding(21)
var<storage, read_write> os_ws_windows: array<Window, OS_MAX_WINDOWS>;

@group(0) @binding(22)
var<storage, read_write> os_ws_events: array<WindowEvent, OS_WINDOW_EVENTS_MAX>;

@group(0) @binding(23)
var<storage, read_write> os_ws_render_commands: array<RenderCommand, OS_MAX_RENDER_COMMANDS>;

@group(0) @binding(24)
var<storage, read_write> os_ws_free_window_ids_bitmap: array<atomic<u32>, OS_MAX_WINDOWS / 32u>; // Bitmap of free window IDs

@group(0) @binding(25)
var<storage, read_write> os_ws_z_order: array<u32, OS_MAX_WINDOWS>; // Sorted by z-order, contains window IDs

@group(0) @binding(26)
var<storage, read_write> os_ws_focused_window: atomic<u32>;

// ---- Networking Constants ----
const OS_MAX_SOCKETS = 1024u;
const OS_MAX_PACKETS = 8192u;
const OS_PACKET_BUFFER_SIZE = 1514u; // MTU + headers
const OS_SOCKET_BACKLOG = 128u;

// ---- Networking Structs ----
struct Socket {
    id: atomic<u32>,
    domain: atomic<u32>, // 0=AF_INET, 1=AF_INET6
    socket_type: atomic<u32>, // 0=SOCK_STREAM, 1=SOCK_DGRAM (renamed from 'type' which is a keyword)
    protocol: atomic<u32>, // 0=IPPROTO_TCP, 1=IPPROTO_UDP
    local_ip: atomic<u32>,
    local_port: atomic<u32>,
    remote_ip: atomic<u32>,
    remote_port: atomic<u32>,
    state: atomic<u32>, // 0=CLOSED, 1=LISTEN, 2=CONNECTING, 3=CONNECTED, 4=DISCONNECTING
    receive_buffer_offset: atomic<u32>, // Offset to packet buffer in os_payload_buffer
    send_buffer_offset: atomic<u32>, // Offset to packet buffer in os_payload_buffer
    receive_buffer_size: atomic<u32>,
    send_buffer_size: atomic<u32>,
    owner_shader: atomic<u32>,
    options: array<atomic<u32>, 8> // Socket options
}

struct Packet {
    src_ip: u32,
    dst_ip: u32,
    src_port: u32,
    dst_port: u32,
    protocol: u32, // 0=TCP, 1=UDP, 2=ICMP
    flags: u32, // TCP flags or UDP options
    sequence: u32, // TCP sequence number
    ack: u32, // TCP acknowledgment
    data_size: u32,
    data: array<u32, 376> // 1504 bytes / 4 bytes per u32
}

struct NetworkOperation {
    operation_type: u32, // 0x1=socket, 0x2=bind, 0x3=listen, 0x4=connect, 0x5=send, 0x6=receive, 0x7=close
    requester_id: u32,
    socket_id: u32,
    params: array<u32, 8>,
    result_buffer: u32, // Pointer to a buffer in os_payload_buffer for result
    status: atomic<u32> // 0=pending, 1=processing, 2=complete, 3=error
}

// ---- Networking Service Bindings ----
@group(0) @binding(27)
var<storage, read_write> os_net_sockets: array<Socket, OS_MAX_SOCKETS>;

@group(0) @binding(28)
var<storage, read_write> os_net_packets: array<Packet, OS_MAX_PACKETS>;

@group(0) @binding(29)
var<storage, read_write> os_net_operations: array<NetworkOperation, 1024>;

@group(0) @binding(30)
var<storage, read_write> os_net_free_socket_ids_bitmap: array<atomic<u32>, OS_MAX_SOCKETS / 32u>; // Bitmap of free socket IDs

@group(0) @binding(31)
var<storage, read_write> os_net_packet_buffers: array<u32>; // Runtime-sized array (dedicated buffer space for each socket)

@group(0) @binding(32)
var<storage, read_write> os_net_connection_table: array<u32, OS_MAX_SOCKETS>; // Connection state tracking, simplified

@group(0) @binding(33)
var<storage, read_write> os_net_routing_table: array<atomic<u32>, 256>; // IP routing table, simplified

@group(0) @binding(34)
var<storage, read_write> os_net_dns_cache: array<u32, 1024>; // DNS cache, simplified

// ---- AI Service Constants ----
const AI_SERVICE_ID: u32 = 7u;

const AI_OP_INFERENCE: u32 = 1u;
const AI_OP_TRAINING_FORWARD: u32 = 2u;
const AI_OP_TRAINING_BACKWARD: u32 = 3u;
const AI_OP_MODEL_LOAD: u32 = 4u;
const AI_OP_MODEL_SAVE: u32 = 5u;

const AI_STATUS_PENDING: u32 = 0u;
const AI_STATUS_SUCCESS: u32 = 1u;
const AI_STATUS_ERROR: u32 = 2u;

const MAX_MODELS: u32 = 16u;
const MAX_LAYERS: u32 = 128u;
const MAX_AI_REQUESTS: u32 = 256u; // Renamed to avoid clash with OS_MAX_REQUESTS
const MAX_WEIGHTS: u32 = 1048576u;  // 1M floats = 4MB
const MAX_LAYER_SIZE: u32 = 2048u;
const MAX_INPUT_SIZE: u32 = 1024u;

// ---- AI Service Structs ----
struct NeuralLayer {
    layer_id: u32,
    input_count: u32,
    output_count: u32,
    activation_type: u32,  // 0=ReLU, 1=Sigmoid, 2=Tanh
    weights_offset: u32,    // Offset in ai_weights buffer
    bias_offset: u32       // Offset in ai_weights buffer
}

struct NeuralNetwork {
    model_id: u32,
    layer_count: u32,
    layers_offset: u32,     // Offset in ai_layers array
    total_parameters: u32,
    input_size: u32,
    output_size: u32
}

struct AIRequest {
    request_id: u32,
    model_id: u32,
    request_type: u32,      // See AI_OP_* constants
    input_buffer_offset: u32,
    output_buffer_offset: u32,
    batch_size: u32,
    status: atomic<u32>    // 0=Pending, 1=Processing, 2=Complete, 3=Error
}

struct AIResult {
    request_id: atomic<u32>,
    status: atomic<u32>,            // 0=Pending, 1=Success, 2=Error
    execution_time: atomic<u32>,    // GPU cycles (for profiling)
    model_id: atomic<u32>,
    output_buffer_offset: atomic<u32> // Where result can be found in payload buffer
}

// ---- AI Service Bindings ----
@group(0) @binding(35)
var<storage, read_write> os_ai_models: array<NeuralNetwork, MAX_MODELS>;

@group(0) @binding(36)
var<storage, read_write> os_ai_layers: array<NeuralLayer, MAX_LAYERS>;

@group(0) @binding(37)
var<storage, read_write> os_ai_requests: array<AIRequest, MAX_AI_REQUESTS>;

@group(0) @binding(38)
var<storage, read_write> os_ai_results: array<AIResult, MAX_AI_REQUESTS>;

@group(0) @binding(39)
var<storage, read_write> os_ai_weights: array<f32, MAX_WEIGHTS>;


// ---- Common helper ----

fn os_debug_log(pc: u32, code: u32, value: u32) {
    let idx = atomicAdd(&os_debug_index, 1u) % OS_DEBUG_ENTRIES;
    os_debug_entries[idx] = DebugEntry(
        idx, pc, code, value
    );
}

fn os_trace_debug_log(thread_id: u32, pc: u32, opcode: u32, data0: u32, data1: u32, data2: u32, data3: u32) {
    let idx = atomicAdd(&os_debug_index, 1u) % OS_MAX_DEBUG_TRACES; // Use os_debug_index as a general trace index
    os_debug_traces[idx] = DebugTrace(
        thread_id,
        pc,
        opcode,
        array<u32, 4>(data0, data1, data2, data3)
    );
}

// ---- AI Helper Functions ----
// Note: WGSL does not allow returning pointers from functions
// Access os_ai_models, os_ai_layers, and os_ai_weights directly instead
// fn get_neural_network(model_id: u32) -> ptr<storage, NeuralNetwork> {
//     return &os_ai_models[model_id];
// }
//
// fn get_neural_layer(layer_id: u32) -> ptr<storage, NeuralLayer> {
//     return &os_ai_layers[layer_id];
// }
//
// fn get_weights_ptr(offset: u32) -> ptr<storage, array<f32, MAX_WEIGHTS>> {
//     return &os_ai_weights; // Return pointer to the entire weights buffer, offset is handled internally
// }

// Activation functions
fn relu(x: f32) -> f32 {
    return select(0.0, x, x > 0.0);
}

fn sigmoid(x: f32) -> f32 {
    return 1.0 / (1.0 + exp(-x));
}

fn tanh_activation(x: f32) -> f32 {
    return tanh(x);
}

// ---- Filesystem Helper Placeholders ----
fn get_system_time() -> u32 {
    // Placeholder: return current frame counter as a simple time approximation
    return atomicLoad(&os_frame_counter);
}

// Placeholder for writing a u32 at a given offset in a generic buffer
// This would ideally operate on a dedicated buffer or payload region
fn os_write_u32(buffer_ptr: u32, value: u32) {
    // For now, assume this writes to os_payload_buffer at 'buffer_ptr' offset
    if (buffer_ptr < arrayLength(&os_payload_buffer)) {
        os_payload_buffer[buffer_ptr] = value;
    }
}

// Placeholder for reading a u32 at a given offset in a generic buffer
fn os_read_u32(buffer_ptr: u32) -> u32 {
    if (buffer_ptr < arrayLength(&os_payload_buffer)) {
        return os_payload_buffer[buffer_ptr];
    }
    return 0u; // Default to 0 if out of bounds
}

fn add_directory_entry(parent_dir_id: u32, file_id: u32, name_hash: u32, is_directory: u32) {
    // Placeholder: find an empty slot in os_fs_directory_entries and add the entry
    for (var i: u32 = 0u; i < OS_MAX_FILES; i = i + 1u) {
        if (atomicLoad(&os_fs_directory_entries[i].file_id) == 0u) { // Assuming 0 is empty
            atomicStore(&os_fs_directory_entries[i].file_id, file_id);
            os_fs_directory_entries[i].name_hash = name_hash;
            os_fs_directory_entries[i].entry_type = is_directory;
            break;
        }
    }
}

// Note: These functions are commented out because FileOperation contains atomic<u32>
// which cannot be passed to functions in WGSL
// fn handle_file_delete(operation: FileOperation) {
//     // Placeholder for file deletion logic
//     os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Log something
// }
//
// fn handle_directory_list(operation: FileOperation) {
//     // Placeholder for directory listing logic
//     os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Log something
// }

fn send_service_response(requester_id: u32, result_data_ptr: u32) {
    // Placeholder: find requester's response slot and write data pointer
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Log something
}

// ---- Window Management Helper Placeholders ----
fn process_window_event(event: WindowEvent) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn handle_mouse_click(event: WindowEvent) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn handle_mouse_move(event: WindowEvent) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn handle_key_press(event: WindowEvent) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn handle_key_release(event: WindowEvent) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn handle_window_resize(event: WindowEvent) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn update_window_state(window_index: u32) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn send_window_event(window_id: u32, event_type: u32, x: u32, y: u32, button_or_key: u32, modifiers: u32) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn allocate_pixel_buffer(size: u32) -> u32 {
    return 0u; // Placeholder
}
fn get_max_z_order() -> u32 {
    return 0u; // Placeholder
}
fn update_z_order_array(window_id: u32, new_z: u32) {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}
fn sort_z_order() {
    os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); // Placeholder
}

// ---- Networking Helper Placeholders ----
// Commented out to avoid conflicts with actual implementations in service shaders
// fn process_tcp_packet(packet: Packet) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn process_udp_packet(packet: Packet) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn process_icmp_packet(packet: Packet) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// Note: These functions are commented out because NetworkOperation contains atomic<u32>
// which cannot be passed to functions in WGSL
// fn handle_socket_create(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_socket_bind(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_socket_listen(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_socket_connect(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_socket_send(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_socket_receive(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_socket_close(operation: NetworkOperation) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// Commented out to avoid conflicts with actual implementations in network service
// fn allocate_socket_id() -> u32 { return 0u; }
// fn allocate_packet_buffer() -> u32 { return 0u; }
// fn find_socket_for_packet(packet: Packet) -> u32 { return 0xFFFFFFFFu; }
// fn make_connection_key(src_ip: u32, src_port: u32, dst_ip: u32, dst_port: u32) -> u32 { return 0u; }
// fn find_connection(key: u32) -> u32 { return 0xFFFFFFFFu; }
// fn handle_new_tcp_connection(packet: Packet, socket_id: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_tcp_data(packet: Packet, socket_id: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn handle_udp_data(packet: Packet, socket_id: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn create_tcp_syn_packet(dst_ip: u32, dst_port: u32, socket_id: u32) -> Packet { return Packet(); }
// fn send_packet_to_network(packet: Packet) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
// fn get_random_sequence() -> u32 { return 0u; }
// fn get_next_sequence(socket_id: u32) -> u32 { return 0u; }
// fn create_data_packet(socket_id: u32, dst_ip: u32, dst_port: u32, data_buffer: u32, data_size: u32) -> Packet { return Packet(); }
// fn os_trigger_network_send(packet_index: u32) { os_trace_debug_log(0u, 0u, 0u, 0u, 0u, 0u, 0u); }
