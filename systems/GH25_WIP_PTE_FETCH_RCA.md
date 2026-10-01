# GH-25 WIP regression — ROOT CAUSE (confirmed by instrumentation)

## Symptom
GH-23 libc gate: 3/5 legs fail with the GH-25 WIP (image-first PTE fetch in
`tools/glyph_isa_v2.py` LD/ST walker). 5/5 green at clean HEAD. Probe:
/tmp/gh23_walk_probe2.py, /tmp/gh23_pte_trace13.py.

## Chain (receipt-grade, measured not inferred)
1. The GH-23 libc bake is 240x64; the page-table window (words 1536..1791)
   overlaps BAKE-TIME program text / zero padding in the image pixels
   (text region + padding live below/around word 1536 in the 15360-word
   image). Measured bake-time image pixels: word 1542 = 0x3ff (vpn-6 PTE
   slot), word 1544 = 0xec5050, word 1546 = 0x1ca0 (vpn-10 slot).
2. With the WIP's image-first PTE fetch, the GH-18 dispatcher's LD of the
   table word 1570 (sys_brk=214 slot) walks vpn 6 -> pte_idx 1542.
   Image pixel says 0x3ff — text garbage — but 0x3ff has V=1 (pfn=3,
   flags=0xff). The walker accepts it, translates table word 1570 to
   pix_word 3*256+34 = 802 (program text), reads 0xec5050 and KJMPs the
   dispatcher to packed PC 0xec5050 → cell 24336 → void. brk tile never
   runs: mem[723] stays 0xa00 (raw seed), legs fail.
   Measured: exactly ONE walker image-PTE read in the whole run
   (step 2334, addr 1542, val 0x3ff), run "halts" 2340 steps.
3. The WIP's `if pte == 0: fall back to RAM` guard is unsound: bake-time
   PT-window pixels are NONZERO garbage, not zero. Every landed GH-17/18/
   20/21/22/23 kernel writes its live PTEs to RAM (the walker's PT window
   in the image is never maintained by the CPU's _mem_write — PTE writes
   go to self.memory; there is no write-through for words 1536..1791).

## Why image-first was chosen (GH-25 need)
The GH-25 parity harness stamps the vpn-12 Hilbert PTE into the IMAGE only
(tests/test_gh25_hilbert_paging.py::_write_pte) because the WGSL engine
reads only pixels. The WGSL twin fetches PTEs from image pixels, so the
CPU twin must see the image-stamped PTE too.

## Sound fix (supersedes image-first)
RAM-first, image-fallback on the CPU LD/ST PTE fetch:
    pte = self.memory[pte_idx]
    if pte == 0 and pte_idx < w_img*h_img:
        pte = self._mem_read(image, pte_idx)
- GH-17/18/20/21/22/23: RAM PTEs are nonzero → identical behavior to HEAD
  (image never consulted).
- GH-25: RAM PTE for vpn 12 is 0 (baked image carries it) → image fetch
  returns the Hilbert PTE. Both engines agree.
- WGSL twin already implements image-only; its box_mmio view of the PT
  window is all zeros on the GPU, so image-fallback there = its current
  behavior — no WGSL change needed.
Coherence rule: never write a PTE to RAM in a GH-25 image (the harness
doesn't), and never rely on bake-time image PTEs in GH-17..23 images.

## Verification plan
- RED: /tmp/gh23_repro.txt (3 legs fail with WIP at 19:2x).
- GREEN: pytest tests/test_gh23_libc_runtime.py → 5/5; GH arc GH15..GH25;
  run_gate_gh18.sh invariant 14/14.
