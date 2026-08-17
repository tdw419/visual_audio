# Cognitive Container Boot - Session Fixes & Status

## Fixes Applied This Session

### 1. Backend Off-By-One Frame Capacity (lib.rs line 204)

**Problem**: Backend reported disk size as `frames * bytes_per_frame`, but frame 0 is metadata-only. Guest reads at end of disk requested frame 283 (doesn't exist), causing I/O errors.

**Fix**:
```rust
// Old (WRONG):
decoded_size = frames * bytes_per_frame;

// New (CORRECT):
decoded_size = frames.saturating_sub(1) * bytes_per_frame;
```

### 2. Backend Metadata File Lookup (lib.rs meta.json path)

**Problem**: `Path::with_suffix('.nut.meta.json')` was REPLACING `.nut` with `.nut.meta.json`, resulting in `ubuntu_cognitive.meta.json.nut` instead of `ubuntu_cognitive.nut.meta.json`. Backend never found metadata and defaulted to 7GB.

**Fix**: Proper suffix handling in code (already fixed)

### 3. Initramfs Offset Mismatch

**Problem**: Initramfs hardcoded offset 3758096384 (start of cognitive payload), but encoder writes metadata AFTER initramfs + GGUF (~914MB into cognitive payload).

**Fix**: Updated `initramfs-cognitive/init`:
```bash
# Calculate offset: rootfs + initramfs + gguf = 3758096384 + 289738492 + 668859375
COGNITIVE_OFFSET_BYTES=4716694251
```

## Current Status

### ✅ What Works
- Backend starts and accepts vhost-user connections
- QEMU boots Linux kernel with cognitive initramfs
- No more OSError: [Errno 5] I/O errors
- Memory-optimized encoder (62MB RSS vs 5-6GB)

### ❌ What's Blocked
- **Container encoding**: Incomplete - stops at ~215 frames (needs 283)
- **Disk space**: / partition 87% full (4.7GB available), encoding needs 14GB+ temporary space
- **Metadata not found**: Container truncated before frame 282 where metadata lives

## Root Cause

The encoder is being killed or hitting disk space before completing all 283 frames. Each attempt produces:
- Expected: 283 frames (4.42GB decoded)
- Actual: ~215 frames (truncated)

The FFmpeg pipeline needs ~3-4x temporary space during encoding.

## Solution Path

**Option A**: Free disk space and re-encode
1. Delete large files (test images, old containers)
2. Target ~20GB free on /
3. Re-encode complete container
4. Verify: `ffprobe -count_frames ubuntu_cognitive_vac2_v3_full.nut` → 283

**Option B**: Stream directly to external disk
- Encode to /home/jericho/projects/zion (separate partition, 42GB free)

**Option C**: Alternative backend approach
- Use GPU acceleration in backend (extract directly to memory, no temp files)
- Requires WebGL context setup

## Quick Test (With Current Incomplete Container)

```bash
chmod +x boot_cognitive_container_fixed.sh
./boot_cognitive_container_fixed.sh
```

Expected: Boot reaches "Could not find cognitive metadata" (correct - metadata at frame 282, truncated)

## Files Modified

1. `systems/virtio_pixel_rs/src/lib.rs` - Fixed decoded_size calculation
2. `initramfs-cognitive/init` - Updated COGNITIVE_OFFSET_BYTES
3. `boot_cognitive_container_fixed.sh` - New test script with verification

## Documentation Created

- `debug_metadata_offset.py` - Calculates correct metadata offset
- `verify_metadata_in_container.py` - Checks metadata presence in container

## Next Session Priorities

1. Clear 15GB+ disk space
2. Re-encode complete 283-frame container
3. Verify: ffprobe shows 283 frames
4. Test full cognitive boot sequence
5. Verify LLM extraction succeeds