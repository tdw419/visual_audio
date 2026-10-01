# V4 Ubuntu Boot Verification — Receipt

**Date**: 2026-08-23
**Session**: V4 Boot Login Verification
**Status**: Login prompt reached; interactive verification blocked by cmdline allocation bug

---

## What Was Verified

### Core Achievement: V4 Bootloader Successfully Boots Ubuntu 24.04

**Evidence** (from earlier successful run, captured in serial log):
```
Ubuntu 24.04.4 LTS ubuntu ttyS0

ubuntu login:
```

**Chain Verified**:
1. V4 bootloader (`bootloader_uefi_v4.efi`) loads from pixel-encoded V4 container
2. Kernel decoded from PNG + loaded into memory
3. Initramfs decoded from PNG + loaded into memory
4. Rootfs mounted via virtio-blk (separate raw disk image)
5. Ubuntu 24.04 Server boots through systemd
6. Serial console (ttyS0) functional
7. System reaches multi-user.target
8. Login prompt displayed

**Configuration**:
- Kernel: Ubuntu 24.04 standard kernel (from cloud image)
- Initramfs: Pixel-encoded (V4 format)
- Rootfs: `ubuntu-24.04-server-cloudimg-amd64.raw` via virtio-blk-pci
- Serial: ttyS0 @ 115200 baud
- Console: `console=ttyS0,115200 earlyprintk=serial,ttyS0,115200 earlycon=uart8250,io,0x3f8`

---

## Bugs Discovered and Fixed

### Bug 1: MaxAddress Allocation Failure (FIXED)

**Problem**: `AllocateType::MaxAddress(0xFFFFFFFF)` fails in UEFI firmware

**Location**: `systems/v4_bootloader_x86/src/bootloader_uefi.rs:280`

**Fix Applied**:
```diff
- uefi::boot::AllocateType::MaxAddress(0xFFFFFFFF),
+ uefi::boot::AllocateType::AnyPages,
```

**Verification**: After fix, allocation succeeds (log shows "Command line allocated at 0x...")

**Status**: ✅ Fixed

### Bug 2: boot_params Allocation Failure (IDENTIFIED, NOT FIXED)

**Problem**: Even though cmdline allocation succeeds, kernel boots without cmdline parameters

**Symptom**: Serial log shows both:
- "Command line allocated at 0x..." (success)
- "Failed to allocate command line memory: , booting without cmdline" (kernel side)

**Root Cause**: boot_params allocation failing or address >32-bit causing Linux boot protocol to ignore cmdline

**Evidence**: System stalls at systemd-networkd-wait-online even though `systemd.mask=systemd-networkd-wait-online.service` was in cmdline

**Status**: 🔬 Identified; fix pending

---

## What Remains

### Interactive Login Verification (BLOCKED by Bug 2)

**Setup Complete**:
- Root password set via guestfish: `root:israel`
- Confirmed via `/etc/shadow` contains hashed password

**Blocked By**: cmdline not passing to kernel, so:
- `systemd.mask=snapd.service` not applied
- `systemd.mask=snapd.seeded.service` not applied
- `systemd.mask=systemd-networkd-wait-online.service` not applied
- System hangs at network wait-online

**Next Steps**:
1. Fix boot_params allocation failure
2. Rebuild bootloader
3. Reboot and wait for login prompt
4. Test interactive login via serial pty or stdio
5. Run verification commands: `uname -a`, `cat /etc/os-release`, `ls /`, `systemctl is-system-running`

---

## Files Modified

1. `systems/v4_bootloader_x86/src/bootloader_uefi.rs`
   - Line 280: Changed `MaxAddress(0xFFFFFFFF)` → `AnyPages`

2. `systems/v4_bootloader_x86/.cargo/config.toml` (created)
   - Added `[build] target = "x86_64-unknown-uefi"`

3. `ubuntu-24.04-server-cloudimg-amd64.raw` (modified)
   - Root password set to `israel`

---

## Test Commands

```bash
# Build
cd /home/jericho/projects/zion/projects/visual_audio/systems/v4_bootloader_x86
cargo build --release --target x86_64-unknown-uefi

# Recreate disk image
dd if=/usr/share/OVMF/OVMF_VARS_4M.fd of=/tmp/ubuntu_v4_efi.img bs=512 count=9216 conv=notrunc
dd if=systems/target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi of=/tmp/ubuntu_v4_efi.img bs=512 seek=1 conv=notrunc

# Boot test
cd /home/jericho/projects/zion/projects/visual_audio
bash run_v4_test.sh

# Check results
tail -50 /tmp/qemu_serial.log
```

---

## Skills Updated

- **Memory**: User preferences (verification-first, no fabricated claims), V4 bootloader debugging patterns
- **Skill**: `visual-audio-v4-boot` added reference `references/uefi-bootloader-debugging.md`

---

## Sign-Off

**V4 Boot Status**: ✅ **Milestone Reached — Boot to Login Prompt Verified**

**Remaining Task**: Fix boot_params allocation to enable cmdline parameter passing, then complete interactive login verification

**Evidence**: Serial log at `/tmp/qemu_serial.log` from earlier successful run shows full boot sequence ending at "ubuntu login:" prompt

---

## Addendum (2026-08-23 21:30 CDT) — V4.1 NBD/Tiled Rootfs Milestone CLOSED

**Milestone**: Ubuntu 24.04 boots to `ubuntu login:` end-to-end with the rootfs served by the hand-rolled NBD server (`geos_pixel_nbd`) decoding PDB tiles from `tmp_tiles/` (331 tiles, re-encoded 20:31-20:34 after corruption fix). Verified across 3 consecutive fresh runs (21:05, 21:16, 21:20), zero I/O errors.

**IMPORTANT — Correct evidence paths (supersedes the lines above for NBD runs):**
- NBD boot logs live at `/tmp/qemu_serial_nbd.log` (written by `test_nbd_boot.sh`, `-serial file:`).
- `/tmp/qemu_serial.log` is the legacy NON-NBD path and stays stale — do NOT cite it for NBD runs.
- Freshness guard: `test_nbd_boot.sh` now `rm -f`s the log before boot and requires `log mtime >= run start` for SUCCESS (fixed a stale-match race that produced a false SUCCESS in 26s against an untouched log; reproduced at 21:14, fixed at 21:20).

**Verification evidence:**
```
/tmp/qemu_serial_nbd.log          21:25:10  (patched-script run, login reached)
/tmp/qemu_serial_nbd_2105_run.log  21:13     (preserved first success)
/tmp/qemu_serial_manual.log        21:20:22  (manual confirm run)
```
All contain `Available block devices:` (vda/vda1/vda2 + vdb/vdb1-4, device mtimes after 20:34), `Rootfs mounted successfully. Switching to real root...`, and end at `ubuntu login:`. `grep -c 'I/O error'` = 0.

**Known cosmetic initramfs quirk**: prints `No block devices found` even when devices were listed — caused by `ls -la /dev/vd* /dev/sd*` exiting non-zero when `/dev/sd*` matches nothing in a virtio guest. Harmless; the loop still finds and mounts `/dev/vdb4`.