# Pixel Self-Hosting Architecture for v2

## Overview

This document describes the pixel self-hosting architecture that enables a pixel-booted VM to boot nested pixel VMs using the virtio_pixel_backend_v2 driver.

## Current State

✅ **Proven Working Components:**
- Nested KVM works inside pixel-booted VMs
- virtio_pixel_backend_v2 runs successfully in guest
- vhost-user-blk communication between nested VMs works
- COW journal writes (dedup, zstd compression) function correctly
- Systemd boot through basic.target → late-stage service startup

✅ **Available Tools:**
- `tools/pixel_self_host_nested_vm.sh` - The single consolidated launcher (v1/v2 selection,
  safety checks, `--quick` smoke-test preset, SSH/9p options). Two other scripts that
  accumulated during self-hosting bring-up (`selfhost_launcher.sh`, `v2_selfhost_test.sh`)
  were merged into this one and no longer exist.

## Self-Hosting Architecture

### 1. Resource Allocation

**VM Hierarchy:**
```
Host System (Physical)
├─ Level 0 VM (you are here) - 3.8G RAM, port 2222 SSH
│  └─ Level 1 VM (nested) - 1.5G RAM, port 2224 SSH
│     └─ Level 2 VM (double-nested) - 512M RAM, port 2226 SSH
│        └─ ... (theoretically unlimited levels)
```

**Resource Constraints:**
- Each level needs: ~1.5G RAM minimum for Ubuntu desktop
- KVM overhead: ~100-200MB per level
- Backend overhead: ~50-100MB per level
- **Practical limit**: 3-4 levels deep on current hardware

### 2. Backend Selection

**v2 Backend (Recommended for self-hosting):**
- Location: `/host_zion/projects/visual_audio/systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2`
- Advantages for self-hosting:
  - COW journal with instant writes (<1ms)
  - HTTP API for journal management
  - ZSTD compression for efficient storage
  - Better resource efficiency
- Start command: `./virtio_pixel_backend_v2 <container_dir> <socket>`

**v1 Backend (Legacy):**
- Location: `/host_zion/projects/visual_audio/systems/virtio_pixel_rs/target/release/virtio_pixel_backend`
- Simpler but less efficient for self-hosting
- No COW journal or HTTP API

### 3. Container Management

**Golden Image Requirements (scope: recursive capability, not self-build):**
The chosen scope is "any VM can boot another VM using its own native tools" - it does
*not* require the guest to be able to rebuild the backend from source. So the golden
image needs:
1. `qemu-system-x86_64` (already present - it's apt-installed in the desktop image today)
2. Pre-compiled `virtio_pixel_backend_v2` at `/usr/local/bin/` (not yet baked in - the
   launcher currently falls back to the repo-relative build under `systems/virtio_pixel_rs_v2/`,
   reached via the `/host_zion` 9p share)
3. `tools/pixel_self_host_nested_vm.sh` at `/usr/local/bin/` (or callable via the share)

A Rust/Cargo toolchain and PXC1 encoder tools are only needed if you later want "true
recursive self-build" (a VM that can rebuild the backend and re-encode containers from
scratch) - a larger, separate scope decision, not required for what's built so far.

**Container Strategy:**
- **Live container**: `ubuntu_desktop_pxc1_v1` - currently running this VM
- **Snapshot container**: `ubuntu_desktop_pxc1_v1_snapshot` - for safe testing
- **Test container**: Any fresh PXC1 container for nested booting

**Container Isolation:**
Each nested VM needs its own container to avoid COW journal conflicts:
```
/containers/
├─ ubuntu_desktop_pxc1_v1              # Level 0 (this VM)
├─ ubuntu_desktop_pxc1_v1_nested       # Level 1  
├─ ubuntu_desktop_pxc1_v1_nested2      # Level 2
└─ ...
```

### 4. Networking Stack

**SSH Port Strategy:**
- Level 0: 2222 (parent host → this VM)
- Level 1: 2224 (this VM → nested VM)
- Level 2: 2226 (nested VM → double-nested)
- Pattern: 2222 + (2 * level)

**Network Access:**
```bash
# Access nested VM from host
ssh -p 2224 jericho@127.0.0.1

# Access from this VM  
ssh -p 2224 jericho@127.0.0.1

# Access double-nested
ssh -p 2226 jericho@127.0.0.1
```

### 5. Memory Sharing Architecture

