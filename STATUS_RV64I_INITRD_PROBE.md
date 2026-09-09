# RV64I Initramfs "Broken Padding" — Probe-Based Isolation Results

**Date**: 2026-08-25
**Status**: Inflate and cpio-parser code paths PROVEN CORRECT on GPU core.
**Remaining suspect**: kernel's VA→PA translation of the initrd region (MMU/TLB)
or an overwrite of 0x82000000 during early boot.

## TL;DR

The "Initramfs unpacking failed: broken padding" error in the full Alpine boot
is **NOT** caused by:

1. ~~Corrupted initrd bytes in memory~~ — GPU memory matches source (input fnv1a OK)
2. ~~Mis-executed instruction in zlib inflate~~ — full-initrd inflate is byte-perfect on GPU
3. ~~Cpio parser alignment bug~~ — cpio walk is CLEAN on GPU (184 records, TRAILER found)

The kernel must therefore be reading DIFFERENT bytes from the initrd region in
the full boot than the bytes we wrote — i.e. an MMU/TLB linear-map translation
divergence, or an overwrite of 0x82000000 before unpack runs.

## The Probe Staircase (all artifacts in rv64_inflate_probe/)

### Rung 1: Bare-metal inflate probe (`probe.elf`)

Same ELF runs on QEMU (golden) and GPU core. Uses the kernel's VERBATIM
zlib_inflate sources (lib/zlib_inflate/inflate.c, inffast.c, inftrees.c) with
a 32KB flush-chunk loop matching __gunzip(flush=flush_buffer).

| Case | QEMU | GPU | Match |
|------|------|-----|-------|
| small (342B→90KB) out fnv1a | 0x3268018db6473835 | 0x3268018db6473835 | ✓ |
| initrd (5.29MB→11.6MB) out fnv1a | 0x8467f515c0c44ada | 0x8467f515c0c44ada | ✓ |
| initrd total_out | 11,600,900 | 11,600,900 | ✓ |
| initrd input fnv1a | 0x1ac689f36c816ec9 | 0x1ac689f36c816ec9 | ✓ (memory read path OK) |
| out[0..7] | "070701" | "070701" | ✓ (cpio newc magic) |
| out[-8..] | TRAILER!!! | TRAILER!!! | ✓ |

Conclusion: **zlib inflate on the GPU core is byte-perfect for the entire real
initrd.** The previous STATUS_RV64I_LOOP.md hypothesis ("mis-executed
instruction in the inflate stream-end path") is DISPROVEN.

### Rung 2: Bare-metal cpio parser probe (`probe_cpio.elf`)

Mirrors init/initramfs.c's do_header/do_reset logic (newc magic, namesize,
filesize, 4-byte padding, TRAILER!!! detection) over the decompressed output.

| Metric | QEMU | GPU |
|--------|------|-----|
| records walked | 184 | 184 |
| TRAILER!!! offset | 0xb10388 | 0xb10388 |
| result | CLEAN | CLEAN |

