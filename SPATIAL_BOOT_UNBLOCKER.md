# Spatial Boot Unblocker — QEMU 8.2.2 Workaround Plan

## Blocker Summary

**Issue:** QEMU 8.2.2's vhost-user-blk has a CONFIG pre-check bug that runs before `GET_PROTOCOL_FEATURES` negotiation completes, causing the virtio-pixel backend to fail.

**Error Messages:**
```
qemu-system-riscv64: Failed to set msg fds.
qemu-system-riscv64: vhost VQ 0 ring restore failed: -22: Invalid argument (22)
```

**Root Cause:** In `hw/virtio/vhost-user.c`, the CONFIG message pre-check runs at line ~1646, but GET_PROTOCOL_FEATURES doesn't complete until line ~1550. The pre-check expects protocol features to be already negotiated.

## Workaround Options

### Option A: NBD-based Boot (IMMEDIATE PATH — 30 min)

**Approach:** Use qemu-nbd to serve extracted disk image via Network Block Device protocol.

**Advantages:**
- ✅ Bypasses vhost-user entirely (no protocol negotiation)
- ✅ Standard QEMU NBD support (built-in, stable)
- ✅ Same virtio-blk driver in guest (no guest changes)
- ✅ Can still boot from MKV (extract on-demand)

**Implementation:**

```bash
#!/bin/bash
# nbd_boot_spatial.sh

MKV_PATH="/home/jericho/projects/zion/projects/visual_audio/test_data/spatial_boot/alpine_minimal.mkv"
NBD_SOCKET="/tmp/spatial-nbd.sock"

# Extract first sector from MKV to verify
python3 -c "
from systems.virtio_pixel_rs.src.lib import SpatialMkvExtractor
extractor = SpatialMkvExtractor(mkv_path='$MKV_PATH')
data = extractor.read(0, 512)
open('/tmp/mbr.bin', 'wb').write(data)
print('MBR extracted:', data.hex()[:16])
"

# Start qemu-nbd with raw image
qemu-nbd --socket=$NBD_SOCKET --format=raw --read-only alpine_minimal.raw

# Boot QEMU from NBD
qemu-system-riscv64 \
    -nographic \
    -machine virt \
    -cpu sifive-u54 \
    -m 512M \
    -drive file=nbd+unix://$NBD_SOCKET,if=virtio,index=0,bootindex=0 \
    -kernel /path/to/kernel \
    -initrd /path/to/initramfs \
    -append "root=/dev/vda1 console=ttyS0"
```

**Why This Works:**
- NBD uses `file=nbd+unix://...` syntax (not vhost-user)
- QEMU treats NBD as a regular block device (no vhost-user handshake)
- virtio-blk-pci driver handles NBD transparently

**Timeline:**
- [ ] Extract MKV to raw image (15 min)
- [ ] Test NBD boot with Alpine (10 min)
- [ ] Verify spatial boot complete (5 min)

---

### Option B: Direct virtio-blk Socket Backend (ALTERNATIVE — 2 hours)

**Approach:** Replace vhost-user-blk with a custom virtio-blk socket backend that doesn't use vhost-user protocol.

**Advantages:**
- ✅ Zero QEMU patches needed
- ✅ Pure userspace socket protocol (simpler)
- ✅ Still serves from MKV directly (no extraction)

**Disadvantages:**
- ⚠️ Need to implement virtio-blk device emulation (complex)
- ⚠️ Not using QEMU's vhost infrastructure (slower)
- ⚠️ More code to maintain

**Not Recommended:** Option A is faster and achieves same goal.

---

### Option C: Patch QEMU (LONG TERM — 4-6 hours)

**Approach:** Apply patch to QEMU 8.2.2 source, recompile.

**Advantages:**
- ✅ Fixes root cause
- ✅ vhost-user works as intended

**Disadvantages:**
- ⚠️ Requires QEMU recompilation (30-60 min)
- ⚠️ Patch might break with QEMU updates
- ⚠️ System-wide change (affects other VMs)

**Recommended Only If:** Option A fails or NBD proves insufficient.

---

## Recommended Path: Option A (NBD-based Boot)

### Step 1: Create NBD Extraction Tool (15 min)

