# Alpine Boot Trace — Software-to-Video Pipeline Verification

**Status**: BLOCKED — Alpine RISC-V cannot boot; use xv6.img for working demos

**Date**: 2026-08-15 (Updated)

## Root Cause

**Alpine RISC-V uses PE32+ EFI kernel format, not ELF64.**

`boot_images/alpine_vmlinuz` decompresses to PE32+ EFI:
- `file alpine_vmlinuz`: gzip compressed data
- `zcat alpine_vmlinuz | file`: PE32+ executable (EFI application) RISC-V 64-bit

OpenSBI (the default RISC-V firmware for QEMU virt) only loads raw ELF64 kernels:
- `boot_images/hello.img`: ELF 64-bit at 0x80200000 — Boots and prints message ✅
- `boot_images/xv6.img`: ELF 64-bit at 0x80000000 — Conflicts with OpenSBI firmware region ❌

PE32+ EFI requires EDK2/UEFI firmware stack (e.g., `virtio-flash-device` firmware), which adds significant complexity and is not currently supported by `qemu_to_mkv.py`.

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