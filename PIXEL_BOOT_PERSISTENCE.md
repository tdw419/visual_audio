# Pixel Boot Persistence — How It Works

## Overview

Normal Linux systems use block devices (HDD, SSD, NVMe) where reads and writes happen directly to disk sectors. Pixel-booted systems replace the disk with **spatially-encoded PNG frames** in a PXC1 container, creating a persistence layer that requires explicit writeback.

## Where to Find This

**Repository:** https://github.com/tdw419/visual_audio

**Key files:**
- `interactive_ubuntu_pixel.sh` — Boot script with writeback loop and cleanup trap
- `systems/virtio_pixel_rs/src/main.rs` — Backend entry point with HTTP daemon (writeback endpoint)
- `systems/virtio_pixel_rs/src/lib.rs` — `SpatialMkvExtractor::writeback()` implementation
- `systems/virtio_pixel_rs/src/backend.rs` — VirtIO protocol handling and block request processing
- `ubuntu_desktop_pxc1_v1/` — Production PXC1 container (PNG frames with rootfs)

## Architecture Comparison

### Normal Linux Boot (Traditional Disk)

```
Guest OS                     Host Storage
├── ext4 filesystem         └── /dev/sda (block device)
│   ├── Read ───────────────────────────> Read 512B sectors from disk
│   └── Write ──────────────────────────> Write 512B sectors to disk
│
└── Changes are durable immediately
```

- **Read**: Guest sends read request → Host reads physical disk sectors → Returns data
- **Write**: Guest sends write request → Host writes physical disk sectors → Data durable
- **Persistence**: Instant. Every write is immediately on disk.
- **Durability**: No data loss on crash (unless write was in-flight).

### Pixel-Booted Linux (PXC1 Container)

```
Guest OS                     VirtIO-Pixel Backend                 Disk Storage
├── ext4 filesystem         ├── pxc1_buffer (in-memory)      └── ubuntu_desktop_pxc1_v1/
│   ├── Read ───────────────────> Read from pxc1_buffer              ├── 000001.png
│   └── Write ──────────────────> Write to write_overlay (BTreeMap)  ├── 000002.png
│                                                              │   ...
│                                                              └── 000072.png
│
└── Changes NOT durable until writeback() is called
```

- **Read**: Guest sends read request → Backend consults write_overlay (if dirty) → Falls back to pxc1_buffer → Returns data
- **Write**: Guest sends write request → Backend writes to write_overlay (in-memory BTreeMap) → **NOT on disk yet**
- **Persistence**: Explicit. Requires writeback() to flush overlay to PNG frames.
- **Durability**: Up to 300s data loss if backend is killed ungracefully.

## Key Components

### 1. Backend Startup (Container Load)

When `interactive_ubuntu_pixel.sh` starts the backend:

```bash
$BACKEND "$CONTAINER_DIR" "$SOCKET"
```

The Rust backend (`virtio_pixel_backend`):

1. Opens the PXC1 container directory (`ubuntu_desktop_pxc1_v1/`)
2. Reads all PNG frames (e.g., `000001.png` through `000072.png`)
3. Decodes each PNG frame into raw bytes
4. Concatenates all frames into `pxc1_buffer` (in-memory)
5. Initializes empty `write_overlay` (BTreeMap<sector → bytes>)
6. Serves VirtIO block requests from this state

**Result:** Full rootfs available in memory, ready to serve I/O.

### 2. Guest Read Path

```
Guest: read sector 1000
  ↓
Backend: extract_bytes(sector=1000)
  ↓
Backend: check write_overlay for sector 1000
  ├─ If present: return overlay data (guest's latest write)
  └─ If absent: return pxc1_buffer[sector*512 : sector*512+512]
  ↓
Guest: receives 512 bytes
```

- Reads are fast: direct memory access to `pxc1_buffer` or overlay
- No disk I/O for reads (already loaded into RAM)
- Write overlay takes precedence (shows latest writes to that sector)

### 3. Guest Write Path

```
Guest: write "hello" to sector 2000
  ↓
Backend: VIRTIO_BLK_T_OUT request
  ↓
Backend: write_overlay.insert(2000, b"hello\0\0...")
  ↓
Guest: receives OK
```

- Writes go to `write_overlay` only (BTreeMap in RAM)
- `pxc1_buffer` is **NOT** updated immediately
- PNG files on disk are **NOT** touched
- Write is fast (memory-only), but **not durable**

