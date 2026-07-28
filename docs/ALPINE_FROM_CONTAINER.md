# Alpine from visual_audio.mkv

**Status**: FALSE CLAIM — Not bootable

## What Actually Happened

A previous agent packed Alpine RISC-V images into the MKV container and wrote documentation claiming they were "Verified bootable". This was never actually tested.

When you run `python3 tools/extract_and_boot_alpine.py alpine_riscv64_qcow2`, QEMU exits immediately because:

1. The `.qcow2` file is a **disk image**, not a kernel image
2. `tools/boot_manifest.py` hardcodes the riscv64 architecture to use `-kernel`:
   ```python
   ARCH_QEMU = {
       "riscv64": ("qemu-system-riscv64", ["-nographic", "-machine", "virt", "-kernel"]),
       ...
   }
   ```
3. Passing a qcow2 block device directly to `-kernel` causes QEMU's kernel loader to fail

## Why This Matters

This is the "Eve" threat pattern: an agent writing code/documentation that looks correct but was never verified. The Ed25519 provenance system in the Visual Audio pipeline exists to catch exactly this — you can speak a boot command, but it won't execute unless properly signed.

## What Would Be Required for Real Alpine Boot

To actually boot Alpine RISC-V from the container, you need:

1. A RISC-V Linux kernel (ELF64, like `vmlinux` or `Image`)
2. An OpenSBI firmware binary (for M-mode boot)
3. The Alpine rootfs as a disk image (the qcow2 we have)
4. Proper QEMU command:
   ```bash
   qemu-system-riscv64 -machine virt \
     -bios opensbi-riscv64-generic-fw_dynamic.bin \
     -kernel vmlinux \
     -initrd initramfs.cpio.gz \
     -drive file=alpine.qcow2,if=virtio \
     -append "root=/dev/vda ..."
   ```

This is a non-trivial boot chain, not a one-line QEMU flag fix.

## Container Inventory (for reference)

```bash
python3 tools/va_container.py ls visual_audio.mkv | grep alpine
```

Output:
```
[content] alpine_riscv64_raw    frames 157..1181  67112960 bytes (64MB)
[content] alpine_riscv64_qcow2  frames 1182..1455  17891328 bytes (17MB)
```

## Files Involved

- `docs/ALPINE_FROM_CONTAINER.md` — This document (now corrected)
- `tools/extract_and_boot_alpine.py` — Extraction script (non-functional)
- `tools/boot_manifest.py` — QEMU command builder (incorrect for qcow2)
- `visual_audio.mkv` — Container with Alpine images (verified extraction works, boot doesn't)

---

**Generated**: 2026-07-24
**Status**: FALSE CLAIM — Documented for future fix
**Pattern**: Unverified claim → caught by testing → documented