# Initramfs Poisoning Investigation Receipt

**Date**: 2026-08-25 (investigation) / 2026-08-26 (root cause + fix)
**Issue**: Alpine Linux boot on GPU emulator fails with "Initramfs unpacking failed: broken padding"
**Root Cause**: OpenSBI relocates its FDT copy to 0x82200000, INSIDE the initrd range → gzip input corrupted at +2MB → inflate decodes garbage → bogus cpio entry → "broken padding" → free_initrd_mem() 0xCC poison
**Status**: RESOLVED (see rv64_inflate_probe/CORRUPTION_FIX_SPEC.md)

---

## Investigation Summary

### Timeline (old layout, initrd at 0x82000000)

1. **2.153s** - "Unpacking initramfs..." starts (async rootfs_initcall)
2. **2.350s+** - Kernel continues other initcalls while unpack runs async
3. **2.4s - 49.4s** - **47-second "silence"**: this is the async gzip inflate of the
   5.29MB input (~470M instructions on the GPU core) + cpio parse. NOT a stall.
4. **49.438s** - "Initramfs unpacking failed: broken padding"

### What the corruption actually was

The 0xCC fill is `POISON_FREE_INITMEM` (include/linux/poison.h) applied by
`free_initrd_mem()` (init/initramfs.c), which runs after the unpack failure.
The dump caught the poison memset mid-flight: front 3,925,960 bytes poisoned,
tail 1,363,481 bytes still intact gzip. It is NOT KASAN, NOT memblock poison,
NOT an emulator memory-model divergence.

### Why the unpack failed

1. Ubuntu's opensbi fw_jump.bin is built with `FW_JUMP_FDT_ADDR=0x82200000`.
2. fw_base.S "Relocate Flatened Device Tree" copies the DTB from a1 (0x82600000)
   to 0x82200000 — which sits inside the initrd (0x82000000..0x8250B5E1).
3. The FDT copy (~2.5KB after OpenSBI fixup expansion) clobbers the gzip at
   initrd+0x200000. The kernel's inflate survives it (deflate resynchronizes),
   produces ~2.5KB of garbage output mid-stream, and the cpio parser trips over a
   bogus entry → `do_reset()` → "broken padding".
4. The kernel then poisons the whole initrd with 0xCC via free_initrd_mem().

### Probe Validation (still valid — and explains the earlier confusion)

- Rung 1 (probe.elf): inflate of the PRISTINE gzip matches QEMU golden.
- Rung 2 (probe_cpio.elf): the PRISTINE decompressed archive parses clean.
- Conclusion: the codec is correct; the corruption is in the INPUT the kernel
  actually reads (the FDT-clobbered gzip), which the probes never exercised.

### Why QEMU boots

QEMU's virt machine places the initrd at 0x84000000, far from 0x82200000, so
OpenSBI's FDT copy clobbers nothing.

---

## Fix (2026-08-26)

Move the initrd from 0x82000000 to **0x82800000** so it no longer spans
OpenSBI's FDT window (0x82200000). The kernel already reserves everything
correctly once the physical overlap is gone:

- `reserve_initrd_mem()` — from /chosen linux,initrd-start/end
- `early_init_fdt_scan_reserved_mem()` — the /reserved-memory nodes
- `memblock_reserve(dtb_early_pa, ...)` — the FDT copy itself (arch/riscv/mm/init.c)

Changed files:
- `tests/standalone_alpine_boot.py` (loader — the actual fix)
- `tests/initrd_verification.py`, `tests/check_dtb_initrd.py` (mirror)
- `rv64_inflate_probe/verify_initrd_in_dump.py`, `rv64_inflate_probe/compare_fullboot_initrd.py`,
  `tools/analyze_mem_dump.py` (dump-analysis offsets)

### Verification

- 40M checkpoint: initrd at 0x82800000 **0 diff bytes** vs source
  (old layout: 1,648 diff bytes at exactly the FDT footprint +0x200000).
- Full boot: no "broken padding" (see fixed_full_run.log).

## Artifacts

- `rv64_inflate_probe/initrd_before_unpack.bin` — 40M dump, old layout
- `rv64_inflate_probe/fullboot_dump.bin` — 510M dump, old layout (broken padding)
- `rv64_inflate_probe/initrd_fixed_40m.bin` — 40M dump, new layout (byte-perfect)
- `rv64_inflate_probe/initrd_fixed_boot_dump.bin` — full-boot dump, new layout
- `rv64_inflate_probe/initramfs_612.c` — kernel source reference
- `rv64_inflate_probe/fw_base.S` — OpenSBI FDT relocation source

**Last Updated**: 2026-08-26