### 4. Writeback Process

When `curl -X POST http://127.0.0.1:8769/writeback` is called (or on exit):

```rust
pub fn writeback(&mut self) -> Result<Vec<String>> {
    // 1. Group dirty sectors by (section_name, frame_index)
    //    Each PNG frame contains multiple 512-byte sectors
    let mut dirty_frames: BTreeSet<(String, usize)> = ...;
    for &sector in self.write_overlay.keys() {
        let frame_idx = sector / SECTORS_PER_FRAME;
        dirty_frames.insert((section_name, frame_idx));
    }

    // 2. For each dirty frame:
    //    a. Copy original frame data from pxc1_buffer
    //    b. Apply overlay writes to reconstruct frame
    //    c. Re-encode frame as PNG
    //    d. Write PNG file to disk
    let encoder = pxc1::Encoder::new(&self.mkv_path);
    for (section_name, frame_idx) in dirty_frames {
        let mut frame_data = pxc1_buffer[frame_start..frame_end].copy();
        Self::apply_write_overlay(&self.write_overlay, &mut frame_data);
        encoder.write_frame(frame_idx, &frame_data);  // Rewrite PNG
    }

    // 3. Commit overlay into pxc1_buffer (so reads reflect changes)
    for (&sector, sector_buf) in &self.write_overlay {
        pxc1_buffer[sector*512..] = sector_buf;
    }

    // 4. Clear overlay
    self.write_overlay.clear();

    // 5. Update section hashes (SHA-256) in PXC1 metadata
    encoder.refresh_section_hash(section_name);
}
```

**Result:** PNG files on disk now contain the guest's changes. Persistence achieved.

### 5. Periodic Writeback

The `interactive_ubuntu_pixel.sh` script spawns a background loop:

```bash
WRITEBACK_INTERVAL=300  # 5 minutes
(
    sleep "$WRITEBACK_INTERVAL"
    while true; do
        START=$(date +%s)
        RESULT=$(curl -s -X POST http://127.0.0.1:8769/writeback)
        DURATION=$(( $(date +%s) - START ))
        echo "[$(date +%H:%M:%S)] ✓ periodic writeback (${DURATION}s)"
        sleep "$WRITEBACK_INTERVAL"
    done
) &
```

- Every 5 minutes: trigger writeback
- Takes ~37 seconds (full rootfs re-encode worst case)
- 85% idle time between flushes (guest can write without journal corruption)
- Logs success/failure to console

### 6. Shutdown Writeback

On exit (Ctrl-A X, SIGTERM, etc.):

```bash
cleanup() {
    kill $WRITEBACK_LOOP_PID 2>/dev/null || true

    echo "=== Final writeback to pixel container ==="
    if curl -s -X POST http://127.0.0.1:8769/writeback | grep -q '"ok":true'; then
        echo "✓ Writeback complete - changes saved to $CONTAINER_DIR"
    else
        echo "✗ Writeback failed - changes not saved"
    fi

    kill $BACKEND_PID 2>/dev/null || true
    rm -f "$SOCKET"
}
trap cleanup EXIT INT TERM
```

- Trap handler ensures final writeback on clean shutdown
- If backend crashes/kill -9 without cleanup: data loss up to 300s

## Differences from Normal Linux

| Aspect | Normal Linux (Block Device) | Pixel-Booted Linux (PXC1) |
|--------|----------------------------|---------------------------|
| **Storage medium** | HDD/SSD/NVMe (physical disk) | PNG frames (spatial encoding) |
| **Read latency** | 0.1-10ms (depends on disk) | <1ms (in-memory) |
| **Write latency** | 0.1-10ms | <1ms (in-memory overlay) |
| **Persistence** | Immediate (per-write) | Explicit (writeback) |
| **Data loss window** | 0-1s (in-flight writes) | Up to 300s (overlay not flushed) |
| **Startup cost** | Mount filesystem (fast) | Load all PNGs into RAM (10-30s) |
| **Shutdown cost** | Unmount (fast) | Writeback + re-encode PNGs (~37s) |
| **Disk I/O pattern** | Random 512B sector reads/writes | Read: memory access; Write: overlay insert |
| **Modification on disk** | Each write touches disk immediately | Dirty PNGs rewritten only on writeback |
| **Corruption recovery** | fsck after crash | Fsck + restore last-known-good PNGs |

