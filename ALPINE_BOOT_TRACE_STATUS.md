# Alpine Boot Trace — Software-to-Video Pipeline Verification

**Status**: FURTHER UNBLOCKED (2026-08-16) — EDK2/UEFI firmware works, kernel
boots directly (GRUB bypassed) with full serial output, panics on a specific,
reproducible kernel bug in SMP bring-up. See "2026-08-16 Update #2" below.

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

## 2026-08-16 Update #2 — GRUB bypassed entirely, kernel boots, hits a real kernel bug

Interactive GRUB-menu automation (spamming keypresses via pexpect to catch its
1s timeout window) proved unreliable — pty echo/timing made it impossible to
tell whether keystrokes were reaching the guest at all. Abandoned that
approach in favor of a fully deterministic, no-interaction path:

1. Extracted `boot/vmlinuz-lts` and `boot/initramfs-lts` from the ISO's
   ISO9660 partition on the host (`isoinfo -R -x ... -i alpine-standard-*.iso`)
   — EDK2's Shell has no ISO9660 driver so these are otherwise invisible to it.
2. Decompressed `vmlinuz-lts` (`zcat`) to get the actual PE32+ EFI kernel
   image the RISC-V EFI stub can run directly, bypassing GRUB entirely.
3. Built a small FAT16 disk (`mtools`/`mkfs.vfat`, no root needed) containing
   the kernel, initrd, and a `startup.nsh`:
   ```
   echo -off
   vmlinuz-lts.efi console=ttyS0 earlycon=uart8250,mmio,0x10000000 initrd=initramfs-lts modules=loop,squashfs,sd-mod,usb-storage
   ```
   EDK2 auto-executes `startup.nsh` on an otherwise-idle console (the same
   "press any key to skip" countdown from before) — no keystroke automation
   needed at all.

**Result**: this reaches full kernel boot with complete serial dmesg output —
the first time this project has ever seen real Alpine kernel output over
serial. It panics deterministically at:

```
kernel BUG at arch/riscv/kernel/smpboot.c:151!
epc : setup_smp+0x9e/0x11c
Kernel panic - not syncing: Fatal exception in interrupt
```

Reproduced identically across:
- `-smp 1` and `-smp 4` (rules out a hart-count race)
- `acpi=off` (rules out ACPI vs. DT hart-topology parsing)
- QEMU 8.2.2 (distro, OpenSBI v1.3) **and** self-built QEMU 9.0.0 with its own
  bundled EDK2/OpenSBI (`/home/jericho/qemu-build/qemu-9.0.0/build/qemu-system-riscv64`)
  — rules out a QEMU/firmware version mismatch.
- Only one Alpine kernel build exists locally (`6.18.35-0-lts`,
  `#1-Alpine SMP PREEMPT_DYNAMIC 2026-06-09`) — no older build to fall back to.

This is now a **kernel-level bug**, not a firmware/tooling/config gap. Fixing
it requires either a different Alpine kernel build or patching
`arch/riscv/kernel/smpboot.c`, both out of scope for a config/flag-level fix.

**Reusable artifact**: `/home/jericho/scratch/alpine_uefi/boot_disk.img` (FAT
disk with kernel+initrd+startup.nsh) and the pflash pairs in
`/home/jericho/scratch/alpine_uefi/` and `/home/jericho/scratch/alpine_uefi_v2/`
are the fastest way to re-test this without repeating the ISO-extraction
steps.

## 2026-08-16 Update #3 — same direct-EFI-stub method tried on Ubuntu's riscv64
## kernel, different early panic; points at a systemic ACPI/memory-map issue

Applied the identical FAT-disk/startup.nsh technique to
`boot_images/ubuntu_Image` + `ubuntu_initrd` (Ubuntu 22.04,
`6.8.0-136-generic`, older/more mainstream than Alpine's 6.18 build). No real
rootfs was attached (`ubuntu_desktop.qcow2` is an empty sparse placeholder),
so this could never reach userspace, but it usefully tests whether the
Alpine SMP panic was Alpine-specific.

**Result**: Ubuntu's kernel gets much further than Alpine — past `setup_smp`
entirely, into `kthreadd`/early process creation — before hitting its own
Oops:
```
Unable to handle kernel paging request at virtual address 0000000000001389
epc : prepare_alloc_pages.constprop.0+0xbc/0x150   (in dup_task_struct -> vmalloc)
```
Retried with `nokaslr` and `-m 4G` (vs 3G) — different but structurally
similar fault, one step earlier:
```
Unable to handle kernel paging request at virtual address 0000004000000008
epc : ___slab_alloc+0x4f8/0x85a   (in kmalloc_trace -> kthread_create_worker -> workqueue_init)
```
Both bad addresses cluster near the 1GiB (`0x40000000`) boundary, in early
slab/vmalloc allocator paths, right after ACPI core init
(`ACPI: Core revision 20230628`).

**Conclusion**: two unrelated kernel builds (Alpine 6.18, Ubuntu 6.8) each
hit an early memory-management panic specifically when booted via the direct
EFI-stub path, which relies on QEMU/EDK2's **ACPI**-based memory map. The toy
kernels that already boot fine (`hello.img`, `xv6.img`) never exercise this
path — they're bare ELF64 images booted straight by OpenSBI, no UEFI/ACPI
involved at all. This reframes the earlier GRUB blocker: GRUB normally hands
the kernel a **devicetree**, not ACPI tables, which may avoid this failure
mode entirely. **Fixing GRUB's silent console** (append `console=ttyS0`,
drop `quiet`, either by interrupting its 1s menu timeout or building a
patched `grub.cfg`) is likely a more promising path than continuing to
hand-roll direct EFI-stub boots.

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