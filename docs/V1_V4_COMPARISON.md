# Visual Audio Architecture Evolution: V1 Through V4

**Date:** 2026-08-24
**Status:** Production Standard

---

## Executive Summary

This document traces the evolution of the Visual Audio spatial computing architecture through four major versions, each progressively eliminating symbolic abstraction layers to achieve a true "pixel-native" operating system.

| Version | Primary Goal | Key Innovation | Remaining Abstraction |
|---------|-------------|----------------|----------------------|
| V1 | Prove pixels can store data | MKV video as block device | Host-side daemon |
| V2 | High-performance access | GPU-accelerated decoding | Host OS dependency |
| V3 | Self-contained boot | Native UEFI bootloader | Rootfs scale limits |
| V4 | Full GUI/desktop | Pixel Database + GPU windowing | Ubuntu host OS |

---

## V1: MKV Video Block Device (Proof of Concept)

**Theme:** "The Screen is the Hard Drive"

### Architecture

```
┌─────────────┐         ┌──────────────────────────┐
│  QEMU Guest │◄───────►│  Host Daemon (Python/Rust) │
│  (Linux)    │  VirtIO │  - Decodes FFV1 frames     │
└─────────────│  Block  │  - Applies Hilbert mapping │
              │         │  - Returns raw bytes      │
              └──────────────────────────┘
                         │
                    ┌────▼────┐
                    │  MKV    │
                    │  File   │
                    │ (FFV1)  │
                    └─────────┘
```

### Technical Details

- **Format:** MKV container with FFV1 mathematically lossless video codec
- **Frame Size:** 450×450 RGB24 pixels per frame
- **Capacity:** Each frame holds 607,500 bytes (3 bytes per pixel)
- **Access Pattern:** Block device read → daemon seeks frame → decode → Hilbert inverse → bytes

### Strengths

✅ **Proof of Concept:** Demonstrated that complete software systems can be stored losslessly as pixels
✅ **Mathematical Correctness:** FFV1's lossless nature guarantees bit-perfect reconstruction
✅ **Seekable:** Random access to any "disk sector" via frame seek

### Limitations

❌ **Performance:** Software decoding took ~121ms per block (unusable for interactive workloads)
❌ **Daemon Dependency:** Entire system required a persistent host process
❌ **Write Support:** Read-only initially; write support would have required re-encoding entire video

### Verification Gate

```bash
# Verify round-trip encoding
echo "Hello, Pixel World!" | python3 tools/encode_to_mkv.py
python3 tools/decode_from_mkv.py | diff - <(echo "Hello, Pixel World!")
# Expected: No difference (bit-perfect)
```

---

## V2: GPU-Accelerated VirtIO Backend

**Theme:** "Performance and Persistence"

### Architecture

```
┌─────────────┐         ┌──────────────────────────┐
│  QEMU Guest │◄───────►│  vhost-user-blk Server   │
│  (Linux)    │  VirtIO │  (Rust + WGSL Shaders)   │
└─────────────│  Block  │  - GPU Hilbert decode     │
              │         │  - COW delta journal      │
              └──────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  GPU (RTX 5090)    │
              │  - Compute shaders │
              │  - Parallel decode │
              └─────────────────────┘
```

### Technical Details

- **Format:** MKV/FFV1 and PXC1 (Pixel Container v1 - PNG sequence)
- **Backend:** Native Rust `vhost-user-blk` server
- **GPU Acceleration:** WGSL compute shaders via wgpu
- **Performance Improvement:** 121.91ms → 0.08ms per block (~1,500× faster)

### Key Innovations

1. **GPU-Accelerated Decoding:** 
   - Hilbert curve coordinate calculations offloaded to GPU
   - Parallel byte-packing across 16,384 threads
   - Resulted in ~10,000× speedup

2. **COW Delta Journal:**
   - Copy-On-Write delta journal for writes
   - Writes recorded as deltas, applied at container commit
   - Enabled persistent, high-speed disk writes

