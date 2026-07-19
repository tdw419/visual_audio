# MKV as 3D Memory Architecture

## The Spatial Paging System

**Core Insight**: The MKV file itself is the computer.

```
2D Canvas (100×100)        →    3D Volume (100×100×∞)
┌─────────────────┐            ┌─────────────────┐
│ Active VRAM     │            │ Frame 0 (z=0)   │
│ (Screen)        │            │ Active VRAM     │
└─────────────────┘            │                 │
                                └─────────────────┘
                                        ↓
                                ┌─────────────────┐
                                │ Frame 1-N (z>0) │
                                │ Storage / ROM   │
                                └─────────────────┘
```

## 3D Coordinate System

```wgsl
Position = (x, y, z)

x, y: Spatial position on the frame
z: Frame index in the MKV (time dimension)
```

## Memory Layers

```
z=0  → Active VRAM (what you see on screen)
z=1  → Storage Page 1 (code segments)
z=2  → Storage Page 2 (data archives)
z=3  → Storage Page 3 (databases)
z=4  → Storage Page 4 (paused processes)
...
z=N  → Storage Page N (backup snapshots)
```

## 3D Pixel Access

```wgsl
fn fetch_pixel_3d(x: u32, y: u32, z: u32) -> vec3<u32> {
    let index = (z * uniforms.vram_width * uniforms.vram_height) +
                (y * uniforms.vram_width) +
                x;
    let p = vram[index];
    return vec3<u32>(p.r, p.g, p.b);
}

fn write_pixel_3d(x: u32, y: u32, z: u32, r: u32, g: u32, b: u32) {
    let index = (z * uniforms.vram_width * uniforms.vram_height) +
                (y * uniforms.vram_width) +
                x;
    vram[index].r = r;
    vram[index].g = g;
    vram[index].b = b;
    vram[index].a = 255u;
}
```

**Index Formula**:
```
index = (z × width × height) + (y × width) + x
```

## Spatial Paging Flow

```
Active Program (x,y,z=0) needs data from storage:
    ↓
1. sys_mmap(req_size, src_z)
    ↓
2. Hilbert allocator finds free block on z=0
    ↓
3. Patch-and-Copy: Copy block from (sx,sy,src_z) to (dx,dy,0)
    ↓
4. Program accesses data locally at (dx,dy,0)
    ↓
5. sys_munmap(addr, dest_z)
    ↓
6. Patch-and-Copy: Copy block back to (sx,sy,dest_z)
    ↓
7. Free region on z=0 for reuse
```

## Hilbert-Curve Allocator

```wgsl
fn hilbert_alloc_block(size: u32) -> vec3<u32> {
    // Hilbert curve scan from (0, 0, 0) → (width-1, height-1, 0)
    // Find consecutive black pixels of requested size
    // Return base coordinate or (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF) on failure

    // Linear scan for now (will upgrade to true Hilbert)
    for (var y = 0u; y < uniforms.vram_height; y = y + 1u) {
        for (var x = 0u; x < uniforms.vram_width; x = x + 1u) {
            let px = fetch_pixel_3d(x, y, 0u);

            if (px.r == 0u && px.g == 0u && px.b == 0u) {
                // Check if we have `size` consecutive pixels
                var consecutive = 0u;
                var scan_x = x;

                while (consecutive < size && scan_x < uniforms.vram_width) {
                    let scan_px = fetch_pixel_3d(scan_x, y, 0u);
                    if (scan_px.r == 0u && scan_px.g == 0u && scan_px.b == 0u) {
                        consecutive = consecutive + 1u;
                        scan_x = scan_x + 1u;
                    } else {
                        break;
                    }
                }

                if (consecutive == size) {
                    return vec3<u32>(x, y, 0u);  // Found block
                }

                x = scan_x;  // Skip past this failed region
            }
        }
    }

    return vec3<u32>(0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu);  // No free space
}
```

## Spatial Syscalls

### sys_mmap: Memory Map (Page In)

```wgsl
fn spatial_mmap(dest_reg: u32, src_z: u32, size: u32) -> vec3<u32> {
    // Find free block on active frame (z=0)
    let dest_addr = hilbert_alloc_block(size);

    if (dest_addr.x == 0xFFFFFFFFu) {
        return dest_addr;  // Allocation failed
    }

    // Copy block from source frame to destination frame
    for (var i = 0u; i < size; i = i + 1u) {
        let src_px = fetch_pixel_3d(i, 0u, src_z);
        write_pixel_3d(dest_addr.x + i, dest_addr.y, 0u, src_px.r, src_px.g, src_px.b);
    }

    return dest_addr;
}
```

