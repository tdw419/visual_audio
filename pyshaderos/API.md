# ShaderOS API Reference

Complete API documentation for ShaderOS services and runtime interfaces.

## Table of Contents

- [Host Runtime API](#host-runtime-api)
- [Shader Service API](#shader-service-api)
- [Debug API](#debug-api)
- [Buffer Structures](#buffer-structures)

## Host Runtime API

### ShaderOSRuntime Class

Main runtime class that manages GPU resources and shader execution.

#### Constructor

```python
runtime = ShaderOSRuntime()
```

Initializes the ShaderOS runtime:
- Creates WebGPU device
- Allocates all 40 global buffers
- Sets up bind group layouts
- Initializes service handlers

**Returns:** `ShaderOSRuntime` instance

**Example:**
```python
from ShaderOSRuntime import ShaderOSRuntime

runtime = ShaderOSRuntime()
print("Runtime initialized with", len(runtime.shared_buffers), "buffers")
```

---

#### register_shader()

```python
runtime.register_shader(
    shader_id: int,
    name: str,
    shader_path: str,
    entry_point: str = "main"
)
```

Compiles and registers a compute shader.

**Parameters:**
- `shader_id` (int): Unique identifier for this shader (0-255)
- `name` (str): Human-readable shader name
- `shader_path` (str): Path to .wgsl shader file
- `entry_point` (str): Entry point function name (default: "main")

**Returns:** None

**Raises:**
- `FileNotFoundError`: If shader file doesn't exist
- `GPUValidationError`: If shader compilation fails

**Example:**
```python
runtime.register_shader(
    shader_id=0,
    name="substrate",
    shader_path="runtime/core/substrate.wgsl",
    entry_point="main"
)
```

---

#### dispatch_shader()

```python
runtime.dispatch_shader(
    shader_id: int,
    workgroups_x: int = 1,
    workgroups_y: int = 1,
    workgroups_z: int = 1
)
```

Dispatches a registered shader for execution.

**Parameters:**
- `shader_id` (int): ID of shader to dispatch
- `workgroups_x` (int): Number of workgroups in X dimension
- `workgroups_y` (int): Number of workgroups in Y dimension
- `workgroups_z` (int): Number of workgroups in Z dimension

**Total Threads:** `workgroups_x × workgroups_y × workgroups_z × workgroup_size`

**Returns:** None

**Example:**
```python
# Dispatch with 1 workgroup (64 threads total)
runtime.dispatch_shader(0)

# Dispatch with 16x16 workgroups (16,384 threads total)
runtime.dispatch_shader(0, workgroups_x=16, workgroups_y=16)
```

---

#### tick()

```python
runtime.tick()
```

Executes one frame of the ShaderOS runtime:
1. Dispatches all active shaders
2. Reads service requests from GPU
3. Processes requests via service handlers
4. Writes responses back to GPU

**Returns:** None

**Example:**
```python
import time

for frame in range(60):
    runtime.tick()
    time.sleep(1/60)  # 60 FPS
```

---

#### read_debug_log()

```python
runtime.read_debug_log()
```

Reads and displays debug log entries from GPU.

**Output Format:**
```
--- SHADER DEBUG LOG ---
  [000] Code: 0xdead, Args: (0x00000001, 0x00000000, 0x00000000)
  [001] Code: 0xbeef, Args: (0x00000042, 0x00000013, 0x00000000)
------------------------
```

**Side Effects:**
- Clears GPU debug buffers after reading
- Resets debug_index to 0

**Example:**
```python
runtime.tick()
runtime.read_debug_log()
```

---

#### read_service_requests()

```python
runtime.read_service_requests() -> List[Tuple[int, int, int, int, int, int]]
```

Reads pending service requests from GPU.

**Returns:** List of tuples, each containing:
- `request_id` (int): Request identifier
- `service_id` (int): Target service ID
- `opcode` (int): Operation code
- `arg0` (int): First argument
- `arg1` (int): Second argument
- `arg2` (int): Third argument

**Example:**
```python
requests = runtime.read_service_requests()
for req_id, svc_id, opcode, arg0, arg1, arg2 in requests:
    print(f"Request {req_id} to service {svc_id}: op={opcode}")
```

---

#### write_service_response()

```python
runtime.write_service_response(
    request_id: int,
    status: int,
    value0: int = 0,
    value1: int = 0,
    value2: int = 0
)
```

Writes a service response back to GPU.

**Parameters:**
- `request_id` (int): Request being responded to
- `status` (int): Response status (0=pending, 1=success, 2=error)
- `value0` (int): First return value
- `value1` (int): Second return value
- `value2` (int): Third return value

**Example:**
```python
# Success response with return value
runtime.write_service_response(
    request_id=0,
    status=1,      # Success
    value0=42,     # Return value
    value1=0,
    value2=0
)

# Error response
runtime.write_service_response(
    request_id=1,
    status=2,      # Error
    value0=404,    # Error code
)
```

---

### Service Handler Functions

#### handle_filesystem()

```python
runtime.handle_filesystem(request_id: int, opcode: int, args: Tuple[int, ...])
```

Handles filesystem service requests.

**Opcodes:**
- `0`: Read file
- `1`: Write file
- `2`: Create file
- `3`: Delete file
- `4`: List directory

**Example:**
```python
# Override default handler
def custom_fs_handler(req_id, opcode, args):
    if opcode == 0:  # Read
        # Custom read logic
        pass

runtime.service_handlers[1] = custom_fs_handler
```

---

#### handle_network()

```python
runtime.handle_network(request_id: int, opcode: int, args: Tuple[int, ...])
```

Handles network service requests.

**Opcodes:**
- `0`: Create socket
- `1`: Bind socket
- `2`: Listen
- `3`: Connect
- `4`: Send data
- `5`: Receive data
- `6`: Close socket

---

#### handle_reload()

```python
runtime.handle_reload(request_id: int, opcode: int, args: Tuple[int, ...])
```

Handles hot shader reload requests.

**Opcodes:**
- `0`: Reload shader by ID
- `1`: Reload all shaders

---

## Shader Service API

### Debug Functions

#### os_debug_log()

```wgsl
fn os_debug_log(pc: u32, code: u32, value: u32)
```

Logs a debug entry to the simple debug buffer.

**Parameters:**
- `pc`: Program counter or line number
- `code`: Debug code (user-defined)
- `value`: Debug value

**Capacity:** 2,048 entries (wraps around)

**Example:**
```wgsl
os_debug_log(0u, 0xDEADu, thread_id);
```

---

#### os_trace_debug_log()

```wgsl
fn os_trace_debug_log(
    thread_id: u32,
    pc: u32,
    opcode: u32,
    data0: u32,
    data1: u32,
    data2: u32,
    data3: u32
)
```

Logs an advanced debug trace with timestamp.

**Parameters:**
- `thread_id`: Thread identifier
- `pc`: Program counter
- `opcode`: Operation code
- `data0-3`: Four data values

**Capacity:** 65,536 traces (wraps around)

**Auto-captured:**
- Frame number (from os_frame_counter)

**Example:**
```wgsl
let tid = gid.x;
os_trace_debug_log(
    tid,           // thread ID
    0u,            // PC
    0xBEEFu,       // opcode
    result,        // data0
    status,        // data1
    0u,            // data2
    0u             // data3
);
```

---

### Service Request Functions

#### Requesting Services

```wgsl
// Access service request buffer
let req_idx = 0u;
os_service_requests[req_idx].opcode = 1u;      // Read file
os_service_requests[req_idx].arg0 = file_id;
os_service_requests[req_idx].arg1 = offset;
os_service_requests[req_idx].arg2 = length;
```

#### Reading Responses

```wgsl
// Check response status
let resp_idx = 0u;
let status = os_service_responses[resp_idx].status;

if (status == 1u) {  // Success
    let value = os_service_responses[resp_idx].value0;
    // Process result
}
```

---

### Helper Functions

#### get_system_time()

```wgsl
fn get_system_time() -> u32
```

Returns current system time (frame counter).

**Returns:** Current frame number

**Example:**
```wgsl
let timestamp = get_system_time();
```

---

#### Activation Functions (AI)

```wgsl
fn relu(x: f32) -> f32
fn sigmoid(x: f32) -> f32
fn tanh_activation(x: f32) -> f32
```

Neural network activation functions.

**Example:**
```wgsl
let activated = relu(-5.0);  // Returns 0.0
let sig = sigmoid(0.0);      // Returns 0.5
```

---

## Buffer Structures

### Core Structures

#### ServiceRequest

```wgsl
struct ServiceRequest {
    opcode: u32,
    arg0: u32,
    arg1: u32,
    arg2: u32,
    arg3: u32,
}
```

**Size:** 20 bytes
**Capacity:** 256 requests

---

#### ServiceResponse

```wgsl
struct ServiceResponse {
    status: u32,   // 0=pending, 1=success, 2=error
    value0: u32,
    value1: u32,
    value2: u32,
}
```

**Size:** 16 bytes
**Capacity:** 256 responses

---

#### DebugEntry

```wgsl
struct DebugEntry {
    tid: u32,
    pc: u32,
    code: u32,
    value: u32,
}
```

**Size:** 16 bytes
**Capacity:** 2,048 entries

---

#### DebugTrace

```wgsl
struct DebugTrace {
    thread_id: u32,
    pc: u32,
    opcode: u32,
    timestamp: u32,
    data: array<u32, 4>,
}
```

**Size:** 32 bytes
**Capacity:** 65,536 traces

---

### Filesystem Structures

#### FileEntry

```wgsl
struct FileEntry {
    name: array<u32, 8>,           // 32 chars (UTF-32)
    size: atomic<u32>,
    blocks: array<atomic<u32>, 256>,
    permissions: atomic<u32>,
    owner_shader: atomic<u32>,
    created_time: atomic<u32>,
    modified_time: atomic<u32>,
    accessed_time: atomic<u32>,
    parent_dir: atomic<u32>,
    is_directory: atomic<u32>,
    ref_count: atomic<u32>,
}
```

**Size:** ~1,088 bytes
**Capacity:** 65,536 files

**Field Details:**
- `name`: UTF-32 encoded filename (8 u32s = 32 chars)
- `blocks`: Direct block pointers (256 × 4KB = 1MB max file size)
- `permissions`: Unix-style permission bits
- `owner_shader`: Shader ID that created the file

---

#### FileOperation

```wgsl
struct FileOperation {
    operation_type: u32,  // 0=read, 1=write, 2=create, 3=delete, 4=list
    requester_id: u32,
    file_handle_id: u32,
    params: array<u32, 8>,
    result_buffer: u32,
    status: atomic<u32>,
}
```

**Size:** 48 bytes
**Capacity:** 1,024 operations

---

### Window System Structures

#### Window

```wgsl
struct Window {
    id: atomic<u32>,
    x: atomic<u32>,
    y: atomic<u32>,
    width: atomic<u32>,
    height: atomic<u32>,
    title: array<atomic<u32>, 8>,
    pixel_buffer_offset: atomic<u32>,
    z_order: atomic<u32>,
    flags: atomic<u32>,
    owner_shader: atomic<u32>,
    parent_window: atomic<u32>,
    class_id: atomic<u32>,
}
```

**Size:** ~64 bytes
**Capacity:** 256 windows

**Flags:**
- `0x1`: Visible
- `0x2`: Minimized
- `0x4`: Maximized
- `0x8`: Focused

---

#### WindowEvent

```wgsl
struct WindowEvent {
    event_type: u32,     // See event types below
    target_window: u32,
    x: u32,
    y: u32,
    button: u32,
    modifiers: u32,
    timestamp: u32,
}
```

**Size:** 32 bytes
**Capacity:** 1,024 events

**Event Types:**
- `0x1`: Mouse click
- `0x2`: Mouse move
- `0x4`: Key press
- `0x8`: Key release
- `0x10`: Resize

---

### Network Structures

#### Socket

```wgsl
struct Socket {
    id: atomic<u32>,
    domain: atomic<u32>,
    socket_type: atomic<u32>,
    protocol: atomic<u32>,
    local_ip: atomic<u32>,
    local_port: atomic<u32>,
    remote_ip: atomic<u32>,
    remote_port: atomic<u32>,
    state: atomic<u32>,
    receive_buffer_offset: atomic<u32>,
    send_buffer_offset: atomic<u32>,
    receive_buffer_size: atomic<u32>,
    send_buffer_size: atomic<u32>,
    owner_shader: atomic<u32>,
    options: array<atomic<u32>, 8>,
}
```

**Size:** ~72 bytes
**Capacity:** 1,024 sockets

**States:**
- `0`: CLOSED
- `1`: LISTEN
- `2`: CONNECTING
- `3`: CONNECTED
- `4`: DISCONNECTING

---

#### Packet

```wgsl
struct Packet {
    src_ip: u32,
    dst_ip: u32,
    src_port: u32,
    dst_port: u32,
    protocol: u32,
    flags: u32,
    sequence: u32,
    ack: u32,
    data_size: u32,
    data: array<u32, 376>,  // 1504 bytes
}
```

**Size:** ~1,512 bytes
**Capacity:** 8,192 packets

---

### AI Structures

#### NeuralNetwork

```wgsl
struct NeuralNetwork {
    model_id: u32,
    layer_count: u32,
    layers_offset: u32,
    total_parameters: u32,
    input_size: u32,
    output_size: u32,
}
```

**Size:** 24 bytes
**Capacity:** 16 models

---

#### NeuralLayer

```wgsl
struct NeuralLayer {
    layer_id: u32,
    input_count: u32,
    output_count: u32,
    activation_type: u32,  // 0=ReLU, 1=Sigmoid, 2=Tanh
    weights_offset: u32,
    bias_offset: u32,
}
```

**Size:** 24 bytes
**Capacity:** 128 layers

---

#### AIRequest

```wgsl
struct AIRequest {
    request_id: u32,
    model_id: u32,
    request_type: u32,
    input_buffer_offset: u32,
    output_buffer_offset: u32,
    batch_size: u32,
    status: atomic<u32>,
}
```

**Size:** 28 bytes
**Capacity:** 256 requests

**Request Types:**
- `1`: Inference
- `2`: Training forward pass
- `3`: Training backward pass
- `4`: Model load
- `5`: Model save

---

## Constants Reference

### Filesystem

```wgsl
const OS_MAX_FILES = 65536u;
const OS_MAX_BLOCKS = 262144u;
const OS_BLOCK_SIZE = 4096u;
const OS_FILENAME_MAX = 256u;
const OS_MAX_PATH_DEPTH = 32u;
```

### Display

```wgsl
const OS_DISPLAY_WIDTH: u32 = 1920u;
const OS_DISPLAY_HEIGHT: u32 = 1080u;
const OS_FRAMEBUFFER_SIZE: u32 = 1920u * 1080u;
```

### Window System

```wgsl
const OS_MAX_WINDOWS = 256u;
const OS_WINDOW_EVENTS_MAX = 1024u;
const OS_MAX_RENDER_COMMANDS = 4096u;
```

### Networking

```wgsl
const OS_MAX_SOCKETS = 1024u;
const OS_MAX_PACKETS = 8192u;
const OS_PACKET_BUFFER_SIZE = 1514u;
```

### AI Service

```wgsl
const MAX_MODELS: u32 = 16u;
const MAX_LAYERS: u32 = 128u;
const MAX_AI_REQUESTS: u32 = 256u;
const MAX_WEIGHTS: u32 = 1048576u;
const MAX_LAYER_SIZE: u32 = 2048u;
```

---

## Error Codes

### Service Status Codes

| Code | Name    | Description              |
|------|---------|--------------------------|
| 0    | PENDING | Request not processed    |
| 1    | SUCCESS | Operation successful     |
| 2    | ERROR   | Operation failed         |

### Common Error Values (in value0)

| Code | Name              | Description                |
|------|-------------------|----------------------------|
| 1    | INVALID_PARAM     | Invalid parameter          |
| 2    | NOT_FOUND         | Resource not found         |
| 3    | PERMISSION_DENIED | Access denied              |
| 4    | OUT_OF_MEMORY     | Insufficient memory        |
| 5    | ALREADY_EXISTS    | Resource already exists    |
| 6    | IO_ERROR          | I/O error occurred         |

---

**API Version:** 1.0
**Last Updated:** November 2025