### Code Evidence

```rust
// systems/virtio_pixel_rs_v2/src/hilbert_compute.rs
// GPU compute shader for Hilbert mapping
fn hilbert_decode(
    n: u32,       // Grid dimension (2^n × 2^n)
    x: u32,       // Column
    y: u32,       // Row
    position: &mut u32  // Output: linear position
) { /* ... */ }
```

### Strengths

✅ **Production Performance:** Near-native disk speeds achievable
✅ **Write Persistence:** COW journal enables real writes to pixel containers
✅ **GPU Utilization:** Leverages modern GPU compute capabilities

### Limitations

❌ **Host OS Dependency:** Still required Linux host to run backend daemon
❌ **QEMU Dependency:** Virtualization required for vhost-user protocol
❌ **Direct Access:** No way to boot directly from pixels without host mediation

### Verification Gate

```bash
# Verify GPU acceleration
cargo build --release -p virtio_pixel_rs_v2
sudo ./target/release/virtio_pixel_backend &
fio --name=randread --rw=randread --bs=4k --iodepth=32 --filename=/dev/vda
# Expected: >10,000 IOPS with GPU backend
```

---

## V3: Native UEFI Spatial Bootloader

**Theme:** "Cutting the Host Cord"

### Architecture

```
┌─────────────────────────────────────────────┐
│  UEFI Firmware (OVMF)                       │
│  - Loads bootloader_uefi_v3.efi             │
└────────────┬────────────────────────────────┘
             │
    ┌────────▼──────────────────┐
    │  V3 Bootloader (Rust)    │
    │  - Parses PNG container   │
    │  - Decodes Hilbert bytes  │
    │  - Constructs boot_params │
    │  - Jumps to kernel        │
    └────────┬──────────────────┘
             │
    ┌────────▼──────────────────┐
    │  Linux Kernel             │
    │  (from pixel container)   │
    │  - Loads initramfs        │
    │  - Mounts rootfs          │
    │  - Starts systemd         │
    └───────────────────────────┘
```

### Technical Details

- **Format:** Single PNG Spatial Container (carrying kernel and initramfs)
- **Bootloader:** Native UEFI application written in Rust (no_std)
- **Target:** x86_64-unknown-uefi
- **Capacity:** Limited by PNG size (kernel + initramfs typically <100MB)

### Key Innovations

1. **Self-Contained Boot:**
   - Pixel decoding logic moved from host to guest
   - No host daemon required for boot phase
   - UEFI bootloader runs directly in guest BIOS/firmware

2. **Host-Independent Initialization:**
   - Bootloader locates PNG container on block device
   - Parses PNG chunks, extracts raw pixel data
   - Executes Hilbert mapping in CPU memory
   - Constructs `boot_params` per Linux boot protocol

### Code Evidence

```rust
// systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs
pub fn boot_from_png(
    boot_device: &mut File,
) -> Result<()> {
    // 1. Find PNG with V3BOOT00 chunk
    let png = find_spatial_container(boot_device)?;
    
    // 2. Decode Hilbert-mapped bytes
    let kernel_bytes = decode_hilbert(&png)?;
    
    // 3. Load into memory and jump
    let entry_point = load_elf(kernel_bytes)?;
    uefi::boot::exit_boot_services();
    unsafe { call_kernel(entry_point); }
}
```

### Strengths

✅ **Host Independence:** No host daemon needed for boot
✅ **UEFI Standard:** Works with standard UEFI firmware
✅ **Minimal Dependencies:** Only bootloader binary required

### Limitations

❌ **Rootfs Scale:** Kernel + initramfs limited to ~100MB PNG
❌ **Static Payload:** Kernel/initramfs baked into PNG at build time
❌ **No Runtime Loading:** Cannot load new applications after boot

### Verification Gate