**vhost-user Memory Backend:**
```bash
# Backend creates shared memory region
-object memory-backend-file,share=on,size=1G,mem-path=/dev/shm/shared,id=ram

# QEMU maps the same region for zero-copy DMA
-machine q35,memory-backend=ram -object memory-backend-file,share=on,size=1G,mem-path=/dev/shm/shared,id=ram -m 1G
```

**Benefits:**
- Zero-copy I/O between backend and nested VM
- Reduced memory overhead
- Better performance for block operations

## Self-Hosting Workflows

### Quick Test (Inside This VM)

```bash
# Small/fast smoke test: 512M RAM, 1 vCPU, headless, auto-torn-down.
# Defaults to the ubuntu_desktop_pxc1_v1_snapshot container if --container is omitted.
cd /host_zion/projects/visual_audio
./tools/pixel_self_host_nested_vm.sh --quick
```

### Full Nested Boot (Interactive)

```bash
# Boot nested Ubuntu VM in the foreground with serial on this terminal
cd /host_zion/projects/visual_audio
./tools/pixel_self_host_nested_vm.sh \
    --container ubuntu_desktop_pxc1_v1_snapshot \
    --ram 2G --cpus 2 --ssh-port 2224 --serial stdio

# From another terminal/session:
ssh -p 2224 jericho@127.0.0.1
```

### Production Self-Hosting

```bash
# Headless, logged, with SSH access and the project share mounted in the guest
cd /host_zion/projects/visual_audio
./tools/pixel_self_host_nested_vm.sh \
    --container ubuntu_desktop_pxc1_v1_snapshot \
    --queues 2 \
    --ram 2G \
    --cpus 2 \
    --ssh-port 2224 \
    --share \
    --serial file
```

### Multi-Level Self-Hosting

```bash
# Level 0: Boot this VM (already done)
# Level 1: Boot nested VM from here
./tools/pixel_self_host_nested_vm.sh --container ubuntu_desktop_pxc1_v1_snapshot \
    --ssh-port 2224 --serial file

# Level 2: From inside the nested VM, boot another - pick a container that ISN'T
# the one currently backing level 1's own root fs (same live-container rule as
# always). --share is required so the nested guest can even reach this repo.
ssh -p 2224 jericho@127.0.0.1
cd /host_zion/projects/visual_audio   # only reachable if level 1 was booted with --share
./tools/pixel_self_host_nested_vm.sh --container <some other container> \
    --ssh-port 2226 --serial file

# Level 3: Repeat from double-nested VM
ssh -p 2226 jericho@127.0.0.1
# ... continue pattern
```

Note: only Level 0 -> Level 1 nesting has actually been run and verified end-to-end
(see "Current State" above). Level 2+ is architecturally the same operation repeated,
but hasn't itself been executed and confirmed - treat it as expected-to-work, not proven.

## Making the Golden Image Self-Hosting Ready

### Required Components

1. **QEMU Installation:**
```bash
# In the golden image build process
sudo apt-get install qemu-kvm qemu-system-x86
```

2. **Backend Binary:**
```bash
# Build and install v2 backend in golden image
cd systems/virtio_pixel_rs_v2
cargo build --release
sudo cp target/release/virtio_pixel_backend_v2 /usr/local/bin/
sudo chmod +x /usr/local/bin/virtio_pixel_backend_v2
```

3. **Self-Hosting Tools:**
```bash
# Install the launcher in golden image
cp tools/pixel_self_host_nested_vm.sh /usr/local/bin/
chmod +x /usr/local/bin/pixel_self_host_nested_vm.sh
```

4. **Container Storage:**
```bash
# Reserve space for nested containers
mkdir -p /var/lib/pixel_containers
chmod 777 /var/lib/pixel_containers
```

### Golden Image Update Process

**This must be done host-side, with no VM attached to `ubuntu_desktop_pxc1_v1`.**
`build_desktop_pxc1.sh` builds a raw disk via `virt-resize`/`virt-customize` (libguestfs,
host-only tooling - not runnable from inside a guest), then `pxc1-encode` writes its
output straight into `ubuntu_desktop_pxc1_v1` - the exact directory that is normally
live-serving a running VM's root filesystem. Running this while any VM has that
container open risks corrupting it. There is no CLI argument to redirect the output
directory - `OUTPUT_DIR` is hardcoded in the script - so either edit the script to
target a fresh directory, or make certain nothing is using the live one first.

