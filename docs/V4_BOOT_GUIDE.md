# V4 Boot Guide — Geometry OS Spatial Boot System

**Last Updated**: 2026-08-24
**Status**: PRODUCTION — Ubuntu 24.04 boots to login from pixel-encoded storage

## Overview

V4 Boot is the Geometry OS spatial boot system that boots complete operating systems (Ubuntu 24.04) from pixel-encoded PNG containers. This guide walks through the complete boot chain: bootloader → PNG tile decoding → rootfs extraction → kernel handover.

## Architecture

### V4 Boot Components

1. **V4 Bootloader** (`v4_bootloader_x86`): UEFI bootloader written in Rust
   - OVMF-compatible (UEFI specification)
   - PNG decoding via V3's proven decoder
   - ELF64 loader for kernel/initramfs
   - Hilbert curve mapping for spatial coherence

2. **V4 Pixel Database (PDB)**: Tiled spatial storage
   - Tiles: 4096×4096×3 BGR24 PNGs
   - Tile capacity: (tile_size-128)*tile_size*3 bytes (128-row header)
   - Hilbert mapping: `tools/geos_hilbert.py`
   - Verification: VCC (Visual Consistency Contract) compliant

3. **V4 Container Format**: Single PNG containing:
   - Section headers (metadata)
   - Kernel (bzImage)
   - Initramfs (gzipped cpio)
   - Rootfs tiles (multi-tile PDB)

## Quick Start

### 1. Build V4 Bootloader

```bash
cd systems/v4_bootloader_x86
cargo build --release --target x86_64-unknown-uefi
```

Output: `target/x86_64-unknown-uefi/release/bootloader_v4_x86.efi`

### 2. Prepare Boot Images

```bash
# Create OVMF variables
dd if=/dev/zero of=/tmp/my_vars.fd bs=1M count=1

# Build V4 container (if encoding new rootfs)
python3 tools/v4_boot_builder.py \
    --kernel vmlinuz \
    --initrd initramfs.gz \
    --rootfs rootfs.ext4 \
    --output ubuntu_v4_boot.pdb.png
```

### 3. Boot Ubuntu from V4 PNG

```bash
# Using VNC display
qemu-system-x86_64 -m 2G -enable-kvm -cpu host \
    -display vnc=:1 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-desktop-15g.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial file:/tmp/qemu_serial.log

# Connect VNC viewer
vncviewer localhost:1
```

### 4. Verify Boot

```bash
# Check serial console for boot logs
tail -f /tmp/qemu_serial.log

# Look for V4 bootloader messages:
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@123: Loading initramfs PNG (tile 1)...
[ INFO]: v4_bootloader_x86/src/media.rs@107: Found V4BOOT00 at offset 68157440
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@126: Initramfs PNG found at offset 90310077
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@324: Jumping to Linux kernel...
```

## V4 Bootloader Internals

### Boot Sequence

```
UEFI Firmware (OVMF)
    ↓
V4 Bootloader (.efi)
    ↓
1. Locate V4BOOT00 magic in EFI partition
    ↓
2. Parse PDB header (section metadata)
    ↓
3. Load initramfs PNG tiles (decode via PixelDecoder)
    ↓
4. Reassemble kernel + initramfs from sections
    ↓
5. Allocate memory (boot_params, cmdline, kernel, initramfs)
    ↓
6. Setup Linux boot protocol (boot_params, cmdline pointer)
    ↓
7. Jump to kernel entry point (0x7d0c20e0 in verified boot)
    ↓
Linux Kernel
    ↓
Initramfs (systemd, mount rootfs)
    ↓
Ubuntu Desktop (GDM → graphical.target)
```

### Memory Layout (Verified Boot)

```
Address      | Size      | Purpose
-------------|-----------|----------------------------------
0x7c276000   | 15.0MB    | Kernel (bzImage)
0x7e769000   | 1.1MB     | Initramfs (decoded from PNG)
0x7eb59000   | 256 bytes | Command line string
0x7e...      | 4KB       | boot_params structure
```