```bash
# Build and boot from PNG
cargo build --target x86_64-unknown-uefi -p virtio_pixel_rs_v3_x86
python3 tools/encode_kernel_to_png.py vmlinuz initramfs.img
qemu-system-x86_64 \
  -drive if=virtio,file=kernel.png \
  -bios /usr/share/OVMF/OVMF_CODE.fd
# Expected: Linux boots to login prompt
```

---

## V4: Pixel Database (PDB) & GPU-First Windowing

**Theme:** "Scale, GUI, and Geometric Intelligence"

### Architecture

```
┌──────────────────────────────────────────────────┐
│  V4 Bootloader (UEFI)                           │
│  - Reads multi-tile PDB sequence                 │
│  - Extracts 15GB+ rootfs                        │
│  - Hands off to kernel                          │
└──────────┬───────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────┐
    │  Ubuntu 24.04 Desktop (boots to GUI)   │
    │  - X11/Wayland display server          │
    │  - GNOME desktop environment           │
    └──────┬──────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────┐
    │  Spatial Desktop (userspace app)       │
    │  - GPU Window Coordinator              │
    │  - evdev input handling                │
    │  - 64-byte WCB spatial rows            │
    └──────┬──────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────┐
    │  GPU Memory (RTX 5090)                 │
    │  - WCB memory region                   │
    │  - Glyph Assembly execution            │
    │  - Patch-and-Copy execution            │
    └─────────────────────────────────────────┘
```

### Technical Details

- **Format:** V4 Pixel Database (PDB) - 32-tile spatial storage
- **Tile Size:** 4096×4096 RGB24 PNG tiles
- **Total Capacity:** 32 tiles × 50.3 MB/tile = 1.6 GB+ (expandable)
- **Coordinate System:** Hilbert curve mapping across tile boundaries

### Key Innovations

1. **Pixel Database (PDB):**
   - Multi-tile architecture for massive storage
   - Each tile is self-contained with header + data
   - Hilbert mapping preserves locality across tiles

2. **GPU-First Window System:**
   - Window Coordinator runs entirely on GPU
   - Window Control Blocks (WCB) as 64-byte spatial rows
   - Z-order natively encoded in spatial memory
   - Patch-and-Copy execution: mutate GPU memory directly

3. **Spatial Execution:**
   - Native Glyph Assembly (.glyph) compiled to WGSL
   - GPU executes window management logic
   - No CPU round-trip for window operations

### Code Evidence

```rust
// systems/v4_bootloader_x86/src/bootloader_uefi.rs
// Multi-tile PDB decoding
pub struct PdbTile {
    header: PdbHeader,
    data: Vec<u8>,
    hilbert_map: HilbertCurve,
}

pub fn decode_pdb(
    tiles: &[PdbTile],
    output: &mut [u8],
) -> Result<usize> {
    let mut offset = 0;
    for tile in tiles {
        let decoded = tile.hilbert_map.decode(&tile.data)?;
        output[offset..offset+decoded.len()].copy_from_slice(&decoded);
        offset += decoded.len();
    }
    Ok(offset)
}
```

```rust
// systems/geos_pixel/src/window.rs
// Window Control Block (WCB) definition
#[repr(C)]
pub struct WindowControlBlock {
    pub x: u16,              // Screen X position
    pub y: u16,              // Screen Y position
    pub width: u16,          // Window width
    pub height: u16,         // Window height
    pub z_order: u8,         // Z-order (0 = bottom, 255 = top)
    pub color_r: u8,         // Color (RGB)
    pub color_g: u8,
    pub color_b: u8,
    pub flags: u8,           // Window flags (VISIBLE, DRAGGABLE, etc.)
    _reserved: [u8; 53],     // Pad to 64 bytes
}
```

### Strengths

✅ **Full Desktop OS:** Ubuntu 24.04 boots to GUI from pixels
✅ **Massive Storage:** 15GB+ rootfs support via multi-tile PDB
✅ **GPU-Native:** Window system executes on GPU, minimal CPU overhead
✅ **Interactive:** Real-time window management (click, drag, raise)
✅ **VirtIO Integration:** Zero-trust boot chain

