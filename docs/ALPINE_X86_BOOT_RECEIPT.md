# Alpine x86_64 Boot — Receipt

**Date**: 2026-08-27
**Status**: ✅ WORKING — Alpine x86_64 boots to login prompt via QEMU

## What Was Tested

### Test 1: Direct ISO Boot (Live)
**Script**: `test_alpine_x86.sh`
**Result**: ✅ PASS

Boots Alpine Linux 3.20 (Kernel 6.6.49-0-virt) to `localhost login:` prompt within **8 seconds**.

**Command**:
```bash
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -smp 1 \
    -drive file=boot_images/alpine-x86_test.qcow2,format=qcow2,if=virtio \
    -drive file=boot_images/alpine-virt-x86_64.iso,media=cdrom,readonly=on \
    -nographic -serial mon:stdio \
    -no-reboot
```

**Output excerpt**:
```
Welcome to Alpine Linux 3.20

Kernel 6.6.49-0-virt on an x86_64 (/dev/ttyS0)

localhost login:
```

## Artifacts

- `boot_images/alpine-virt-x86_64.iso` — Downloaded from Alpine official mirrors (61MB)
- `boot_images/alpine-x86_test.qcow2` — 2GB test disk (created automatically)

## Comparison: RISC-V vs x86_64

| Aspect | Alpine RISC-V | Alpine x86_64 |
|--------|---------------|---------------|
| Boot Method | UEFI (PE32+) | BIOS/MBR |
| Kernel Format | PE32+ EFI | ELFx86_64 |
| Firmware | EDK2 (complex) | SeaBIOS (simple) |
| Status | ❌ Kernel panic in SMP bootup | ✅ Boots to login |
| Complexity | High (ACPI memory map issues) | Low (standard PC boot) |

## Why x86_64 Works

Alpine x86_64 uses standard BIOS boot:
- SeaBIOS loads ISOLINUX bootloader from CDROM
- ISOLINUX loads Linux kernel (ELFx86_64)
- Kernel boots with standard PC hardware support
- Serial console configured via kernel cmdline

No complex ACPI tables or memory map quirks — just traditional x86 boot.

## Recommendations

1. **For demonstrations**: Use Alpine x86_64 — boots reliably, no kernel panics
2. **For RISC-V GPU emulator**: Use xv6 — works perfectly on GPU
3. **For Alpine RISC-V**: Blocked by kernel bug in SMP bootup (out of scope)

## Next Steps

To make Alpine x86_64 more useful:
1. Create installed disk image (not just live ISO)
2. Setup cloud-init for auto-login
3. Pre-install common tools (ssh, vim, git)
4. Test with audio boot manifest

## Verification

Reproduce this test:
```bash
cd /home/jericho/projects/zion/projects/visual_audio
./test_alpine_x86.sh
```

Expected: Boot completes with `localhost login:` prompt within 15 seconds.