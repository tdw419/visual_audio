# V3 → V4 Boot Path Analysis

## V3 Architecture (What Works)

V3 boots kernels via: **UEFI/OpenSBI → BlockIO → PNG decode → ELF64 load → jump**

```
bootloader_uefi.rs (x86_64)
├─ UEFI entry point
├─ Locate BlockIO device
├─ Read disk bytes
├─ Detect PNG signature (0x89PNG\r\n\x1a)
├─ PixelDecoder::decode_geos_pixel_container()
│  ├─ Parse PNG chunks (IHDR, IDAT, IEND)
│  ├─ DEFLATE decompress (miniz_oxide)
│  ├─ Unfilter PNG rows
│  └─ Hilbert xy2d mapping → linear byte stream
└─ Elf64Loader → load PT_LOAD segments → jump to e_entry
```

## V4 Architecture (What We Have)

V4 is a tiled spatial storage format (PDB), not a bootable image:

```
V4/PDB Output
├─ tiles.json (metadata)
│  ├─ table: rootfs_blob (row_count=1519210866, row_length=1)
│  └─ tiles: 32 PNG tiles (48.7MB each, Hilbert-mapped RGB)
└─ file_metadata.pdb.png
   └─ 85K file entries (path → offset + size)
```

## What V4 Can Reuse from V3

### 1. **Hilbert Curve Implementation** ✓ Already Shared
```rust
// V3 decoder.rs line 128
let d = geos_pixel::HilbertCurve::xy2d(grid_size, x, y);
```
V3's Hilbert code is `geos_pixel::HilbertCurve`, which V4 already uses. The spatial mapping is identical.

### 2. **PNG Decoding Infrastructure** ✓ Reusable
V3 has a no_std PNG decoder (`PixelDecoder::decode_frame`) that:
- Parses PNG chunks
- DEFLATE decompresses via `miniz_oxide`
- Unfilters PNG rows
- Extracts RGBA/RGB pixels

**V4 can port this to decode its tiled PNGs at boot time.**

### 3. **ELF64 Loader** ✓ Reusable
V3's `Elf64Loader` can load kernels from any byte buffer.
V4 could encode a kernel as another PDB table and use V3's loader.

## V4 Boot Path Options

### Option A: Hybrid (Boot-time Extract) — Recommended
```
V4 bootloader (V3-based)
├─ Decode V4 tiles using V3's PixelDecoder
├─ Reassemble rootfs blob (cat 32 tiles)
├─ Mount as virtio-blk device
└─ Boot standard Linux kernel with ext4 support
```

**Pros:**
- Uses standard Linux kernel (no new drivers needed)
- V4 becomes storage format only
- Leverages V3's proven PNG decoder + Hilbert mapping

**Cons:**
- Boot-time extraction adds latency
- Doesn't fully exploit spatial filesystem at runtime

### Option B: V4-Native (Kernel-space PDB driver)
```
Custom kernel with PDB filesystem driver
├─ V4 bootloader loads kernel via V3's Elf64Loader
├─ Kernel includes PDB driver (new code needed)
├─ Mount V4 tiles directly as rootfs
└─ No extraction step
```

**Pros:**
- Spatial filesystem available at runtime
- No extraction overhead

**Cons:**
- Requires new kernel driver development
- Out of scope for current milestone

## Recommended Next Steps for V4 Boot

1. **Port V3's PixelDecoder to V4**
   - Move `virtio_pixel_rs_v3_shared/decoder.rs` → `geos_pixel/src/decoder/`
   - Adapt to decode multi-tile PDB sequences

2. **Create V4 boot tool**
   - Generate multi-PDB PNG containing: kernel + initramfs + rootfs tiles
   - Use V3 bootloader structure with V4 tile decoding logic

3. **Extract-and-handoff proof-of-concept**
   - Boot standard Ubuntu from V4 tiles
   - Extract rootfs blob at boot time
   - Hand off to standard kernel

## What V3 Cannot Help With

V3 does NOT provide:
- PDB header parsing (V4-specific metadata)
- Multi-tile sequence reassembly
- file_metadata table querying
- Tiled blob seeking logic

**These must be implemented as V4-specific extensions to V3's decoder.**