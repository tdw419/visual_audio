# Boot from MKV - True Spatial Boot

## Clarification

### What I Built (EXTRACT-THEN-BOOT)
```
MKV (pixels) → extract_spatial_disk.py → raw.img → qemu-nbd → QEMU
```
- Pixels decoded to disk **before** boot
- QEMU reads from raw disk
- ❌ Not true "boot from pixels"

### What We Need (BOOT-FROM-PIXELS)
```
QEMU read request → vhost-user → VirtioPixelServer → decode Hilbert FROM MKV → return bytes
```
- Every sector read decodes **live from MKV pixels**
- No intermediate raw disk
- ✅ True spatial boot

## Why This Matters

The difference is fundamental:

| Aspect | Extract-then-boot | Boot-from-pixels |
|--------|------------------|-----------------|
| Storage | Pixels → disk | Pixels only |
| Decode timing | Pre-boot | Live on-demand |
| Disk usage | 2x (MKV + raw) | 1x (MKV only) |
| Goal achieved | ❌ Storage only | ✅ Execution inside pixels |

## Current Status

**VirtioPixelServer ALREADY implements boot-from-pixels:**

```rust
// backend.rs:1109-1113
let decoded_data = {
    let mut extractor = self.extractor.lock().unwrap();
    extractor.read(offset, data_desc.len as u64)?  // Live decode from MKV
};
```

Every `extractor.read()` triggers live Hilbert decoding from the MKV file.

**The only blocker is QEMU 8.2.2's CONFIG pre-check bug.**

## The Blocker

QEMU 8.2.2's `hw/virtio/vhost-user.c` line ~1646:

```c
// CONFIG pre-check runs BEFORE GET_PROTOCOL_FEATURES
if (!u->user_backend_ops->supports_config || !dev->config_ops) {
    return 0;  // Fails here
}
```

The backend correctly advertises `VHOST_USER_F_PROTOCOL_FEATURES` in `GET_FEATURES`, but QEMU's pre-check expects protocol negotiation to already be complete.

## The Fix

Option A: Patch QEMU 8.2.2 (2-3 hours)
Option B: Wait for QEMU 9.x (may fix it)
Option C: Custom QEMU build (1-2 days)

See `QEMU_CONFIG_PATCH.md` for details.

## Temporary Workaround

The NBD extraction I built (`extract_spatial_disk.py`) works for development but is NOT the goal. It's a workaround, not a solution.

## Session Handoff Summary

**Current state:**
- Backend: ✅ Complete (live decode from MKV working)
- Extraction: ✅ Complete (NBD workaround)
- Boot-from-pixels: ❌ BLOCKED by QEMU 8.2.2

**Next session's task:**
Fix QEMU 8.2.2 CONFIG pre-check bug to enable true boot-from-MKV.

**Files to review:**
- `SPATIAL_BOOT_SESSION_STATUS.md` (session history)
- `systems/virtio_pixel_rs/src/backend.rs` (working backend code)
- `QEMU_CONFIG_PATCH.md` (patch plan)