Create `tools/mkv_to_nbd.sh`:
```bash
#!/bin/bash
set -e

MKV_PATH="$1"
RAW_PATH="$2"

echo "Extracting MKV to raw disk: $MKV_PATH → $RAW_PATH"

# Use SpatialMkvExtractor to extract all sectors
python3 <<EOF
from systems.virtio_pixel_rs.src.lib import SpatialMkvExtractor
extractor = SpatialMkvExtractor(mkv_path='$MKV_PATH')

# Get total size
total_size = extractor.decoded_size
sectors = total_size // 512

print(f"Extracting {sectors} sectors ({total_size} bytes)...")

with open('$RAW_PATH', 'wb') as f:
    # Extract in 1MB chunks
    chunk_size = 1024 * 1024
    offset = 0
    while offset < total_size:
        to_read = min(chunk_size, total_size - offset)
        data = extractor.read(offset, to_read)
        f.write(data)
        offset += to_read

        if offset % (10 * 1024 * 1024) == 0:
            print(f"  Progress: {offset} / {total_size} bytes")

print(f"✓ Extraction complete: {RAW_PATH}")
EOF
```

### Step 2: Boot Alpine via NBD (10 min)

Create `systems/virtio_pixel_rs/boot_alpine_nbd.sh`:
```bash
#!/bin/bash
set -e

RAW_PATH="/tmp/alpine_minimal.raw"
NBD_SOCKET="/tmp/spatial-nbd.sock"

# Extract from MKV if needed
if [ ! -f "$RAW_PATH" ]; then
    bash tools/mkv_to_nbd.sh \
        test_data/spatial_boot/alpine_minimal.mkv \
        "$RAW_PATH"
fi

# Start NBD server
echo "Starting NBD server..."
qemu-nbd --socket=$NBD_SOCKET --format=raw "$RAW_PATH" &
NBD_PID=$!

sleep 2

# Boot QEMU
echo "Booting QEMU from NBD..."
timeout 45 qemu-system-riscv64 \
    -nographic \
    -machine virt \
    -cpu rv64 \
    -m 512M \
    -drive file=nbd+unix://$NBD_SOCKET,if=virtio,index=0,bootindex=0 \
    -kernel boot_images/alpine_Image \
    -initrd boot_images/alpine_initrd \
    -append "console=ttyS0 earlycon root=/dev/vda rw" \
    -no-reboot

# Cleanup
kill $NBD_PID
rm -f $NBD_SOCKET
```

### Step 3: Verify and Update Status (5 min)

Run the script and check:
1. NBD socket created successfully
2. QEMU boots without vhost-user errors
3. Alpine mounts filesystem
4. Shell prompt appears

Update SPATIAL_BOOT_SESSION_STATUS.md:
```markdown
## Blocker Status

**PREVIOUS BLOCKER:** QEMU 8.2.2 vhost-user CONFIG pre-check bug

**STATUS:** ✅ RESOLVED via NBD workaround (Option A)

**Resolution:**
- Implemented NBD-based boot path
- Bypasses vhost-user protocol entirely
- Same spatial MKV → extraction → NBD → QEMU flow
- Verified Alpine boot complete

**Files:**
- tools/mkv_to_nbd.sh
- systems/virtio_pixel_rs/boot_alpine_nbd.sh

**Next Steps:**
- [ ] Test Ubuntu Desktop boot via NBD
- [ ] Benchmark NBD vs vhost-user performance
- [ ] Document NBD boot pattern in LINUX_BOOT_INTEGRATION.md
```

---

## Long-Term Considerations

### Keep vhost-user Backend?

**Yes, but defer:**
- vhost-user is still valuable for production (zero-copy, high performance)
- Once we have NBD working, can revisit vhost-user QEMU patch (Option C)
- Or wait for QEMU 9.x which may have fixed the bug

### Alternative: virtio-blk-chardev

**Another Option:** Use `-chardev socket` with virtio-blk:
```bash
qemu-system-riscv64 \
    -chardev socket,id=blk0,path=/tmp/virtio.sock \
    -device virtio-blk-device,chardev=blk0
```

**Status:** Not tested yet — NBD is known working, try chardev if NBD fails.

---

## Decision Matrix

| Criterion | Option A (NBD) | Option B (Socket) | Option C (Patch QEMU) |
|-----------|---------------|------------------|----------------------|
| Time to unblock | **30 min** | 2 hours | 4-6 hours |
| Complexity | Low | High | Medium |
| Stability | High | Unknown | Medium |
| Spatial MKV support | ✓ (extract) | ✓ (direct) | ✓ (direct) |
| Performance | Medium | Medium | High |
| Maintenance | Low | High | High |

**Winner:** Option A (NBD) — fastest path to unblocked development

---

## Action Plan

1. ✅ Create this document (DONE)
2. ⏭️ Implement mkv_to_nbd.sh (15 min)
3. ⏭️ Implement boot_alpine_nbd.sh (5 min)
4. ⏭️ Test Alpine boot (10 min)
5. ⏭️ Update SPATIAL_BOOT_SESSION_STATUS.md (5 min)
6. ⏭️ Commit and tag: `feat(spatial-boot): unblock via NBD workaround`

**Total Time:** ~40 minutes

**Result:** Spatial boot unblocked, development can continue.