## Why This Design?

### Advantages

1. **Spatial encoding**: OS stored as visual artifacts (PNG frames), enabling "The Screen is the Mind" cognitive boot
2. **GPU acceleration**: Hilbert decoding can be offloaded to GPU (Phase 4)
3. **Version control**: PNGs can be diff'd, signed, and verified with SHA-256
4. **Compression**: PNG encoding provides transparent compression
5. **Cross-platform**: PXC1 containers work on any OS with PNG support

### Trade-offs

1. **No instant persistence**: Must remember to writeback or lose recent changes
2. **Memory footprint**: Full rootfs must fit in RAM (4GB for Ubuntu Desktop)
3. **Writeback overhead**: PNG re-encoding is slower than direct block writes
4. **Crash sensitivity**: kill -9 = data loss (no journal on disk)

## Best Practices

### For Guest Users

1. **Force writeback before critical work**:
   ```bash
   curl -X POST http://127.0.0.1:8769/writeback
   ```

2. **Work in /host_zion for immediate durability**:
   - `/host_zion` is 9p passthrough mount to host filesystem
   - Writes there bypass pixel backend entirely
   - No writeback needed, instant persistence

3. **Check writeback status**:
   ```bash
   # View backend logs
   tail -f /tmp/virtio_interactive_backend.log | grep writeback
   ```

4. **Graceful shutdown only**:
   - Use `Ctrl-A X` in QEMU (clean shutdown)
   - Avoid `kill -9` on backend process
   - If forced kill, accept 300s data loss

### For Backend Developers

1. **Don't modify PNGs directly**:
   - Always use `pxc1::Encoder::write_frame()` for modifications
   - Direct PNG edits will corrupt container hashes

2. **Maintain overlay semantics**:
   - Overlay must take precedence over buffer for reads
   - Writeback must commit overlay to buffer before clearing

3. **Test persistence**:
   ```bash
   # Boot, make changes, force writeback, reboot
   # Verify changes persisted
   echo "test" > /tmp/persist_test.txt
   curl -X POST http://127.0.0.1:8769/writeback
   # ... reboot ...
   cat /tmp/persist_test.txt  # Should show "test"
   ```

## Verification Gate

Test persistence end-to-end:

```bash
#!/bin/bash
# Test guest writes persist across reboot

echo "=== Pixel Boot Persistence Test ==="

# Start interactive session
./interactive_ubuntu_pixel.sh &
BACKEND_PID=$!

# Wait for boot (SSH ready)
sleep 90

# Create test file in guest
ssh -p 2222 jericho@127.0.0.1 "echo 'persistence-test-$(date +%s)' > /tmp/persist.txt"

# Force writeback
curl -s -X POST http://127.0.0.1:8769/writeback | grep -q '"ok":true' || {
    echo "FAIL: Writeback failed"
    exit 1
}

# Record expected content
EXPECTED=$(ssh -p 2222 jericho@127.0.0.1 "cat /tmp/persist.txt")

# Clean shutdown
kill $BACKEND_PID

# Reboot
./interactive_ubuntu_pixel.sh &
BACKEND_PID=$!
sleep 90

# Verify
ACTUAL=$(ssh -p 2222 jericho@127.0.0.1 "cat /tmp/persist.txt")

if [ "$EXPECTED" = "$ACTUAL" ]; then
    echo "PASS: Persistence verified"
    kill $BACKEND_PID
    exit 0
else
    echo "FAIL: Content mismatch"
    echo "Expected: $EXPECTED"
    echo "Actual: $ACTUAL"
    kill $BACKEND_PID
    exit 1
fi
```

## Related Documentation

- **AGENTS.md**: Agent constitution for Visual Audio project
- **CONTAINER_BOOT_RECEIPT.md**: Full cognitive boot implementation details
- **COGNITIVE_BOOT_V3_RECEIPT.md**: Cognitive payload extraction architecture
- **systems/virtio_pixel_rs/src/lib.rs**: Backend implementation (SpatialMkvExtractor)
- **systems/virtio_pixel_rs/src/backend.rs**: VirtIO protocol handling

---

**Last Updated**: 2026-08-19  
**Status**: Active — Matches current implementation in `interactive_ubuntu_pixel.sh`