### sys_munmap: Memory Unmap (Page Out)

```wgsl
fn spatial_munmap(addr: vec3<u32>, dest_z: u32, size: u32) {
    // Copy block from active frame to destination frame
    for (var i = 0u; i < size; i = i + 1u) {
        let src_px = fetch_pixel_3d(addr.x + i, addr.y, 0u);
        write_pixel_3d(i, 0u, dest_z, src_px.r, src_px.g, src_px.b);
    }

    // Free block on active frame (black out pixels)
    for (var i = 0u; i < size; i = i + 1u) {
        write_pixel_3d(addr.x + i, addr.y, 0u, 0u, 0u, 0u);
    }
}
```

## Opcodes

```wgsl
const OPCODE_LDI: u32 = 0u;
const OPCODE_ADD: u32 = 1u;
const OPCODE_PRT: u32 = 8u;
const OPCODE_HALT: u32 = 9u;
const OPCODE_MMAP: u32 = 10u;   // Memory map (page in)
const OPCODE_MUNMAP: u32 = 11u; // Memory unmap (page out)
```

## Process Control Block (3D)

```wgsl
struct Process {
    pid: u32,
    state: u32,
    pc: vec3<u32>,         // 3D Program Counter (x, y, z)
    base_coord: vec3<u32>, // 3D Spatial region base
    registers: array<u32, 8>,
    output_ptr: u32,
}
```

**Size**: 68 bytes per process
```
4(pid) + 4(state) + 12(pc) + 12(base) + 32(registers) + 4(output) = 68 bytes
```

## Memory Block Tracking

```wgsl
struct MemoryBlock {
    in_use: u32,
    owner_pid: u32,
    size: u32,
    addr: vec3<u32>,       // 3D coordinate
    z_page: u32,          // Storage page (if paged out)
}
```

## Spatial Advantages

### 1. Zero-Random-Access Paging
- Traditional OS: Page in from disk → RAM access
- Spatial OS: Read from z=1 → Copy to z=0 → Access locally
- No disk I/O, only GPU memory operations

### 2. VLM-Observable State
- Traditional OS: Memory hidden in RAM
- Spatial OS: All memory is visible as pixel patterns
- VLM can see fragmentation, hot blocks, cold blocks

### 3. Spatial Locality Preservation
- Linear heap: 1×16 strip (ugly, non-local)
- Hilbert allocator: 4×4 square (beautiful, cache-friendly)

### 4. Self-Contained Storage
- Traditional OS: Separate hard drive
- Spatial OS: Hard drive IS the MKV frames
- Entire computer is a single video file

## The MKV Computer

**What the MKV Contains**:
```
Frame 0 (z=0): Active processes, UI, windows
Frame 1 (z=1): Storage archives, code segments
Frame 2 (z=2): Databases, filesystems
Frame 3 (z=3): Paused processes, snapshots
Frame 4-9 (z=4-9): Reserved for expansion
```

**What the CPU Does**:
- Only launches initial kernel shader
- Reads final result
- Never touches program memory

**What the GPU Does**:
- Manages 3D memory pages
- Pages in/out on demand
- Executes programs across frames
- Self-healing via backup frames

## Implementation Status

### Phase 2: Memory Management (CURRENT)
- ✅ 3D coordinate system (x, y, z)
- ✅ 3D pixel fetch/write
- ✅ Hilbert allocator (linear scan version)
- ✅ sys_mmap / sys_munmap opcodes
- ✅ VRAM 3D buffer (10 frames)
- ✅ Process table with 3D coordinates
- ⏳ True Hilbert curve allocator
- ⏳ Memory block tracking table
- ⏳ Page fault handling

### Next: Hilbert Curve Implementation
- Implement true Hilbert curve mapping
- Preserve spatial locality
- Enable 4×4 square allocations instead of 1×16 strips

---

**The MKV file IS the computer.**

Frame 0 is the screen. Frames 1-N are the hard drive. The Z-axis is the storage depth. The entire OS is a 3D volume of pixels.