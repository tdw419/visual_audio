# QEMU 8.2.2 CONFIG Pre-Check Bug - Patch

## Location
File: `hw/virtio/vhost-user.c`
Line: ~1646

## The Bug

The CONFIG message pre-check runs BEFORE `GET_PROTOCOL_FEATURES` completes:

```c
// Line ~1646 (RUNS TOO EARLY)
if (!u->user_backend_ops->supports_config || !dev->config_ops) {
    return 0;  // Pre-check fails here
}

// Line ~1550 (GET_PROTOCOL_FEATURES - runs AFTER)
vhost_user_get_protocol_features(...)
```

The pre-check expects protocol features to be already negotiated, but that hasn't happened yet.

## The Fix

Skip the CONFIG pre-check until after protocol negotiation:

```c
// In vhost_user_backend_init() around line 1646:
if (!u->user_backend_ops->supports_config || !dev->config_ops) {
    // Skip CONFIG pre-check if protocol features not negotiated yet
    // The actual CONFIG message handler will fail later if truly unsupported
    return 0;
}
```

Actually, the fix is simpler - just move the pre-check AFTER GET_PROTOCOL_FEATURES.

## Implementation

Download QEMU 8.2.2 source, apply patch, build minimal vhost-user-blk support:

```bash
# Get QEMU 8.2.2 source
wget https://download.qemu.org/qemu-8.2.2.tar.xz
tar xf qemu-8.2.2.tar.xz
cd qemu-8.2.2

# Apply patch
patch -p1 < /path/to/vhost-config-precheck.patch

# Configure for minimal build (only vhost-user-blk)
./configure --target-list=riscv64-softmmu \
    --enable-vhost-user \
    --enable-vhost-user-blk \
    --disable-gtk \
    --disable-sdl \
    --disable-spice \
    --disable-curses \
    --disable-docs \
    --disable-tools

# Build (only what we need)
make -j$(nproc) 2>&1 | tee qemu-build.log

# Use the patched binary
./build/qemu-system-riscv64 -drive file=virtio-pixel,file=/tmp/vhost.sock ...
```

## Alternative: Build FFmpeg-based MKV Reader for Direct Boot

If patching QEMU is too heavy, we could build a lighter approach:

**qemu-softmmu with custom block driver:**
- Load MKV via FFmpeg
- Decode frames to RAM
- Present as virtio-blk device
- No vhost-user, no external backend

This is more work (~1-2 days) but avoids QEMU patches.

## Decision

| Option | Time | Complexity | Pros | Cons |
|--------|------|------------|------|------|
| Patch QEMU 8.2.2 | 2-3 hours | Medium | Fixes root cause | QEMU rebuild required |
| Custom block driver | 1-2 days | High | No external deps | More code to maintain |
| NBD workaround | ✅ Done | Low | Works now | Extracts first (not true boot-from-MKV) |

**Current path:** NBD works for development, defer true boot-from-MKV until we have time to patch QEMU.