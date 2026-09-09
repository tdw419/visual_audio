# Infinite Desktop & Pixel-Native Linux Architecture

## Current Constraints

```
VAC2 Container: 4096×4096×3 BGR24 (50MB)
├─ Viewport: Fixed 4096×4096
├─ Problem: Can't position windows outside this boundary
└─ Need: Infinite virtual coordinate space
```

## Solution: Virtual Viewport System

### Virtual Coordinate Space

```
Virtual Space: 65536×65536×3 (8GB of virtual pixels)
├─ Viewport 0:  (0,0) → (4096,4096)  ← Current visible region
├─ Viewport 1:  (4096,0) → (8192,4096) ← Off-screen window
├─ Viewport 2:  (0,4096) → (4096,8192) ← Off-screen window
└─ ...: Infinite grid of viewports
```

### Implementation Layers

**Layer 1: Virtual Memory Manager**
- Maps virtual coordinates (vx, vy) → physical pixel locations
- Handles viewport translation: `phys_offset = viewport_origin + local_offset`
- Supports viewport switching (scroll/paging)

**Layer 2: Window Manager for Infinite Space**
- Windows can exist at any virtual coordinate
- Track window positions in virtual coordinate system
- Pan/scroll to bring off-screen windows into view

**Layer 3: Multi-Container Composition**
- Each pixel Linux = one VAC2 container (4096×4096)
- Place containers at different virtual coordinates
- Seamlessly composite between containers

## Pixel-Native OS Operations

### Concept: Pixels as Instructions

```
Traditional:  ls → compiled bash binary → syscalls → files
Pixel-Native:  ls → pixel pattern transformation → file list as pixels
```

### Execution Model

**Phase 1: Understand Pixel-Encoded Behavior**
- Map bash `ls` behavior to pixel patterns in current container
- Identify which pixel regions encode directory traversal
- Extract the "program graph" from pixel structures

**Phase 2: Pixel Manipulation Compiler**
```
Command: ls /home
↓
Pixel Plan:
  - Locate /home directory pixels
  - Extract filename patterns
  - Transform to ASCII pixel grid
  - Output to display viewport
↓
Execute: Move pixels directly
```

**Phase 3: Pixel-Based Virtual Machine**
- Define instruction set where each opcode = pixel pattern
- VM operates on pixel memory directly
- "Running a program" = applying pixel transformations

## Recursive Pixel Linux Boot

### Goal: Boot Pixel Linux from Within Pixel Linux

```
┌─────────────────────────────────┐
│  Current Pixel Linux (Viewport 0) │
│  ┌─────────────────────────────┐ │
│  │  Launcher pixels            │ │
│  │  ┌───────────────────────┐  │ │
│  │  │  New Pixel Linux     │  │ │
│  │  │  (Viewport 1)         │  │ │
│  │  │  Booting...           │  │ │
│  │  └───────────────────────┘  │ │
│  └─────────────────────────────┘ │
└─────────────────────────────────┘
```

### Boot Flow

1. **Create virtual viewport at (4096, 0)**
2. **Load second VAC2 container pixels** into that region
3. **Initialize bootloader pixels** at virtual offset
4. **Extract kernel pixels** and map to virtual memory
5. **Boot second instance** in isolated virtual space

### Implementation Steps

```
Step 1: Virtual Viewport API
  - create_viewport(x, y, width, height, container_path)
  - switch_viewport(viewport_id)
  - list_windows()
  - pan_viewport(dx, dy)

Step 2: Pixel-Program Extractor
  - analyze_container(container_path)
  - extract_program_graph(command_name)
  - output_pixel_plan()

Step 3: Pixel-Program Executor
  - execute_pixel_plan(plan)
  - monitor_pixel transformations
  - capture_results

Step 4: Recursive Bootloader
  - launch_pixel_linux(container_path, virtual_origin)
  - manage multiple instances
  - communicate between instances
```

## Technical Approach: VirtIO Pixel Extended

### Current Backend (virtio_pixel_backend.rs)
```
Guest requests: Block read/write → pixel container access
```

### Proposed Extension: Virtual Viewport Backend

