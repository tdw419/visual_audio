# ShaderOS Architecture

## Overview

ShaderOS implements a complete operating system abstraction layer on the GPU using WebGPU compute shaders. This document describes the technical architecture, design decisions, and implementation details.

## Design Philosophy

### GPU-First Architecture

Traditional OS: `CPU (kernel) → GPU (peripheral)`
ShaderOS: `GPU (kernel) → CPU (privileged host)`

**Key Principles:**
1. **GPU as Primary Compute** - All OS logic runs in compute shaders
2. **CPU as Privileged Host** - CPU mediates hardware access only
3. **Shared Memory Model** - WebGPU storage buffers for IPC
4. **Service-Oriented** - Modular services with defined ABIs

## System Layers

### Layer 1: Host Runtime (CPU)

**File**: `ShaderOSRuntime.py`

The host runtime provides:
- Buffer allocation and management
- Shader compilation and dispatch
- Service request/response handling
- Debug output collection

```python
class ShaderOSRuntime:
    def __init__(self):
        self.device = wgpu.utils.get_default_device()
        self.shared_buffers = self._create_shared_buffers()
        self.shader_registry = {}
        self.service_handlers = {}

    def tick(self):
        # 1. Dispatch all active shaders
        # 2. Read service requests from GPU
        # 3. Process requests via handlers
        # 4. Write responses back to GPU
```

**Responsibilities:**
- One-time GPU buffer allocation
- Shader module creation and pipeline setup
- Command encoding and submission
- Buffer read/write for host-GPU communication

### Layer 2: Substrate Kernel (GPU)

**File**: `runtime/core/substrate.wgsl`

The substrate kernel is the minimal "boot" shader that:
- Increments global frame counter atomically
- Logs frame transitions to debug buffer
- Provides execution context for other shaders

```wgsl
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    if (gid.x == 0u) {
        let frame = atomicAdd(&os_frame_counter, 1u);
        os_trace_debug_log(gid.x, 0u, 0xDEADu, frame, 0u, 0u, 0u);
    }
}
```

### Layer 3: OS ABI (GPU)

**File**: `runtime/core/os_abi.wgsl`

Defines the complete OS interface:
- 40 global buffer bindings
- Service request/response structures
- System constants and limits
- Helper functions for common operations

## Buffer Architecture

### Global Buffer Layout

All buffers are bound to `@group(0)` with sequential bindings:

#### Core Buffers (0-9)

| Binding | Name                  | Size    | Purpose                      |
|---------|-----------------------|---------|------------------------------|
| 0       | service_requests      | 9KB     | Host→Shader service calls    |
| 1       | service_responses     | 6KB     | Shader→Host responses        |
| 2       | payload_buffer        | 4MB     | General data payload         |
| 3       | debug_log             | 16KB    | Debug entries (4 u32s each)  |
| 4       | debug_index           | 4B      | Atomic debug counter         |
| 5       | bytecode_program      | 4MB     | VM bytecode                  |
| 6       | vm_vram               | 8MB     | VM video memory              |
| 7       | vm_thread_state       | 768B    | VM thread contexts           |
| 8       | global_frame_counter  | 4B      | Atomic frame counter         |
| 9       | system_flags          | 4B      | Global state flags           |

#### Framebuffer Buffers (10-13)

| Binding | Name                    | Size    | Purpose                    |
|---------|-------------------------|---------|----------------------------|
| 10      | compositor_framebuffer  | 8.3MB   | 1920x1080 RGBA compositor  |
| 11      | display_framebuffer     | 8.3MB   | 1920x1080 RGBA display     |
| 12      | debug_traces            | 2.1MB   | 65K debug trace entries    |
| 13      | visual_debug_data       | 8.3MB   | Debug visualization        |

#### Filesystem Buffers (14-20)

| Binding | Name                  | Size    | Purpose                        |
|---------|-----------------------|---------|--------------------------------|
| 14      | fs_metadata           | 71MB    | 65K file entries               |
| 15      | fs_data_blocks        | 256MB   | Data storage blocks            |
| 16      | fs_directory_entries  | 768KB   | Directory structure            |
| 17      | fs_file_handles       | 16KB    | Open file handles              |
| 18      | fs_operations         | 48KB    | Pending file operations        |
| 19      | fs_free_blocks_bitmap | 32KB    | Free block tracking            |
| 20      | fs_free_inodes_bitmap | 8KB     | Free inode tracking            |

#### Window System Buffers (21-26)

| Binding | Name                      | Size   | Purpose                  |
|---------|---------------------------|--------|--------------------------|
| 21      | ws_windows                | 16KB   | 256 window structures    |
| 22      | ws_events                 | 32KB   | Window event queue       |
| 23      | ws_render_commands        | 192KB  | Render command buffer    |
| 24      | ws_free_window_ids_bitmap | 32B    | Free window ID tracking  |
| 25      | ws_z_order                | 1KB    | Z-order sorted IDs       |
| 26      | ws_focused_window         | 4B     | Currently focused window |

#### Network Buffers (27-34)