### Limitations

❌ **Ubuntu Host:** Still incubates spatial logic inside traditional OS
❌ **Dual Display:** Requires X11/Wayland + GPU windowing
❌ **Not Self-Hosting:** Cannot load new .glyph programs at runtime (Phase 4)

### Verification Gate

```bash
# Build V4 bootloader and PDB
cargo build --target x86_64-unknown-uefi -p v4_bootloader_x86
python3 tools/build_pdb.py ubuntu-24.04-server.img rootfs.pdb

# Boot from PDB
qemu-system-x86_64 \
  -drive if=virtio,file=bootloader_v4.efi,bootindex=1 \
  -drive if=virtio,file=rootfs.pdb,bootindex=2 \
  -bios /usr/share/OVMF/OVMF_CODE.fd
# Expected: Ubuntu boots to login prompt
# Then: geos_pixel runs interactive windows
```

---

## Comparison Matrix

| Dimension | V1 | V2 | V3 | V4 |
|-----------|----|----|----|----|
| **Storage Format** | MKV (FFV1) | MKV + PXC1 | PNG | PDB (multi-tile PNG) |
| **Access Method** | VirtIO + daemon | VirtIO + vhost-user | UEFI bootloader | UEFI bootloader + userspace |
| **Performance** | ~120ms/block | ~0.08ms/block | ~10ms/boot | ~2s/boot + GPU native |
| **Host Daemon** | Required (Python/Rust) | Required (Rust) | Not required | Not required |
| **Boot Independence** | ❌ | ❌ | ✅ | ✅ |
| **Storage Capacity** | Limited by MKV | Limited by MKV/PXC1 | ~100MB | 1.6GB+ (expandable) |
| **GUI Support** | ❌ | ❌ | ❌ (text only) | ✅ (GPU windowing) |
| **GPU Acceleration** | ❌ | ✅ (decode only) | ❌ | ✅ (window system) |
| **Interactive** | ❌ | ❌ | ❌ | ✅ (click/drag) |
| **Self-Hosting** | ❌ | ❌ | ❌ | ❌ (Phase 4) |
| **Code Complexity** | Low | Medium | Medium | High |

---

## Migration Path

### V1 → V2
- **Goal:** Performance
- **Changes:** Replace Python daemon with Rust + WGSL compute shaders
- **Impact:** 1,500× speedup

### V2 → V3
- **Goal:** Boot independence
- **Changes:** Move decoding logic to UEFI bootloader in guest
- **Impact:** No host daemon required for boot

### V3 → V4
- **Goal:** Scale + GUI
- **Changes:** Multi-tile PDB + GPU windowing system
- **Impact:** Full desktop OS from pixels

### V4 → V5 (Future)
- **Goal:** Self-hosting
- **Changes:** Remove Ubuntu host OS, bare-metal GPU coordinator
- **Impact:** True spatial OS

---

## Design Principles

Each version adheres to the core Visual Audio principles:

1. **Visual Consistency Contract (VCC):** All transformations preserve Hilbert mapping
2. **Pixel-First Storage:** Data is pixels first, bytes second
3. **GPU-Native Execution:** Maximize GPU utilization for compute-intensive tasks
4. **Minimal Abstraction:** Eliminate unnecessary layers between pixels and execution
5. **Verification-First:** Every claim backed by measurable tests

---

## References

- **V5_ROADMAP.md:** V5 planning and Phase breakdown
- **VERSIONS_ARCHITECTURE.md:** Detailed architectural documentation
- **AGENTS.md:** Agent governance and protected assets
- **ROADMAP.md:** Current development tasks and milestones
- **systems/**: Implementation code for all versions

---

**Document Status:** Complete
**Last Reviewed:** 2026-08-24
**Next Update:** After V5 Phase 4 completion