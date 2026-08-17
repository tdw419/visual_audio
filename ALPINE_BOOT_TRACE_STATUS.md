# Alpine Boot Trace — Software-to-Video Pipeline Verification

**Status**: PARTIALLY UNBLOCKED (2026-08-16) — EDK2/UEFI firmware works; GRUB reaches
the kernel but produces no serial output because of its own config, not a firmware
limitation. See "2026-08-16 Update" below.

**Date**: 2026-08-15 (original), updated 2026-08-16

## Root Cause (original, now resolved)

**Alpine RISC-V uses PE32+ EFI kernel format, not ELF64.**

`boot_images/alpine_vmlinuz` decompresses to PE32+ EFI:
- `file alpine_vmlinuz`: gzip compressed data
- `zcat alpine_vmlinuz | file`: PE32+ executable (EFI application) RISC-V 64-bit

OpenSBI (the default RISC-V firmware for QEMU virt) only loads raw ELF64 kernels:
- `boot_images/hello.img`: ELF 64-bit at 0x80200000 — Boots and prints message ✅
- `boot_images/xv6.img`: ELF 64-bit at 0x80000000 — Conflicts with OpenSBI firmware region ❌

PE32+ EFI requires EDK2/UEFI firmware stack. This was previously assumed out of
scope, but **the firmware is already installed on this machine** (`qemu-efi-riscv64`
package, `/usr/share/qemu-efi-riscv64/RISCV_VIRT_{CODE,VARS}.fd`) and works.

## 2026-08-16 Update — EDK2 firmware confirmed working, new precise blocker found

Booted `boot_images/alpine-standard-3.24.1-riscv64.iso` (isohybrid) as a raw
`virtio-blk-device` disk with EDK2 pflash firmware attached:

```bash
qemu-system-riscv64 -machine virt -m 3G -smp 4 \
    -pflash /usr/share/qemu-efi-riscv64/RISCV_VIRT_CODE.fd \
    -pflash /usr/share/qemu-efi-riscv64/RISCV_VIRT_VARS.fd \
    -drive file=boot_images/alpine-standard-3.24.1-riscv64.iso,if=none,format=raw,id=cd0,readonly=on \
    -device virtio-blk-device,drive=cd0 \
    -nographic -no-reboot
```

(pflash files must be writable copies, not the read-only package originals —
copy them to a scratch dir first.)

**Confirmed working**: OpenSBI → EDK2 RISC-V UEFI firmware boots cleanly →
correctly enumerates the ISO's GPT partitions → mounts the small FAT ESP
partition as `FS0:` → finds `\EFI\BOOT\BOOTRISCV64.EFI` (GRUB) at the standard
path. This directly refutes the old "out of scope" / "BLOCKED" verdict — the
UEFI firmware stack is not the blocker.

**New, more precise blocker**: launching `FS0:\EFI\BOOT\BOOTRISCV64.EFI` from
the UEFI Shell produces **zero serial output**, even after 4+ minutes (ruled out
as merely "TCG software emulation is slow" — GRUB should print something within
seconds even under slow emulation).

Root cause, confirmed by extracting `boot/grub/grub.cfg` from the ISO
(`isoinfo -R -x /boot/grub/grub.cfg -i alpine-standard-3.24.1-riscv64.iso`):

```
set timeout=1

menuentry "Linux lts" {
linux	/boot/vmlinuz-lts modules=loop,squashfs,sd-mod,usb-storage quiet
initrd	/boot/initramfs-lts
}
```

This is **not a hang** — it's silent-by-design:
- `timeout=1` with a single menu entry means GRUB never prints a menu.
- The kernel cmdline has `quiet` and **no `console=ttyS0`**, so nothing is
  routed to the serial UART we're capturing, even if boot succeeds.
- Alpine's inittab/openrc typically only spawns a serial getty when
  `console=ttyS0` appears on the kernel cmdline, so even a fully-booted system
  would show no login prompt over this pipe.

Also confirmed: EDK2's built-in Shell has no ISO9660 filesystem driver, so
`vmlinuz-lts`/`initramfs-lts` (which live on the ISO9660 rootfs partition, not
the FAT ESP) are invisible to `FS0:` — only GRUB's own bundled fs drivers
(baked into `boot/grub/efi.img`) can read them. This rules out bypassing GRUB
entirely from the Shell; the fix has to happen through GRUB.