| Binding | Name                      | Size   | Purpose                    |
|---------|---------------------------|--------|----------------------------|
| 27      | net_sockets               | 72KB   | 1024 socket structures     |
| 28      | net_packets               | 12MB   | 8192 packet buffers        |
| 29      | net_operations            | 48KB   | Network operation queue    |
| 30      | net_free_socket_ids_bitmap| 128B   | Free socket tracking       |
| 31      | net_packet_buffers        | 1.5MB  | Dedicated packet space     |
| 32      | net_connection_table      | 4KB    | Connection state           |
| 33      | net_routing_table         | 1KB    | IP routing table           |
| 34      | net_dns_cache             | 4KB    | DNS resolution cache       |

#### AI Service Buffers (35-39)

| Binding | Name        | Size   | Purpose                     |
|---------|-------------|--------|-----------------------------|
| 35      | ai_models   | 384B   | 16 neural network models    |
| 36      | ai_layers   | 3KB    | 128 layer definitions       |
| 37      | ai_requests | 7KB    | 256 inference requests      |
| 38      | ai_results  | 5KB    | 256 result buffers          |
| 39      | ai_weights  | 4MB    | 1M float32 weight values    |

### Buffer Access Patterns

**Read-Write Buffers:**
Most buffers use `var<storage, read_write>` for bidirectional access.

**Read-Only Buffers:**
- `os_vm_bytecode` (binding 5) - Immutable after load

**Atomic Operations:**
Many struct fields use `atomic<u32>` for thread-safe updates:
```wgsl
struct FileEntry {
    size: atomic<u32>,
    created_time: atomic<u32>,
    // ... more atomic fields
}
```

## Service Architecture

### Service Request/Response Model

#### Request Structure

```wgsl
struct ServiceRequest {
    opcode: u32,      // Operation to perform
    arg0: u32,        // First argument
    arg1: u32,        // Second argument
    arg2: u32,        // Third argument
    arg3: u32,        // Fourth argument
}
```

#### Response Structure

```wgsl
struct ServiceResponse {
    status: u32,      // 0=pending, 1=success, 2=error
    value0: u32,      // First return value
    value1: u32,      // Second return value
    value2: u32,      // Third return value
}
```

### Service IDs

| ID | Service Name    | Purpose                              |
|----|-----------------|--------------------------------------|
| 1  | Filesystem      | File operations, directory access    |
| 2  | Reload          | Hot shader reloading                 |
| 3  | Network         | Socket, TCP/UDP, packet handling     |
| 4  | Service Manager | Service registration, IPC            |
| 5  | Control         | System shutdown, runtime control     |

### Filesystem Service (ID: 1)

**Constants:**
```wgsl
const OS_MAX_FILES = 65536u;
const OS_MAX_BLOCKS = 262144u;
const OS_BLOCK_SIZE = 4096u;
```

**File Entry Structure:**
```wgsl
struct FileEntry {
    name: array<u32, 8>,           // 32 chars max
    size: atomic<u32>,
    blocks: array<atomic<u32>, 256>, // Direct block pointers
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

**Operations:**
- Read file
- Write file
- Create file
- Delete file
- List directory

### Window System (ID: 21-26)

**Constants:**
```wgsl
const OS_MAX_WINDOWS = 256u;
const OS_WINDOW_EVENTS_MAX = 1024u;
const OS_MAX_RENDER_COMMANDS = 4096u;
```

**Window Structure:**
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
    flags: atomic<u32>,              // visible, minimized, maximized, focused
    owner_shader: atomic<u32>,
    parent_window: atomic<u32>,
    class_id: atomic<u32>,
}
```

**Event Types:**
- Mouse click
- Mouse move
- Key press
- Key release
- Resize

### Network Service (ID: 3)

**Constants:**
```wgsl
const OS_MAX_SOCKETS = 1024u;
const OS_MAX_PACKETS = 8192u;
const OS_PACKET_BUFFER_SIZE = 1514u;  // MTU + headers
```

**Socket Structure:**
```wgsl
struct Socket {
    id: atomic<u32>,
    domain: atomic<u32>,              // AF_INET, AF_INET6
    socket_type: atomic<u32>,         // SOCK_STREAM, SOCK_DGRAM
    protocol: atomic<u32>,            // TCP, UDP
    local_ip: atomic<u32>,
    local_port: atomic<u32>,
    remote_ip: atomic<u32>,
    remote_port: atomic<u32>,
    state: atomic<u32>,               // CLOSED, LISTEN, CONNECTED, etc.
    receive_buffer_offset: atomic<u32>,
    send_buffer_offset: atomic<u32>,
    receive_buffer_size: atomic<u32>,
    send_buffer_size: atomic<u32>,
    owner_shader: atomic<u32>,
    options: array<atomic<u32>, 8>,
}
```

### AI Service (ID: 35-39)

**Constants:**
```wgsl
const MAX_MODELS: u32 = 16u;
const MAX_LAYERS: u32 = 128u;
const MAX_AI_REQUESTS: u32 = 256u;
const MAX_WEIGHTS: u32 = 1048576u;  // 1M floats = 4MB
```

