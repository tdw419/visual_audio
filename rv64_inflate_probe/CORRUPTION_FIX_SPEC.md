# RV64I Initrd Corruption — ACTUAL Root Cause (2026-08-26)

## Status: RESOLVED

The previous "sync fence in chunked write path" hypothesis (CHUNKED_WRITE_FIX.md)
is **ruled out**. The load-time chunked writes demonstrably land correctly (see
Evidence). The real culprit is the bootloader.

## Problem

After ~510M boot steps the initrd region showed a contiguous 0xCC-filled front
(3,925,960 bytes = 74%), and the kernel printed
`Initramfs unpacking failed: broken padding` at kernel time 49.4s.

## Root Cause Chain

1. **OpenSBI relocates the DTB to 0x82200000.** The Ubuntu opensbi package
   (`/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin`, v1.7) is built with
   `FW_JUMP_FDT_ADDR=0x82200000`. Its boot path (firmware/fw_base.S,
   "Relocate Flatened Device Tree") copies the FDT from the previous stage's a1
   (our DTB at 0x82600000) to that fixed address:
   ```
   t0 = a1 (source = our DTB at 0x82600000)
   t2 = fdt_totalsize(source)  # 1511 bytes
   copy 8 bytes at a time: 0x82600000 -> 0x82200000
   ```
   OpenSBI prints `Domain0 Next Arg1 : 0x0000000082200000` and hands a1=0x82200000
   to the kernel.

2. **0x82200000 is INSIDE the initrd range.** The old loader placed the initrd at
   0x82000000..0x8250B5E1 (5,289,441 bytes). OpenSBI's FDT copy (~2.5KB after its
   own fixup expansion) lands at initrd+0x200000, clobbering the gzip there.
   Verified in the 40M dump: FDT magic 0xd00dfeed at phys 0x82200000, gzip source
   bytes replaced at offsets 0x200000-0x200676.

3. **The kernel's inflate survives the corruption (deflate resynchronizes)** but
   produces ~2.5KB of garbage output at ~4.4MB into the decompressed stream. The
   garbage decodes as bogus cpio entries, so the parser consumes a different number
   of bytes than the real archive, and at the end `do_reset()` (init/initramfs.c)
   sees non-zero, misaligned trailing bytes -> `error("broken padding")`.
   (Python zlib on the corrupted input fails only at the CRC check, confirming the
   stream decodes to the end.)

4. **free_initrd_mem() poisons the initrd with 0xCC.** On ANY unpack result
   (success or failure), `do_populate_rootfs()` calls
   `free_initrd_mem(initrd_start, initrd_end)` (init/initramfs.c), which fills the
   range with `POISON_FREE_INITMEM` (0xCC, include/linux/poison.h). The dump caught
   this memset mid-flight: front 3.93MB poisoned, tail 1.36MB still intact gzip.

## Why QEMU Boots

QEMU's virt machine places the initrd at 0x84000000 (its default), far from
0x82200000, so OpenSBI's FDT copy clobbers nothing.

## Fix

Move the initrd out of OpenSBI's FDT window. New layout:

| Component | Old address | New address |
|-----------|-------------|-------------|
| OpenSBI   | 0x80000000  | 0x80000000  |
| Kernel    | 0x80200000  | 0x80200000  |
| OpenSBI FDT copy | 0x82200000 (clobbered initrd!) | 0x82200000 (free RAM, harmless) |
| DTB (source) | 0x82600000 | 0x82600000 |
| Initrd    | 0x82000000  | **0x82800000** |
| CMA       | 0x83000000  | 0x83000000  |

Change: `tests/standalone_alpine_boot.py` — fixed initrd offset
`RAM_BASE + 0x2000000` -> `RAM_BASE + 0x2800000` (mirrored in
`tests/initrd_verification.py`, `tests/check_dtb_initrd.py`, and the
`rv64_inflate_probe/` + `tools/analyze_mem_dump.py` dump-analysis offsets).

The kernel already reserves everything correctly once the physical overlap is gone:
`reserve_initrd_mem()` (from /chosen linux,initrd-start/end),
`early_init_fdt_scan_reserved_mem()` (the /reserved-memory nodes), and
`memblock_reserve(dtb_early_pa, ...)` (the FDT copy itself at 0x82200000,
arch/riscv/mm/init.c).

## Evidence

- 40M dump (old layout): initrd 1,648 diff bytes, ALL at +0x200000..0x200676 =
  exactly the OpenSBI FDT copy footprint.
- 40M dump (new layout): initrd **0 diff bytes**; FDT copy still at 0x82200000
  (now in free RAM); DTB source intact at 0x82600000.
- OpenSBI UART: `Domain0 Next Arg1 : 0x0000000082200000`.
- fw_base.S source: `Relocate Flatened Device Tree` copy loop (lines ~257-297).
- init/initramfs.c v6.12: do_reset "broken padding"; free_initrd_mem +
  POISON_FREE_INITMEM (0xCC).
- arch/riscv/mm/init.c v6.12: reserve_initrd_mem + dtb memblock_reserve.

## Testing Plan (result)

1. ✅ 40M checkpoint run with fix: initrd byte-perfect at 0x82800000 (0 diff bytes).
2. ✅ Full boot (907M steps): NO "broken padding"; kernel reached
   "Run /init as init process" (kernel time 89.6s) and freed initrd memory
   ("Freeing initrd memory: 5164K"). Before the fix it died at 49.4s / 510M steps.
3. ✅ Unit tests: tests/test_spatial_rv64i_cpu.py + test_opensbi_setup.py (17)
   + test_spatial_cpu.py + test_spatial_rv32i_cpu.py (21) all pass.
4. Repeatable gate: `rv64_inflate_probe/verify_initrd_gate.sh`.

## Follow-up (new, separate issue — NOT this bug)

The fixed boot now fails differently during unpack:
`[88.5s] Initramfs unpacking failed: write error` — a ramfs file write fails
(do_copy/xwrite path), after 3 `workqueue: Failed to create ... kthread ... -EAGAIN`
messages and kernel `Tainted: [B]=BAD_PAGE`. This points to memory pressure /
page-allocator trouble in the 64MB emulator RAM (only ~20.7MB available per the
kernel; CMA takes 16MB), not the initrd addressing. The kernel still proceeds to
"Run /init as init process". Next investigation: why ramfs runs out of space and
what triggers BAD_PAGE (candidate: emulator store/load edge under allocation
pressure, or the 16MB CMA reservation starving the unpack).
