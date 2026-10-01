# PXC1 Research → Implementation Gaps

## Executive Summary
Analysis of `/host_zion/docs/research/489_pixel_storage.txt` (238KB, 4938 lines) reveals concrete unimplemented features in the current VirtIO-Pixel backend that align with the PXC1 architecture research.

## Status: Current Implementation vs. Research Spec

### ✅ FULLY IMPLEMENTED
- **COW Journaling**: Active delta journal with instant writeback (0ms per flush vs. previous 37-102s)
- **SHA256 Base Verification**: All container sections verified at load time
- **3D Coordinate System**: `(x,y,z)` space with z-layer routing
- **Sparse HashMap Index**: `HashMap<Coord3D, JournalEntry>` for O(1) block resolution
- **Periodic Writeback**: 5s intervals (WRITEBACK_INTERVAL=5)
- **Live Production Verification**: Running on 16GB ubuntu_cognitive_vac2_v3.nut container

### ❌ NOT IMPLEMENTED (Priority Order)

#### 1. **BLOCK DEDUPLICATION** (HIGH PRIORITY - HIGH IMPACT)
**Research Spec:**
- Content-addressed block store using SHA256 hashes
- Replace duplicate 4KB blocks with `DEDUP_REF` codec + hash reference
- Target: "meaningful reduction in journal" for shared libraries/repeated content
- Scaffolding: `BlockCodec::DEDUP_REF` enum exists in `choose_codec()` (lines 143-160)

**Current State:**
```rust
// cow_journal.rs:143-160
fn choose_codec(data: &[u8]) -> BlockCodec {
    if data.iter().all(|&b| b == 0) {
        return BlockCodec::ZERO_FILL;
    }
    BlockCodec::RAW  // ONLY THIS IS EVER RETURNED
}
```

**Implementation Required:**
- Add in-memory `HashMap<Sha256Hash, Vec<u8>>` for content-addressed block cache
- Compute SHA256 for each non-zero block write
- Check cache before choosing codec → `DEDUP_REF` if hash exists
- Store hash reference (32 bytes) instead of full block
- Impact Estimate: 10-30% journal reduction for typical Linux rootfs (shared libs, repeated binaries)

**Code Location:** `systems/virtio_pixel_rs/src/cow_journal.rs`

---

#### 2. **Z-LAYER SEMANTIC ROUTING** (MEDIUM PRIORITY)
**Research Spec:**
- 4 semantic z-layers with per-layer codec selection:
  ```
  z=0: Framebuffer tiles (RGBA display updates)     → GRAMMAR_MACRO
  z=1: VM CPU Context & Register Snapshot           → LZ_ENTROPY
  z=2: OS Rootfs Blocks (ext4 filesystem pages)     → ZERO_FILL + DEDUP_REF
  z=3: Cognitive Weights (GGUF tensors)             → RAW
  ```

**Current State:**
```rust
// z=2 is hardcoded everywhere
const Z_LAYER_ROOTFS: u8 = 2;  // Only layer used
```

**Implementation Required:**
- Add per-layer codec policy table: `HashMap<u8, Vec<BlockCodec>>`
- Route virtio-blk requests based on data type (not implemented yet)
- Add `ZLayerPolicy` trait for extensible routing logic
- Impact: Only matters when backend serves non-rootfs traffic

**Code Location:** `systems/virtio_pixel_rs/src/cow_journal.rs`, `backend.rs`

---

#### 3. **SPARSE QUADTREE LUT** (LOW PRIORITY - NOT NEEDED)
**Research Spec:**
- Replace 1.28GB flat LUT with 27.5MB quadtree
- 46× metadata reduction for large volumes

**Current State:**
Already using `HashMap<Coord3D, JournalEntry>` which achieves the same goal.
The research doc targets a flat-array indexing problem that doesn't exist here.

**Status:** ✅ SKIP - Sparse HashMap is already optimal for this use case

---

## Implementation Priority Matrix

| Feature | Complexity | Impact | Dependencies | Effort | Status |
|---------|-----------|--------|--------------|--------|--------|
| Block Deduplication | Medium | High (10-30% journal reduction) | None (scaffolding exists) | 2-4 hours | READY TO IMPLEMENT |
| Z-Layer Semantic Routing | High | Low (only if multi-layer traffic) | Dedup first | 6-8 hours | BLOCKED |
| Sparse Quadtree LUT | High | None | N/A (already solved) | N/A | SKIP |

## Research Insights (Not Implementation Tasks)

### Pixel Compression Theory
- Grammar/macro encoding achieves 642× compression for periodic patterns
- LZ entropy best for code subroutines (180-358× compression)
- Fixed-point convergence proven (24px → 24px on re-encoding)
- Random data hits entropy floor at 4 bytes/pixel

### PXC1 Container Architecture
- Multi-modal spatial container (RGBA + metadata)
- Block-addressable O(1) cold-load
- 4-layer semantic organization
- MDL-optimized representation selection

**Note:** These are encoder-side improvements for future PXC1 generation tools. The backend (VirtIO-Pixel) is read-only regarding container format and focuses on delta journaling.

## Next Action

**Implement Block Deduplication** in `cow_journal.rs`:
1. Add `dedup_cache: HashMap<[u8; 32], Vec<u8>>` to `CowJournal` struct
2. Implement SHA256 computation for block data
3. Modify `choose_codec()` to check cache → `DEDUP_REF` if match
4. Add `BlockCodec::DEDUP_REF` serialization/deserialization
5. Update writeback path to resolve hash references to actual data

**Expected Impact:** 
- Instant reduction in `.pxc1_delta.jnl` size
- Better compression for repeated library pages
- No breaking changes to existing format
- Can verify impact with `ls -lh .pxc1_delta.jnl` before/after
