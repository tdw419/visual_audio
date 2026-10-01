# Golden Image Self-Hosting Build Guide

## Overview

This guide covers the updated `build_desktop_pxc1.sh` script that creates a truly self-hosting golden pixel image. The image contains everything needed for a VM to launch nested pixel VMs without relying on external toolchains or the `/host_zion` mount.

## What Gets Built

### Base Components (Preserved from Original)
- **15GB Ubuntu Desktop**: Ubuntu 24.04 with minimal desktop environment
- **PXC1 Pixel Encoding**: 15GB rootfs encoded into Hilbert pixel frames
- **Cognitive Payload**: Initramfs + LLM weights (if specified)

### New Self-Hosting Components (Added)
- **v2 Pixel Backend**: Pre-compiled `virtio_pixel_backend_v2` at `/usr/local/bin/`
- **QEMU Hypervisor**: `qemu-system-x86_64` for nested virtualization
- **Self-Host Launcher**: `pixel_self_host_nested_vm.sh` for spawning nested VMs
- **Container Fork Tool**: `pixel_fork_container.sh` for instant zero-copy container creation
- **Container Storage**: `/var/lib/pixel_containers/` for managing child containers
- **Documentation**: Complete self-hosting instructions in the image

**Not included, and deliberately so**: a system-wide `systemd-networkd-wait-online`
timeout override. An earlier draft of this guide baked one into
`/etc/systemd/system/` unconditionally, which would change boot behavior for
the *real, everyday interactive desktop* every time it boots - not just
nested test VMs. The slow network-wait during nested boots (QEMU's `-netdev
user` SLIRP stack doesn't signal carrier the way a real NIC does) is real,
but the fix belongs scoped to the specific container being used for nested
testing, not the golden image everyone boots from. See "Network timeout"
under Troubleshooting below for the correctly-scoped, opt-in version.

## Build Requirements

### On the Host System
```bash
# Required packages (typically already installed)
sudo apt-get install \
    qemu-kvm \
    qemu-utils \
    libguestfs-tools \
    virt-customize \
    virt-resize

# Rust toolchain for PXC1 encoder
cargo build --release --manifest-path tools/pxc1/Cargo.toml
```

### Prerequisite Files
```bash
# Source cloud image
ubuntu-24.04-server-cloudimg-amd64.raw

# Cognitive components (optional)
initramfs-cognitive/output/initramfs-cognitive.gz
~/.cache/visual_audio/cognitive/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

# Self-hosting components (built and ready)
systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2
tools/pixel_self_host_nested_vm.sh
tools/pixel_fork_container.sh
```

## Building the Golden Image

### Execution Flow
```bash
cd /host_zion/projects/visual_audio

# Run the build script
./build_desktop_pxc1.sh
```

### Build Phases

**Phase 1: Desktop Image Preparation (15-25 minutes)**
```bash
# Creates 15GB disk
qemu-img create -f raw ubuntu-desktop-15g.raw 15G

# Expands source image
virt-resize --expand /dev/sda1 ubuntu-24.04-server-cloudimg-amd64.raw ubuntu-desktop-15g.raw

# Installs desktop and self-hosting tools
virt-customize -a ubuntu-desktop-15g.raw \
    --run-command 'apt-get install -y ubuntu-desktop-minimal qemu-system-x86 ...'
```

**Phase 2: PXC1 Encoder Compilation (30-60 seconds)**
```bash
cargo build --release --manifest-path tools/pxc1/Cargo.toml
```

**Phase 3: Pixel Encoding (10-20 minutes)**
```bash
tools/pxc1/target/release/pxc1-encode \
    ubuntu_desktop_pxc1_v1 \
    rootfs ubuntu-desktop-15g.raw \
    initramfs initramfs-cognitive/output/initramfs-cognitive.gz \
    gguf ~/.cache/visual_audio/cognitive/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

## What's Inside the Golden Image

### System Tools
```
/usr/local/bin/
├── virtio_pixel_backend_v2      # v2 pixel backend (15MB)
├── pixel_self_host_nested_vm.sh # Unified launcher (22KB)
└── pixel_fork_container.sh       # Zero-copy forker (8KB)

/usr/bin/
└── qemu-system-x86_64            # QEMU hypervisor (pre-installed)

/var/lib/
└── pixel_containers/             # Container storage (777 permissions)
```

### Documentation
```
/usr/local/share/doc/pixel-self-hosting/
└── README.txt                    # Complete usage instructions
```

### Configuration
```
/etc/systemd/system/
├── ssh.service                    # Enabled and running
└── ...                           # Standard Ubuntu desktop services
```

No network-wait timeout override ships in the golden image itself - see the
note above. Apply it per-container when actually needed (Troubleshooting,
"Nested boot is slow to reach login").

## Using the Golden Image

### Booting the Golden Image

`pixel_ubuntu_v2.sh` and `pixel_self_host_nested_vm.sh` serve different
purposes - don't mix them up:
- **`pixel_ubuntu_v2.sh`** boots the real, top-level interactive desktop
  from `ubuntu_desktop_pxc1_v1` (its `CONTAINER_DIR` is hardcoded, it does
  not take a `--container` argument). This is what you actually log into.
- **`pixel_self_host_nested_vm.sh`** is for booting a *nested* VM from
  *inside* an already-running pixel VM. It refuses `ubuntu_desktop_pxc1_v1`
  by name (see Safety Features below) - it is not an alternative way to
  boot the golden image itself.

```bash
./pixel_ubuntu_v2.sh
```

### Self-Hosting Workflow (Inside the VM)

You cannot fork or nest-boot from `ubuntu_desktop_pxc1_v1` directly while
it's the container backing your own running VM - the same live-container
safety check that protects `pixel_self_host_nested_vm.sh` also protects
`pixel_fork_container.sh`'s *source*. Start from a static snapshot instead
(a one-time full copy, made once, reused as the fork source from then on):

```bash
# 0. One-time: make a snapshot to fork from (NOT the live container)
sudo cp -r /path/to/some/idle/pxc1/container /var/lib/pixel_containers/golden_base_snapshot

# 1. Check available tools
which virtio_pixel_backend_v2    # Should be /usr/local/bin/virtio_pixel_backend_v2
which qemu-system-x86_64         # Should be /usr/bin/qemu-system-x86_64

# 2. Read instructions
cat /usr/local/share/doc/pixel-self-hosting/README.txt

# 3. Fork a container (instant, zero-copy)
sudo /usr/local/bin/pixel_fork_container.sh \
    --source /var/lib/pixel_containers/golden_base_snapshot \
    --dest /var/lib/pixel_containers/nested_vm_01

# 4. Boot the nested VM with SSH access (--quick is a headless smoke test
#    that tears itself down after ~20s - it does NOT stay up for you to log
#    into, so don't use it here; use --ssh-port + --serial file instead)
sudo /usr/local/bin/pixel_self_host_nested_vm.sh \
    --container /var/lib/pixel_containers/nested_vm_01 \
    --ssh-port 2224 --serial file

# 5. Access nested VM (from another terminal, while step 4 is still running)
ssh -p 2224 jericho@127.0.0.1    # password: israel

# 6. From inside the nested VM, fork again for Level 2 (fork from
#    nested_vm_01's own snapshot, not from its live root container, for the
#    same reason as step 0)
sudo /usr/local/bin/pixel_fork_container.sh \
    --source /var/lib/pixel_containers/some_idle_container \
    --dest /var/lib/pixel_containers/level2_vm
```

## Container Management

### Instant Forking
```bash
# Fork from any container that ISN'T your current VM's own live root
# container (see the note in "Self-Hosting Workflow" above - the fork tool
# refuses a source that looks actively in use, same rule as the launcher)
sudo pixel_fork_container.sh --source <source_dir> --dest <dest_dir>

# Example: fork a snapshot, not the live golden container
sudo pixel_fork_container.sh \
    --source /var/lib/pixel_containers/golden_base_snapshot \
    --dest /var/lib/pixel_containers/child_vm_$(date +%s)

# Result: footprint scales with frame count, not source size - a few
# hundred KB to low MB range (symlinks + header + empty journal), not the
# multi-GB source
```

### Container Isolation
```bash
# Check container health
ls -la /var/lib/pixel_containers/

# Verify isolation
ls -la /var/lib/pixel_containers/child_vm_01/.pxc1_delta.jnl  # Private journal
ls -la /var/lib/pixel_containers/child_vm_01/frame_*.png | head -5  # Symlinks
```

### Safe Operations
```bash
# Launch against forked container (safe - won't corrupt base)
sudo pixel_self_host_nested_vm.sh --container /var/lib/pixel_containers/child_vm_01

# Compaction is safe (symlink corruption fixed)
curl -X POST http://127.0.0.1:8769/compact_journal  # De-links symlinks automatically
```

## Performance Characteristics

### Build Performance
- **Desktop image prep**: 15-25 minutes (network + package installation)
- **PXC1 encoding**: 10-20 minutes (15GB → pixel frames)
- **Total build time**: 25-45 minutes

### Runtime Performance
- **Nested boot time**: without the network-wait timeout override (see
  Troubleshooting), `systemd-networkd-wait-online.target` / `snapd.seeded.service`
  can stall boot indefinitely (observed: still not resolved after 90-130s,
  no timeout configured on those units by default) - not just "30+ seconds".
  Apply the per-container override below if this matters for your workflow.
- **Container forking**: <10ms (instant symlink creation), footprint scales
  with source frame count rather than source size (low hundreds of KB to a
  few MB, not the multi-GB source)
- **Compaction**: was 47.6s per patched frame on an unaccelerated section
  (whole-section rehash); **712ms measured** on an accelerated section
  (frame_hashes populated - see spec §6a and `pxc1-verify --backfill-frame-hashes`)
  - roughly a 67x improvement, real and re-measurable, not an estimate

### Resource Requirements
- **Golden image**: 15GB disk space
- **Each nested VM**: 1.5-2GB RAM minimum
- **Nesting overhead**: 20-30% per level
- **Practical nesting**: 3-4 levels on current hardware

## Safety Features

### Live Container Protection
```bash
# Hardened safety check in launcher
sudo pixel_self_host_nested_vm.sh --container ubuntu_desktop_pxc1_v1
# ERROR: 'ubuntu_desktop_pxc1_v1' is the known default container...
# Refusing.

# Force override (expert only)
sudo pixel_self_host_nested_vm.sh --container ubuntu_desktop_pxc1_v1 --force
```

### Symlink Corruption Prevention
```bash
# Compaction automatically breaks symlinks
curl -X POST http://127.0.0.1:8769/compact_journal

# Original: frame_00005.png -> ubuntu_desktop_pxc1_v1/frame_00005.png (symlink)
# After compact: frame_00005.png (private file, de-linked)

# Safe to compact without corrupting shared base
```

### COW Journal Isolation
```bash
# Each container has private delta journal
/var/lib/pixel_containers/child_vm_01/.pxc1_delta.jnl  # Isolated
/var/lib/pixel_containers/child_vm_02/.pxc1_delta.jnl  # Isolated

# No journal conflicts between containers
```

## Verification Checklist

### Build Verification
```bash
# 1. Check build output exists
ls -la ubuntu_desktop_pxc1_v1/header.json
ls -la ubuntu_desktop_pxc1_v1/frame_*.png | wc -l  # Should match expected frame count

# 2. Verify golden image size
du -sh ubuntu_desktop_pxc1_v1/  # Should be ~15GB equivalent in pixels

# 3. Check PXC1 integrity
tools/pxc1/target/release/pxc1-verify ubuntu_desktop_pxc1_v1
```

### Boot Verification
```bash
# 1. Boot golden image
./pixel_ubuntu_v2.sh

# 2. Verify self-hosting tools in guest
ssh -p 2222 jericho@127.0.0.1
ls -la /usr/local/bin/virtio_pixel_backend_v2          # Should exist
ls -la /usr/local/bin/pixel_self_host_nested_vm.sh      # Should exist
ls -la /usr/local/bin/pixel_fork_container.sh           # Should exist
ls -la /var/lib/pixel_containers/                       # Should exist

# 3. Verify QEMU availability
which qemu-system-x86_64

# 4. Check documentation
cat /usr/local/share/doc/pixel-self-hosting/README.txt
```

### Self-Hosting Verification
```bash
# Inside the golden VM. Fork from a snapshot, never from your own live root
# container (see "Self-Hosting Workflow" above) - both the launcher and the
# fork tool refuse a live/actively-written source by design.

# 1. Test container forking
sudo pixel_fork_container.sh --source /var/lib/pixel_containers/golden_base_snapshot --dest /tmp/test_fork
ls -la /tmp/test_fork/  # Should have symlinks + header (no delta journal file yet - it self-initializes on first backend launch)

# 2. Quick smoke test (boots headless, polls up to 20s, tears itself down -
#    use this just to confirm the mechanism works, not for interactive access)
sudo pixel_self_host_nested_vm.sh --container /tmp/test_fork --quick
# Should report REACHED_LOGIN (or at least real boot progress) in the verdict

# 3. For actual interactive access, run it WITHOUT --quick instead (stays up
#    until you stop it - run this in its own terminal/background job):
sudo pixel_self_host_nested_vm.sh --container /tmp/test_fork --ssh-port 2224 --serial file
# From another terminal, while the above is still running:
ssh -p 2224 jericho@127.0.0.1
# Should log in successfully

# 4. Test multi-level (from inside the nested VM at step 3, in yet another
#    terminal/session - fork from a snapshot there too, not its own live root).
#    This has NOT actually been run and confirmed in this environment - only
#    Level 0 -> 1 has (see "Not yet verified" in the Summary below).
sudo pixel_fork_container.sh --source /var/lib/pixel_containers/some_snapshot --dest /var/lib/pixel_containers/level2
sudo pixel_self_host_nested_vm.sh --container /var/lib/pixel_containers/level2 --ssh-port 2226 --serial file &
# From another terminal, while the above is still running:
ssh -p 2226 jericho@127.0.0.1  # Should reach Level 2
```

### Zero-Copy Verification
```bash
# 1. Fork a container (from a snapshot, not the live root)
sudo pixel_fork_container.sh --source /var/lib/pixel_containers/golden_base_snapshot --dest /var/lib/pixel_containers/child_vm

# 2. Check initial footprint - scales with frame count, not source size
du -sh /var/lib/pixel_containers/child_vm

# 3. Boot the nested VM WITHOUT --quick (it needs to still be running for
#    the curl calls below - --quick tears the backend down when it returns)
sudo pixel_self_host_nested_vm.sh --container /var/lib/pixel_containers/child_vm --ssh-port 2224 --serial file &
sleep 15   # let it boot and make some real writes

# 4. Force compaction (from another terminal / while step 3 is still running)
curl -X POST http://127.0.0.1:8769/compact_journal

# 5. Verify symlinks de-linked correctly
ls -la /var/lib/pixel_containers/child_vm/frame_*.png | grep "^-"
# Should show some regular files (de-linked), some symlinks (unchanged)

# 6. Verify the fork SOURCE is unchanged (not the live golden container -
# that was never the fork source in this workflow)
sha256sum /var/lib/pixel_containers/golden_base_snapshot/frame_00000.png  # Should match original

# 7. Stop the nested VM from step 3
kill %1  # or: pkill -f "pixel_self_host_nested_vm.sh.*child_vm"
```

## Migration Path

### From Current Setup to Self-Hosting Golden Image

**Phase 1: Prepare (host-side)**
```bash
# 1. Ensure all prerequisites are ready
ls -la systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2
ls -la tools/pixel_self_host_nested_vm.sh
ls -la tools/pixel_fork_container.sh

# 2. Backup current container - this is a full multi-GB copy (the golden
#    image is 15GB+ of raw content). Make sure the HOST filesystem you're
#    running this on has that much headroom before starting; don't run it
#    from inside a guest with a small root disk.
cp -r ubuntu_desktop_pxc1_v1 ubuntu_desktop_pxc1_v1.backup

# 3. Stop any running VMs using ubuntu_desktop_pxc1_v1
# (Critical: virt-customize requires exclusive access, and any backend
# still serving this container while virt-customize/pxc1-encode write to
# it risks corrupting it)
```

**Phase 2: Build (host-side)**
```bash
# 1. Run the updated build script
./build_desktop_pxc1.sh

# 2. Verify build output
ls -la ubuntu_desktop_pxc1_v1/header.json
tools/pxc1/target/release/pxc1-verify ubuntu_desktop_pxc1_v1

# 3. Test boot new golden image (CONTAINER_DIR is hardcoded in the script,
#    it does not take a --container argument)
./pixel_ubuntu_v2.sh
```

**Phase 3: Validate (in new VM)**
```bash
# 1. Boot and verify tools
ssh -p 2222 jericho@127.0.0.1
# Verify all self-hosting components present

# 2. Test self-hosting workflow - fork from a snapshot, never the live
#    root container this VM is itself running from (see "Self-Hosting
#    Workflow" above)
sudo cp -r /some/idle/container /var/lib/pixel_containers/golden_base_snapshot
sudo pixel_fork_container.sh --source /var/lib/pixel_containers/golden_base_snapshot --dest /tmp/test_fork
sudo pixel_self_host_nested_vm.sh --container /tmp/test_fork --ssh-port 2224 --serial file &

# 3. Verify nested access (while the launcher above is still running)
ssh -p 2224 jericho@127.0.0.1
```

**Phase 4: Migrate (optional)**
```bash
# 1. Migrate any important data from old container
# (e.g., COW journal content if needed)

# 2. Switch boot scripts to use new golden image
# Update CONTAINER_DIR in pixel_ubuntu_v2.sh

# 3. Archive old container
mv ubuntu_desktop_pxc1_v1.backup ubuntu_desktop_pxc1_v1.old
```

## Troubleshooting

### Build Issues

**virt-customize fails with "unable to connect"**
```bash
# Solution: Ensure libguestfs is properly configured
sudo apt-get install libguestfs-tools
export LIBGUESTFS_BACKEND=direct
```

**PXC1 encoder not found**
```bash
# Solution: Build PXC1 encoder first
cargo build --release --manifest-path tools/pxc1/Cargo.toml
```

**v2 backend not found during build**
```bash
# Solution: Build v2 backend first
cd systems/virtio_pixel_rs_v2
cargo build --release
cd ../..
```

### Runtime Issues

**Backend not found in guest**
```bash
# Solution: Copy manually to guest
scp systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2 jericho@127.0.0.1:/tmp/
ssh jericho@127.0.0.1
sudo cp /tmp/virtio_pixel_backend_v2 /usr/local/bin/
sudo chmod +x /usr/local/bin/virtio_pixel_backend_v2
```

**Nested boot is slow to reach login**

This is *not* applied golden-image-wide (see the note near the top of this
doc) - apply it to the specific nested-test container/VM instance where you
actually need faster boots, via SSH once that instance is up:
```bash
ssh -p <its ssh port> jericho@127.0.0.1
sudo mkdir -p /etc/systemd/system/systemd-networkd-wait-online.service.d/
echo "[Service]" | sudo tee /etc/systemd/system/systemd-networkd-wait-online.service.d/timeout.conf
echo "TimeoutStartSec=5sec" | sudo tee -a /etc/systemd/system/systemd-networkd-wait-online.service.d/timeout.conf
sudo systemctl daemon-reload
```
This changes that one running instance's own systemd state for its current
boot, not the golden image it was booted from.

**Container forking fails**
```bash
# Solution: Check permissions
sudo chmod 777 /var/lib/pixel_containers
sudo chown root:root /var/lib/pixel_containers

# Verify the SOURCE container you're forking from exists and isn't your own
# live root container (the fork tool refuses that by design)
ls -la /var/lib/pixel_containers/golden_base_snapshot/header.json
```

## Performance Notes

### Compaction Performance - Fixed

**Was**: 47.6s to compact a single patched frame, because
`hash_section_streaming()` re-read and re-hashed every frame of the section
regardless of how many actually changed.

**Now**: 712ms measured for the same single-frame-patch scenario, on a
section with `frame_hashes` populated (spec §6a - see
`docs/PIXEL_CONTAINER_SPEC_V1.md`). The fix: each section can optionally
carry a per-frame SHA-256 list; a patched frame updates just its own entry
(O(1) read-modify-write of `header.json`) instead of re-hashing the whole
section. Verified correct via `pxc1-verify` after compaction, and via unit
tests in `tools/pxc1/src/lib.rs` and `systems/virtio_pixel_rs_v2/src/lib.rs`.

**Containers written before this fix have no `frame_hashes` yet** and keep
using the old (correct, just slower) whole-section rehash path automatically
- nothing breaks. To accelerate an existing container:
```bash
tools/pxc1/target/release/pxc1-verify --backfill-frame-hashes <container_dir>
# One-time full read per section (same cost as one whole-section verify).
# After this, future single-frame compactions on that container are fast.
```
Containers encoded fresh via `pxc1-encode` (including a freshly-built golden
image) get `frame_hashes` automatically - no backfill needed.

### Memory Constraints
**Level 0 VM**: 3.8G RAM (current environment)
**Level 1 VM**: 1.5-2G RAM (recommended minimum)
**Level 2 VM**: 1G RAM (functional desktop)
**Level 3+ VM**: 512M RAM (basic system, no GUI)

**Practical Limit**: 3-4 nesting levels on current hardware

## Future Enhancements

### Golden Image Improvements
1. **Rust Toolchain**: Include for true recursive self-building (a larger
   scope decision than what's built so far - see "Golden Image Requirements"
   in `PIXEL_SELF_HOSTING_ARCHITECTURE.md`)
2. **Network Stack**: Configure bridge networking for better nested VM isolation
3. **Storage**: Add shared storage cluster support for distributed pixel computing

### Self-Hosting Features
1. **Auto-Fork**: Automatic container forking on VM launch
2. **Resource Pool**: Dynamic RAM/CPU allocation based on nesting depth
3. **Network Mesh**: Automatic SSH key distribution for nested cluster
4. **Monitoring**: Built-in monitoring for nested VM health and performance

## Summary

The updated `build_desktop_pxc1.sh` recipe, once actually run, would create
a golden image that:

✅ Contains all tools needed for pixel self-hosting (backend binary, launcher, fork tool)
✅ Enables instant zero-copy container forking
✅ Has fast compaction available (712ms measured, once a container's
   sections have `frame_hashes` - fresh `pxc1-encode` output gets this
   automatically; existing containers need one `--backfill-frame-hashes` pass)
✅ Includes comprehensive documentation
✅ Maintains safety protections (live container checks, symlink corruption prevention)
✅ Can be migrated to without disrupting current workflows

**Not yet verified**: multi-level (Level 2+) nesting has not actually been
run and confirmed in this environment - only Level 0 → Level 1 has. Treat
deeper nesting as architecturally expected to work, not proven, until
someone actually runs it end-to-end (ports listening, real SSH login, real
writes) the way Level 0 → 1 was.

**Next Steps**:
1. Dry-run the fixed workflows in this doc against a real (non-live) test
   container before trusting them for the actual golden-image build
2. Build the golden image when ready (requires no VMs attached to `ubuntu_desktop_pxc1_v1`)
3. Test the full self-hosting workflow in the new image, including an
   actual Level 2 nesting attempt
4. Explore distributed pixel computing with multiple self-hosting VMs

This is preparation for pixel self-hosting capability - the build itself
has not been run yet.