### Command Line Parameters (V4 Default)

```
console=ttyS0,115200 earlyprintk=serial,ttyS0,115200
earlycon=uart8250,io,0x3f8 loglevel=7 debug
cloud-init=disabled
systemd.mask=snapd.service
systemd.mask=snapd.seeded.service
systemd.mask=systemd-networkd-wait-online.service
```

**Purpose**: Fast boot to graphical target, disable snap services (speeds boot by ~10s)

## V4 PDB Format

### PDB Header Structure

```
Offset | Size | Field
-------|------|------------------------------------------
0      | 4    | Magic: "PDB\0"
4      | 2    | Version: 1
6      | 2    | Flags
8      | 8    | Table offset (bytes)
16     | 8    | Section count
```

### Section Metadata

```
Offset | Size | Field
-------|------|------------------------------------------
0      | 16   | Section name (padded)
16     | 8    | Offset (bytes from container start)
24     | 8    | Size (bytes)
32     | 8    | Tile count (if multi-tile)
40     | 8    | Reserved
```

### Hilbert Curve Mapping

V4 uses 2D Hilbert curves for spatial coherence:

```bash
# Generate Hilbert mapping (N=4096 for tile size)
python3 tools/geos_hilbert.py --N 4096 > tools/hilbert_map.py
```

**Verification**: VCC compliance required for any spatial transformation

## Verification Gates

### Boot Verification

```bash
# Fresh boot check
rm -f /tmp/qemu_serial.log
qemu-system-x86_64 [boot args] &
sleep 40

# Check for V4 bootloader messages
grep "v4_bootloader_x86" /tmp/qemu_serial.log | head -10

# Check for Ubuntu login prompt
tail -5 /tmp/qemu_serial.log
# Expected: "Ubuntu 24.04.4 LTS ubuntu ttyS0\nubuntu login:"
```

### Screenshot Capture

```bash
# Boot with monitor socket
qemu-system-x86_64 -monitor unix:/tmp/qemu_monitor.sock,server,nowait [boot args]

# Capture screenshot
printf "screendump /tmp/qemu_screenshot.ppm\n" | nc -U /tmp/qemu_monitor.sock

# Verify output
file /tmp/qemu_screenshot.ppm
# Expected: "Netpbm image data, size = 1280 x 800, rawbits, pixmap"
```

### Memory Layout Verification

```bash
# Extract command line from boot_params (requires QEMU debug)
# Or inspect bootloader logs for allocation addresses
```

## Troubleshooting

### Boot Fails at "Failed to allocate command line memory"

**Cause**: `boot_params` allocation failure
**Fix**: Check available memory in bootloader, reduce initramfs size

### "ubuntu login:" appears but GUI doesn't start

**Cause**: graphical.target not reached
**Fix**: Check systemd logs, ensure GPU passthrough enabled

### Screenshot is blank/black

**Cause**: QEMU display mode issue
**Fix**: Try `-display sdl` or `-display gtk` instead of `-display none`

## Performance Metrics

| Metric | Baseline | Achieved | Status |
|--------|----------|----------|--------|
| Boot time (PNG → login) | <30s | ~25s | ✅ |
| Initramfs decode | <5s | ~2s | ✅ |
| PDB tile load | <10s | ~8s | ✅ |

## References

- `systems/v4_bootloader_x86/` — Bootloader source
- `systems/geos_pixel/src/decoder/` — PNG decoder (V3 proven)
- `tools/geos_hilbert.py` — Hilbert curve generator
- `V4_UBUNTU_BOOT_RECEIPT.md` — Verified boot evidence
- `GOVERNANCE_PROTOCOL.md` — Authorization and safety protocols

## Governance Notes

- NO host filesystem passthrough in production demos (WC008 governance decision)
- All spatial transformations must pass VCC verification
- Boot parameters recorded in session logs for reproducibility