Note: run_probe_gpu.py reported "DIVERGES" for probe_cpio.elf only because it
greps for the inflate probe's "total_out:" string, which the cpio probe never
prints. The UART output itself is identical. (Cosmetic runner bug, not a real
divergence — the probe's own CPIO RESULT: CLEAN line is authoritative.)

Conclusion: **cpio parser logic on the GPU core is correct.**

## Next Step (in flight)

Full boot with `--stop-on-uart "broken padding" --dump-mem` then compare the
initrd region (physical 0x82000000–0x8250b5e1) against initrd.gz.bin:

- If dump matches source → kernel read garbage through the MMU → page-walk the
  kernel's linear-map VA (0xffffffff82xxxxxx) vs QEMU's mapping.
- If dump differs → something overwrote 0x82000000 during early boot (memblock
  allocator collision, DTB/CMA overlap, kernel zeroing) — find the writer.

## Key Technical Facts Re-confirmed

- "broken padding" is emitted by init/initramfs.c `do_reset()`:
  ```c
  while (byte_count && *victim == '\0') eat(1);
  if (byte_count && (this_header & 3)) error("broken padding");
  ```
  It fires when, after eating NUL padding, bytes remain at a non-4-aligned
  header offset — i.e. the decompressed stream the parser sees is not the
  well-formed cpio archive.
- QEMU with the correctly-extracted initrd shows NO initramfs error:
  `Unpacking initramfs...` → (no error) → `VFS: Unable to mount root fs` panic.
  QEMU is a clean golden. The "write error" note in an earlier status doc came
  from a run using the WRONG (contiguous) initrd extraction.
- The full boot is SLOW on GPU (~1.7M steps/s with threading): reaching
  "broken padding" needs ~500-700M steps. The probes were the right call —
  they reach the same code in ~400M steps for the full initrd, or ~millions
  for the small payload.

## UPDATE (2026-08-25, later): Decisive byte-comparison result

Ran the planned next step: `tools/monitor_rv64i.py --program alpine --stop-on-uart
"broken padding" --dump-mem` (515M steps to trigger), then byte-compared the
dumped linear guest memory at physical 0x82000000 (offset confirmed correct —
independently recomputed from tests/standalone_alpine_boot.py's own placement
logic: kernel_load_addr=0x80200000, kernel_mem_size=20,852,736 rounds to
0x80200000+0x1400000, which is less than RAM_BASE+0x2000000, so
initrd_load_addr = 0x82000000 exactly) against the source
`rv64_inflate_probe/initrd.gz.bin` (5,289,441 bytes).

**Result: NEITHER hypothesis from the "Next Step" section above.** This is not
scattered/page-granular corruption (which an MMU/TLB translation divergence
would produce), and it's not a clean match either. It's a **clean, contiguous
prefix overwrite**:

- Bytes `[0x0, 0x1076c0)` (1,078,976 bytes, ~1.03MB) are `0xCC` repeated —
  uniform filler, not the real gzip header/data at all.
- Bytes `[0x1076c0, end)` — i.e. everything from byte 1,078,976 through the
  full 5,289,441-byte length — are **byte-identical** to source (verified at
  the boundary, the midpoint 0x285af0, and the last 32 bytes at 0x50b5a1).

So ~980KB of the initrd's tail-end content is intact in memory, but the first
~1.03MB has been overwritten with a uniform `0xCC` pattern sometime between
when the loader wrote it and when the kernel's unpacker read it. `0xCC` does
not appear anywhere in our own write path (`tools/spatial_rv64i_cpu.py`,
`tools/SPATIAL_RV64I.wgsl`, `tests/standalone_alpine_boot.py`,
`tools/create_dtb.py` — grepped, no matches), so this isn't a leftover
uninitialized-buffer artifact from our own code; something is *actively*
overwriting this specific address range.

**Leading hypothesis:** the kernel's own early-boot memblock allocator is
handing out physical pages inside `[0x82000000, 0x821076c0)` for something
else (early page tables, per-CPU data, boot-time heap) *before* it reserves
the initrd region from `/chosen/linux,initrd-start`+`linux,initrd-end`. This
would explain a clean, contiguous, front-loaded overwrite of exactly the size
of whatever got allocated there, while leaving everything after that
allocation's end address untouched. Worth checking: does Linux's DT/initrd
handling reserve the initrd memblock as an atomic step at a well-defined
point in `setup_arch()`/`early_init_dt_scan_chosen()`, and could something in
our boot sequence (kernel command line, DTB property ordering, or a missing
`/reserved-memory` node) cause that reservation to happen too late or not at
all?

**Files:** `.worktrees/mem_at_broken_padding.bin` (64MB linear dump, not
committed — regenerable via the `--stop-on-uart`/`--dump-mem` command above).

## UPDATE (2026-08-25, later still): /reserved-memory fix — real but incomplete effect

Implemented the fix the prefix-overwrite finding pointed to: added an explicit
`/reserved-memory` child node for the initrd's physical range in
`tools/create_dtb.py` (alongside the existing OpenSBI reservation), using
plain `memblock_reserve()` semantics (no `no-map`, since the kernel still
needs normal read access to unpack it).

**Result: measurable change, not a fix.** Same test (`--stop-on-uart "broken
padding" --dump-mem`, 515M steps to trigger — identical trigger point to
before, so the fix did not prevent or defer the failure) was re-run and the
dump re-compared against source:

- Before fix: 1,078,976 differing bytes, a clean contiguous block `[0x0,
  0x1076c0)`, uniform `0xCC`.
- After fix: 923,763 differing bytes, scattered (not contiguous) within
  `[0x0, 0x2006aa]` — the corrupted *range* is larger (up to ~2.1MB vs
  ~1.05MB) but the actual differing-byte *count* is smaller, meaning most of
  that range now matches source with gaps of corruption rather than one solid
  block.

The corruption's new extent (~2MB) lines up with where the FDT magic
`0xd00dfeed` was previously found inside the initrd region (at
initrd_start+0x200000) in the pre-unpack dump — consistent with the
kernel's own `unflatten_device_tree()` working-copy allocation still landing
partially inside the initrd, despite the explicit reservation. Two plausible
explanations, untested:
1. The kernel's very first DTB scan pass (which is what actually processes
   `/reserved-memory` nodes, via `early_init_dt_scan_reserved_mem()`) may
   itself need a small allocation before `/reserved-memory` has been fully
   applied, or processes `/chosen` (and its own DTB relocation) before
   `/reserved-memory` in a way that isn't fully atomic.
2. Something in the added node's structure (`#address-cells`/`#size-cells`
   inheritance, node naming, or overlap with the OpenSBI reservation's
   address range) could be malformed in a way that causes a `dtc`/kernel FDT
   validator to reject or partially ignore it — worth checking with `dtc
   -I dtb -O dts` on the generated blob to confirm both reservation nodes
   parse as expected.

**Not reverted** — the fix is real (verified different, better-but-not-fully
corrected behavior) and worth keeping while the remaining scattered
corruption is investigated further.

## UPDATE: DTB structure validated — not a malformed-node issue

Ran `dtc -I dtb -O dts` on the generated blob to check hypothesis #2 from the
previous update. The `/reserved-memory` node decompiles cleanly with both
children present and well-formed:

```
reserved-memory {
    #address-cells = <0x02>;
    #size-cells = <0x02>;
    ranges;
    opensbi@80000000 { reg = <0x00 0x80000000 0x00 0x50000>; no-map; };
    initrd@82000000 { reg = <0x00 0x82000000 0x00 0x50b5e1>; };
};
```

No dtc warnings or errors. **Hypothesis #2 (malformed FDT structure) is
ruled out.** The remaining open question is genuinely about kernel-internal
allocation ordering/timing (hypothesis #1) — why the kernel's own DTB
working-copy allocation still appears to land partially inside a region
that's explicitly memblock-reserved. This needs either kernel source
(not available in this repo) or targeted in-emulator instrumentation of
early boot memory allocations to resolve definitively.
