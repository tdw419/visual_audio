# Ubuntu MKV Boot - Current Status

## Status: WORKING ✅ (2026-07-30)

Full Ubuntu boot chain proven end-to-end from visual_audio.mkv:

```
pixel-decode → QEMU + U-Boot + Ubuntu server cloudimg + NoCloud seed ISO
             → OpenSBI → U-Boot → GRUB → Linux 6.17 → systemd → cloud-init → login
```

**Boot time to login: ~35-45 seconds** (latest verified run: 44.9s, 30.7s up)

## What's Proven (Byte-For-Byte)

1. **MKV Container Integrity** — `visual_audio.mkv` holds all boot components pixel-encoded
2. **Byte-perfect round-trip** — all three components decode with matching MD5:
   - `server_cloudimg.qcow2.pixel` → 813,105,152 bytes (4.5 GiB virtual qcow2), MD5 `c92267ff2921a67209ec4e4d3d0cc7a4`
   - `u-boot.bin.pixel` → 1,180,288 bytes, MD5 `7068fcd985e104e6c01c6728086936ee`
   - `nocloud.iso.pixel` → 374,784 bytes, MD5 `0e32bede9a035c0fd8931f8c4db9639c`
3. **va_container.py Optimizations** — streaming `read_entry_streamed` (keyframe seek) extracts entries in seconds without OOM; full `load_container` decode of 50K-frame container is NOT needed for extraction.

## The Working Boot Chain

The earlier failure (stuck at OpenSBI "Boot HART MEDELEG") was caused by:
- **Wrong disk**: booted the desktop image (`ubuntu/desktop/ubuntu-24.04-desktop.qcow2`, 785MB) instead of the server cloud image (`server_cloudimg.qcow2`, 4.5 GiB virtual)
- **Missing U-Boot**: no `-kernel u-boot.bin` → OpenSBI had nothing to hand off to
- **Missing NoCloud seed**: no cloud-init ISO → no `mkv-verify` hostname/login config

### Working QEMU command

```bash
qemu-system-riscv64 \
  -machine virt -cpu rv64 -m 2048 -smp 2 \
  -bios default \
  -kernel u-boot.bin \
  -drive file=server_cloudimg.qcow2,if=virtio,format=qcow2 \
  -drive file=nocloud.iso,if=virtio,format=raw \
  -nographic
```

Key facts:
- OpenSBI v1.3 (system default at 0x80000000) hands off to U-Boot at 0x80200000
- U-Boot 2025.10-0ubuntu0.24.04.2 scans virtio 0:1, finds GRUB
- GRUB loads Linux 6.17.0-35-generic
- cloud-init uses DataSourceNoCloud [seed=/dev/vdb] (the nocloud.iso, attached as second virtio drive)
- Login: `mkv-verify login:` (user `ubuntu` / password `verify`, SSH on port 2222 via hostfwd if enabled)

## How to Boot

```bash
# One-shot: extract all three components from MKV + boot
python3 tools/boot_ubuntu_from_mkv.py

# Verify mode: boot with timeout, check for login prompt, auto-exit
python3 tools/boot_ubuntu_from_mkv.py --verify

# Reuse already-extracted components in scratch dir
python3 tools/boot_ubuntu_from_mkv.py --verify --keep
```

## MKV Entries (boot-relevant)

| Component | MKV Path | Decoded Size | Purpose |
|-----------|----------|-------------|---------|
| Disk | `server_cloudimg.qcow2.pixel` | 813 MB (4.5 GiB virtual) | Ubuntu 24.04 server cloud image |
| Bootloader | `u-boot.bin.pixel` | 1.2 MB | U-Boot 2025.10 (S-mode payload) |
| Seed | `nocloud.iso.pixel` | 375 KB | cloud-init NoCloud seed (hostname `mkv-verify`) |

Created: 2026-07-30
Updated: 2026-07-30 (boot chain fixed and re-verified)