```rust
struct VirtualViewpointBackend {
    virtual_size: (u32, u32), // 65536×65536
    viewports: HashMap<ViewportID, Viewport>,
    containers: HashMap<ContainerID, Container>,
}

struct Viewport {
    origin: (u32, u32), // Virtual coordinate
    size: (u32, u32),   // Usually 4096×4096
    container_id: Option<ContainerID>,
}

// New virtio commands:
VIRTIO_PIXEL_CMD_CREATE_VIEWPORT  = 0x10
VIRTIO_PIXEL_CMD_SWITCH_VIEWPORT  = 0x11
VIRTIO_PIXEL_CMD_PAN              = 0x12
VIRTIO_PIXEL_CMD_MAP_CONTAINER    = 0x13
```

### Guest Kernel Driver Extensions

```c
// New ioctl interface:
ioctl(fd, PIXEL_CREATE_VIEWPORT, &viewport_config);
ioctl(fd, PIXEL_SWITCH_VIEWPORT, viewport_id);
ioctl(fd, PIXEL_PAN, &pan_delta);

// Userspace library:
int pixel_create_viewport(int x, int y, int w, int h);
void pixel_switch_viewport(int id);
void pixel_pan_to(int x, int y);
```

## Phase 1 Proof of Concept: Off-Screen Window Demo

**Goal:** Create a window outside current viewport and scroll to it

**Steps:**
1. Extend virtio-pixel backend with viewport commands
2. Create viewport at (4096, 0) with second pixel container
3. Place a test window in off-screen viewport
4. Implement pan/scroll to bring it into view
5. Verify window persists when switching viewports

**Verification:**
```
# From within Pixel Linux
pixel-create-viewport --x 4096 --y 0 --container ubuntu_desktop_pxc1_v2
pixel-switch-viewport 1
# Window appears
pixel-pan --dx -4096
# Window disappears (back to viewport 0)
```

## Phase 2: Pixel Program Extraction

**Goal:** Map `ls /etc/passwd` to pixel operations

**Steps:**
1. Trace `ls` execution in current container
2. Log all pixel accesses/transformations
3. Build pixel-operation graph for this command
4. Replay graph to verify correctness
5. Optimize graph for pixel-nativeness

**Expected Output:**
```json
{
  "command": "ls /etc/passwd",
  "pixel_operations": [
    {"type": "read_region", "offset": [12345, 67890], "size": 512},
    {"type": "transform", "pattern": "filename_extract"},
    {"type": "write_region", "offset": [4095, 100], "data": "/etc/passwd"}
  ]
}
```

## Phase 3: Pixel-Native VM

**Goal:** Execute programs by applying pixel transformations

**Design:**
- Instruction set = 256 pixel patterns
- Registers = pixel regions
- Memory = pixel coordinate space
- "Compilation" = translate bash commands to pixel transformations

**Example:**
```pixel
OP_READ_REGION  [file_header]
OP_TRANSFORM    [pattern: list_entries]
OP_WRITE_REGION [output_buffer]
OP_DISPLAY      [viewport: current]
```

## Long-Term Vision

### Recursive Self-Modification

```
Pixel Linux modifies its own pixels to add features
→ New features encoded as pixel patterns
→ Self-improving OS through pixel manipulation
```

### Multi-Level Pixel Computing

```
Level 1: Pixels represent data (current VAC2)
Level 2: Pixels represent programs (pixel-native OS)
Level 3: Pixels represent architecture (recursive boot)
Level 4: Pixels represent the pixel format itself
```

### The "Infinite Desktop" as Infinite Computing

- Each viewport region = independent computing space
- Container = isolated OS instance
- Pixel manipulation = communication channel
- No boundaries except virtual coordinate space

## Open Questions

1. **Performance:** Pixel manipulation vs compiled code?
2. **Debugging:** How to debug pixel programs?
3. **Security:** Prevent pixel corruption of critical regions?
4. **Compression:** Infinite space needs efficient encoding
5. **Bootstrapping:** First pixel program must come from somewhere

## Next Steps

1. Implement virtual viewport backend
2. Create off-screen window demo
3. Extract pixel graphs for simple commands
4. Design pixel instruction set
5. Build pixel-native VM prototype