```bash
# On host system, with no VM running against ubuntu_desktop_pxc1_v1
cd /host_zion/projects/visual_audio

# Back up current container first (cheap insurance, not a substitute for
# making sure nothing has it open)
cp -r ubuntu_desktop_pxc1_v1 ubuntu_desktop_pxc1_v1_before_selfhosting

# Edit build_desktop_pxc1.sh's virt-customize invocation to add:
#   --copy-in systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2:/usr/local/bin/
#   --copy-in tools/pixel_self_host_nested_vm.sh:/usr/local/bin/
#   --chmod 0755:/usr/local/bin/virtio_pixel_backend_v2
#   --chmod 0755:/usr/local/bin/pixel_self_host_nested_vm.sh
# Do NOT also mask systemd-networkd-wait-online/snapd system-wide here - that
# changes real interactive-desktop boot behavior, not just nested-test boot
# behavior. If the network-wait stall needs fixing, scope it to nested-guest
# boots specifically (e.g. a kernel cmdline flag or a systemd drop-in shipped
# only in nested-test containers), not the golden image everyone boots from.

# Rebuild (writes to ubuntu_desktop_pxc1_v1 - see warning above)
./build_desktop_pxc1.sh
```

## Safety and Isolation

### COW Journal Conflicts

**Problem:** Multiple backends writing to same COW journal corrupts data.

**Solution:** Each nested VM uses its own container:
```bash
# Wrong: two backends on same container
Backend 1: virtio_pixel_backend_v2 ubuntu_desktop_pxc1_v1
Backend 2: virtio_pixel_backend_v2 ubuntu_desktop_pxc1_v1  # CONFLICT!

# Correct: each backend has its own container
Backend 1: virtio_pixel_backend_v2 ubuntu_desktop_pxc1_v1
Backend 2: virtio_pixel_backend_v2 ubuntu_desktop_pxc1_v1_snapshot
```

### Safety Checks

The `pixel_self_host_nested_vm.sh` includes automatic safety checks:

1. **Name-based check:** Refuses `ubuntu_desktop_pxc1_v1` (known live container)
2. **Growth-based check:** Monitors COW journal growth for 6 seconds
3. **Force override:** `--force` flag for expert users

### Resource Limits

**Memory Constraints:**
```bash
# Check available memory in this VM
free -h

# Calculate safe nested allocation
# Rule: Leave at least 1.5G for parent VM
TOTAL_MEM=$(free -g | grep '^Mem:' | awk '{print $2}')
SAFE_NESTED=$((TOTAL_MEM - 2))  # Leave 2G for parent
```

**KVM Limits:**
```bash
# Check KVM availability
lsmod | grep kvm

# Check nested KVM
kvm-ok  # Inside VM to verify nested KVM support
```

## Performance Monitoring

### Self-Hosting Metrics

Monitor the self-hosting stack using the monitoring system we just created:

```bash
# Start monitoring in this VM
python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/level0_monitoring.json

# Start nested VM
./tools/pixel_self_host_nested_vm.sh --container ubuntu_desktop_pxc1_v1_snapshot \
    --ssh-port 2224 --share --serial file

# From inside nested VM, monitor its I/O
ssh -p 2224 jericho@127.0.0.1
python3 /host_zion/projects/visual_audio/tools/vm_pixel_monitor.py --duration 60 --output /tmp/level1_monitoring.json

# Analyze both levels
python3 tools/pixel_driver_optimizer.py --input /tmp/level0_monitoring.json
python3 tools/pixel_driver_optimizer.py --input /tmp/level1_monitoring.json
```

Note: `vm_pixel_monitor.py`'s diskstats fallback (used unless run with `sudo`) does not
produce real amplification/hot-sector/pattern numbers - see that tool's own fix history.
Use `sudo` for a meaningful nested-vs-host comparison.

### Expected Performance

The specific throughput/overhead numbers that used to be here were illustrative
placeholders, not measurements from an actual monitoring run - removed rather than left
looking like real data. Use the monitoring workflow above to get real baseline vs.
nested numbers instead of trusting estimated figures.

## Troubleshooting

### Common Issues

**1. Backend fails to start:**
```bash
# Check if v2 backend exists
ls -la systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2

# Check backend logs (pixel_selfhost_backend_<pid>.log, printed at launch time
# and also in the --quick verdict output)
tail -20 /tmp/pixel_selfhost_backend_*.log

# Try v1 fallback
./tools/pixel_self_host_nested_vm.sh --backend v1 --container <dir>
```

