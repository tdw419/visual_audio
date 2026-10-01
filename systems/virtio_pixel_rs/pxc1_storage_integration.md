# PXC1 Integration Plan for VirtIO-Pixel

## Current Bottlenecks

1. **37-second writeback latency** - Full rootfs re-encode required for every flush
2. **300-second writeback interval** - Required to prevent ext4 journal corruption
3. **GB-scale LUT overhead** - Flat lookup table for large containers
4. **No block-level deduplication** - Duplicate pages consume full storage

## PXC1 Architecture Integration

### Phase 1: Persistent COW Journal (Immediate Impact)

**Goal:** Replace full re-encode writes with append-only delta journal

**Implementation:**
- Create `.pxc1_delta` file alongside existing `.nut` container
- Track mutated 4KB blocks in in-memory hash map
- Append-only log format: `[seq(4B) | x(2B) | y(2B) | z(1B) | codec(1B) | len(4B) | crc32(4B) | payload(N)]`
- Instant compaction: Merge delta back to base in 10ms instead of 37s

**Expected Impact:**
- Writeback: 37s → ~10ms (3700× faster)
- Interval: 300s → 5s (60× more responsive)
- Data loss window: 300s → 5s

### Phase 2: Sparse Quadtree LUT (Memory Optimization)

**Goal:** Replace flat 1.28GB LUT with 27.5MB quadtree

**Implementation:**
- Replace linear LUT with hierarchical quadtree indexing
- Collapse contiguous uniform regions (zero pages, duplicate blocks)
- 46× metadata reduction for 4096×4096×4 volumes

**Expected Impact:**
- Memory overhead: 1.28GB → 27.5MB for indexing
- O(log n) lookup instead of O(n) for sparse regions
- Better cache locality for block resolution

### Phase 3: Multi-Layer Spatial Organization (Architecture Upgrade)

**Goal:** Organize data into semantic z-layers

**Layer Mapping:**
```
z=0: Framebuffer tiles (RGBA display updates)
z=1: CPU context snapshots (register state during migration)
z=2: OS rootfs blocks (ext4 filesystem pages - current data)
z=3: GGUF neural weights (LLM model tensors - future)
```

**Implementation:**
- Extend existing `(x,y)` coordinate space to `(x,y,z)`
- Per-layer codec selection based on data type:
  - z=0: GRAMMAR_MACRO (repeating pixel patterns)
  - z=1: LZ_ENTROPY (structured register state)
  - z=2: ZERO_FILL + DEDUP_REF (sparse filesystem)
  - z=3: RAW (incompressible quantized weights)

**Expected Impact:**
- 2-5× additional compression for structured data
- O(1) access to any layer without loading others
- Support for future GGUF-X integration

## Integration Points

### Existing VirtIO-Pixel Backend Modifications

1. **backend.rs** - Add PXC1 container wrapper around `SpatialMkvExtractor`
2. **Writeback API** - Extend HTTP daemon with delta journal operations
3. **Block device interface** - Add z-layer routing to virtio-blk requests
4. **Compaction service** - Add background delta-to-base merger

### New Components

1. **src/pxc1_container.rs** - PXC1 format implementation
2. **src/quadtree_lut.rs** - Sparse spatial indexing
3. **src/cow_journal.rs** - Append-only delta management
4. **src/codec_selector.rs** - Per-block optimal codec choice

## Migration Strategy

1. **Backward Compatible**: Existing `.nut` containers continue to work
2. **Opt-in**: New containers use `.pxc1` extension and COW journal
3. **Conversion Tool**: Convert existing `.nut` to `.pxc1` format offline
4. **Fallback**: If delta journal corrupted, revert to full re-encode

## Verification Receipts

### Receipt 1: COW Write Performance
- Test: 1000 random 4KB block writes across z-layers
- Metric: <1ms append, <10ms full flush vs 37s re-encode
- Verification: CRC32 exact match after rebase

### Receipt 2: Quadtree Lookup
- Test: Cold-load specific block at (x=2048, y=2048, z=2)
- Metric: <5µs lookup, <1% of container bytes touched
- Verification: O(log n) complexity, no full scan

### Receipt 3: Layer Isolation
- Test: Modify z=2 block, verify z=0,1,3 unchanged
- Metric: Zero cross-layer impact during COW writes
- Verification: SHA256 of non-target layers identical pre/post

## Next Steps

1. Implement Phase 1 (COW Journal) - addresses current writeback bottleneck
2. Prototype codec selection logic
3. Benchmark against current 37s writeback baseline
4. Deploy to test pixel boot, verify persistence model