## Next Step (not yet done)

Interrupt GRUB's 1-second menu timeout (send a keypress immediately after
invoking `BOOTRISCV64.EFI`, before the menu auto-boots) to edit the boot entry
and append `console=ttyS0` (and drop `quiet`), or build a custom ISO/GRUB
config with those changes baked in. Either should make the actual boot
progress (or actual failure) visible over serial for the first time.

## What Works

1. **QMP Memory Dump Pipeline** — VERIFIED:
   - Boot hello.img (ELF64) → captures memory snapshots
   - Hilbert mapping + FFV1 encoding → MKV
   - Frame extraction → round-trip hash verification
   - QMP connection now has exponential backoff retry

2. **hello.img Boot Trace** — VERIFIED:
   - Kernel boots fully on RISC-V virt with default OpenSBI
   - Memory changes are captured during boot
   - Multi-frame delta encoding works

## What DOES NOT Work

1. **Alpine RISC-V** — BLOCKED:
   - Kernel format: PE32+ EFI (not ELF64)
   - Requires: EDK2/UEFI firmware (not default OpenSBI)
   - Symptoms: QEMU hangs at OpenSBI, never loads kernel

2. **xv6.img** — BROKEN:
   - Linker loads at 0x80000000 (overlaps OpenSBI at 0x80000000-0x8004180)
   - QEMU aborts: "Some ROM regions are overlapping"
   - QMP socket never created (process dies before listening)

## Fixed Issues (2026-08-15)

1. **QMP Connection Reliability**: Added exponential backoff retry (0.1s → 51.2s max, 10 attempts)
2. **Duplicate Disk Parameter**: Kernel-only boot no longer adds redundant `-drive` pointing to same file
3. **Auto-detect Kernel Files**: Searches multiple naming conventions for kernel/initrd pairs

## Verification Commands (hello.img)

Capture hello.img boot trace:
```bash
python3 tools/qemu_to_mkv.py boot_images/hello.img \
    --arch riscv64 \
    --output /tmp/hello_boot_trace.mkv \
    --interval 100000 \
    --max-frames 10 \
    --memory 64M
```

Extract frame back to memory dump:
```bash
python3 tools/qemu_to_mkv.py /tmp/hello_boot_trace.mkv \
    --extract-frame 0 \
    --output /tmp/hello_frame0.mem
```

Verify extracted memory:
```bash
file /tmp/hello_frame0.mem
xxd /tmp/hello_frame0.mem | head -20
```

## Software-to-Video Pipeline Status

The QMP memory dump → Hilbert mapping → FFV1 MKV → frame extraction pipeline is FULLY OPERATIONAL for:
- ELF64 RISC-V kernels at 0x80200000 (hello.img)
- PE32+ EFI kernels (Alpine) — firmware stack limitation
- ELF64 kernels at 0x80000000 (xv6) — OpenSBI firmware overlap

## Next Steps

1. Use hello.img for boot trace demonstrations — Works end-to-end
2. Rebuild xv6.img at 0x80200000 (hello.img address) to avoid OpenSBI overlap
3. Document Alpine limitation — PE32+ EFI requires EDK2 firmware (out of scope)
4. Integrate working trace into VAC3 container — Z=1 = RAM substrate, Z=0 = display

## Comparison: Boot Trace Options

| Aspect | hello.img | xv6.img | Alpine |
|--------|-----------|---------|--------|
| Kernel format | ELF64 | ELF64 | PE32+ EFI |
| Load address | 0x80200000 | 0x80000000 | N/A |
| OpenSBI | Compatible | Overlaps | Ignores |
| QMP socket | ✅ Created | ❌ QEMU aborts | ✅ Created |
| Boot trace | ✅ VERIFIED | ❌ Can't connect | ❌ No execution |
| Status | WORKING | FIXABLE | BLOCKED |

---

**Software-to-video pipeline is fully operational for ELF64 RISC-V kernels.** Use hello.img for demonstrations. Alpine RISC-V boot traces are blocked by kernel format incompatibility (PE32+ EFI vs ELF64) and require EDK2/UEFI firmware support. xv6.img can be fixed by relocating load address to 0x80200000.