**Neural Network Structure:**
```wgsl
struct NeuralNetwork {
    model_id: u32,
    layer_count: u32,
    layers_offset: u32,
    total_parameters: u32,
    input_size: u32,
    output_size: u32,
}

struct NeuralLayer {
    layer_id: u32,
    input_count: u32,
    output_count: u32,
    activation_type: u32,  // ReLU, Sigmoid, Tanh
    weights_offset: u32,
    bias_offset: u32,
}
```

**Supported Operations:**
- Model inference
- Forward pass
- Backward pass (training)
- Model load/save

## Debug System

### Debug Logging

Two debug systems are available:

#### 1. Simple Debug Log (binding 3-4)

```wgsl
fn os_debug_log(pc: u32, code: u32, value: u32) {
    let idx = atomicAdd(&os_debug_index, 1u) % OS_DEBUG_ENTRIES;
    os_debug_entries[idx] = DebugEntry(idx, pc, code, value);
}
```

**Capacity:** 2,048 entries
**Entry Size:** 16 bytes (4 u32s)

#### 2. Advanced Debug Traces (binding 12)

```wgsl
fn os_trace_debug_log(
    thread_id: u32,
    pc: u32,
    opcode: u32,
    data0: u32,
    data1: u32,
    data2: u32,
    data3: u32
) {
    let idx = atomicAdd(&os_debug_index, 1u) % OS_MAX_DEBUG_TRACES;
    os_debug_traces[idx] = DebugTrace(
        thread_id, pc, opcode,
        atomicLoad(&os_frame_counter),
        array<u32, 4>(data0, data1, data2, data3)
    );
}
```

**Capacity:** 65,536 traces
**Entry Size:** 32 bytes

### Reading Debug Output

```python
runtime.read_debug_log()
```

Output format:
```
--- SHADER DEBUG LOG ---
  [000] Code: 0xdead, Args: (0x00000000, 0x00000001, 0x00000000)
  [001] Code: 0xbeef, Args: (0x00000042, 0x00000000, 0x00000000)
------------------------
```

## WGSL Constraints & Solutions

### No u64 Support

**Problem:** WGSL requires `SHADER_INT64` capability for u64 types.

**Solution:** All u64 replaced with u32:
```wgsl
// Before
timestamp: u64,
created_time: atomic<u64>,

// After
timestamp: u32,
created_time: atomic<u32>,
```

### No Pointer Returns

**Problem:** Functions cannot return pointers in WGSL.

**Solution:** Access arrays directly instead of helper functions:
```wgsl
// Not allowed
fn get_model(id: u32) -> ptr<storage, NeuralNetwork> {
    return &os_ai_models[id];
}

// Use direct access instead
let model = os_ai_models[model_id];
```

### No Atomic Struct Parameters

**Problem:** Structs containing atomic fields cannot be passed as function parameters.

**Solution:** Use indices and access structs directly:
```wgsl
// Not allowed
fn handle_operation(op: FileOperation) { }

// Use indices instead
fn handle_operation(op_index: u32) {
    let op = os_fs_operations[op_index];
}
```

### Reserved Keywords

**Problem:** `type` is a reserved keyword in WGSL.

**Solution:** Renamed to descriptive alternatives:
```wgsl
struct WindowEvent {
    event_type: u32,  // Was 'type'
    // ...
}

struct Socket {
    socket_type: atomic<u32>,  // Was 'type'
    // ...
}
```

## Performance Characteristics

### Memory Access Patterns

**Atomic Operations:**
- Frame counter: ~1 atomic add per dispatch
- Debug index: ~64 atomic adds per frame (workgroup_size=64)

**Buffer Reads:**
- Service requests: ~256 requests × 20 bytes = 5KB per frame
- Debug log: 16KB read per debug dump

**Buffer Writes:**
- Service responses: ~256 responses × 16 bytes = 4KB per frame
- Debug traces: ~64 traces × 32 bytes = 2KB per frame

### Dispatch Configuration

**Substrate Kernel:**
- Workgroup size: 64 threads
- Typical dispatch: `(1, 1, 1)` workgroups
- Total threads: 64

**Scaling:**
For heavy computation, dispatch more workgroups:
```python
runtime.dispatch_shader(shader_id, workgroups_x=16, workgroups_y=16)
# Total threads: 64 × 16 × 16 = 16,384
```

## Future Enhancements

### Planned Features

1. **Multi-Shader Orchestration**
   - Shader dependency graphs
   - Parallel shader dispatch
   - Inter-shader synchronization

2. **Persistent Storage**
   - Save filesystem to disk
   - Restore state on boot
   - Incremental checkpoints

3. **Real Network Integration**
   - Host-side TCP/IP bridge
   - Actual socket operations
   - Network packet injection

4. **Window System Rendering**
   - Integrate with display output
   - Hardware cursor support
   - VSync timing

5. **Performance Optimizations**
   - Sparse buffer updates
   - Shader compilation cache
   - Asynchronous buffer reads

### Research Directions

- **Shader-based Process Scheduler**
- **GPU Memory Management Unit**
- **Inter-shader RPC mechanisms**
- **JIT compilation of bytecode to WGSL**
- **Distributed ShaderOS across multiple GPUs**

---

**Document Version:** 1.0
**Last Updated:** November 2025