**2. Nested VM doesn't boot:**
```bash
# Check KVM availability
lsmod | grep kvm_intel   # or kvm_amd
cat /sys/module/kvm_intel/parameters/nested   # should be Y for nesting

# Check socket connection (path is printed at launch, defaults to
# /tmp/pixel-selfhost-<pid>.sock unless --socket was given)
ls -la /tmp/pixel-selfhost-*.sock

# Check QEMU serial log (only written with --serial file)
tail -20 /tmp/pixel_selfhost_guest_*.log
```

**3. COW journal corruption:**
```bash
# Stop all backends
pkill -9 virtio_pixel_backend

# Check journal status
curl http://127.0.0.1:8769/journal_stats

# Force writeback and compaction
curl -X POST http://127.0.0.1:8769/writeback
curl -X POST http://127.0.0.1:8769/compact_journal
```

### Debug Mode

```bash
# Enable verbose backend logging
RUST_LOG=debug ./tools/pixel_self_host_nested_vm.sh --container <dir> --serial file
```

## Future Enhancements

### Self-Replicating Pixel VMs

**Concept:** A pixel VM that can create exact copies of itself.

**A real constraint this needs to work around:** a running guest has no way to
introspect "which PXC1 container am I backed by" - `readlink -f /` just resolves to
`/`, since PXC1/vhost-user-blk is entirely host/backend-side; the guest only ever sees
an ordinary block device (`/dev/vda`). The container's identity has to be handed to
the guest explicitly (e.g. baked into the image at build time, passed via kernel
cmdline, or looked up through the backend's own HTTP API - `base_container_hash` from
`GET /journal_stats` at least identifies *which* container is currently backing you,
even if it can't give you the container's directory path).

**Full-copy approach (safe today):**
```bash
#!/bin/bash
SOURCE_CONTAINER="/host_zion/projects/visual_audio/ubuntu_desktop_pxc1_v1_snapshot"  # passed in explicitly
NEW_CONTAINER="/var/lib/pixel_containers/copy_$(date +%s)"

cp -r "$SOURCE_CONTAINER" "$NEW_CONTAINER"

# Boot the copy
./tools/pixel_self_host_nested_vm.sh --container "$NEW_CONTAINER"
```

**Zero-copy fork (now safe to build):** `Encoder::write_frame` (`tools/pxc1/src/lib.rs`)
was fixed to break a symlinked frame into a private file before writing, instead of
following the link and mutating whatever it points at. That means a child container
made of symlinks into a shared base's PNG frames, plus its own private
`.pxc1_delta.jnl`, can now safely call `/compact_journal` without corrupting the base
or its siblings - each touched frame silently de-links into a private copy on first
write, and untouched frames keep costing zero extra disk space. `tools/pixel_fork_container.sh`
implementing this (symlink frames + copy header.json + empty delta journal, per the
original design) hasn't been written yet - the fix just removes the corruption risk
that was blocking it.

### Distributed Pixel Computing

**Concept:** Multiple pixel VMs coordinating through a shared pixel storage backend.

**Architecture:**
```
Pixel Network Node 1 ─┐
                     ├── Shared Pixel Storage Cluster
Pixel Network Node 2 ─┤   (COW journal with distributed writeback)
                     │
Pixel Network Node 3 ─┘
```

## Summary

The pixel self-hosting architecture is **proven working** for:
- ✅ Nested KVM virtualization
- ✅ v2 backend execution in guests
- ✅ COW journal persistence
- ✅ Level 0 → Level 1 nesting, verified end-to-end
- ✅ Safety checks and isolation (hardened after a real false-negative was caught in testing)
- ✅ Zero-copy container forking is now safe against corrupting the shared base (see
  `Encoder::write_frame` in `tools/pxc1/src/lib.rs` - it breaks a symlinked frame into a
  private file before writing, instead of following the link)

Not yet done:
- Level 2+ nesting (architecturally identical, just not actually run)
- Golden image update (binary/script bake-in) - deliberately not run yet; it writes to
  the live `ubuntu_desktop_pxc1_v1` container and must be done host-side with no VM
  attached to it
- `tools/pixel_fork_container.sh` (the zero-copy branching tool itself) - the underlying
  corruption risk is fixed, but the tool hasn't been written

**Next Steps:**
1. Update golden image with self-hosting components (host-side, VM detached)
2. Build `tools/pixel_fork_container.sh` now that symlink-based forking is safe
3. Actually run and verify Level 2+ nesting before claiming it works

This creates a **complete pixel computing ecosystem** where pixel VMs can bootstrap and coordinate other pixel VMs, enabling distributed pixel-native computing systems.