# RECEIPT — BK-62/BK-63 twin frame-path legs: the WGSL paged walker's HILB and PIX frame arms measured consulting the GO-2 tile fence POST-TRANSLATION on-device (ruling 9714a363 clause 5, both frame modes)

Builder: af3e62239ce2 · 2026-09-29 ~00:4x CDT · HEAD at claim: 0f875164
(monitor CLEAN, tracked_dirty=0, queue=0; no RULING_*.md newer than HEAD —
newest RULING mtime 2026-09-27 18:00 < HEAD commit time 2026-09-29 00:29).

## What this closes

The BK-66-TWIN landing (7c4d791d) named exactly one frame-path gap in its
NOT-proved section: "PTE_HILB twin arm not device-measured in-tile (consult
covers it by code path; BK-62/63 twin legs are the frame-path line items)."
This tick converts that code-path claim into a device measurement for BOTH
frame arms — HILB and PIX — closing the clause-5 measurement debt on the
twin side the same way the BK-48 landing closed it for the UNPAGED arm.

## Gate

`tests/test_bk62_bk63_hilb_pix_frame_fence_twin.py` — 9/9 GREEN, pytest
(9 passed in 3.51s) AND standalone (`python3 tests/…` exit 0). Two pinned
GREEN runs byte-identical: stdout md5 `a6c2ee6ac81883ebed3367e2846126a2`
(both runs).

## Legs (device verdicts from ram/mmio/image readback, never stdout)

- **L1a HILB in-tile LD lands** — vaddr 192 → vpn 0/off 192 → HILB pfn
  0x000 (xy2d(0,0)=0) → frame word 192 (tile-grid row 6, col 0 — IN the
  (0,0,8,8) tile, past program text). r6=0x0ADF00D, mode USER, fault 0.
  Clause-3 over-confinement guard: lawful GH-25 HILB translation intact.
- **L1b HILB out-of-tile LD refused** — vaddr 0x300 → HILB pfn 0x300
  (xy2d(0,3)=5) → frame word 1280 (row 40 — OUT). fault_addr = 5120 =
  1280×4 — THE PADDR BYTE the fence judged (oracle :777 parity), r6
  unwritten, mode→SUPER.
- **L1c HILB out-of-tile ST refused** — same mapping, W granted: fault
  5120, canary NOWHERE in the image plane (word 1280 readback ≠ canary),
  mode→SUPER — the instruction-stream-class write (GH-8b) does not land.
- **L2a/L2b/L2c PIX siblings** — PIX pfn 0/off 192 (word 192, IN) lands
  clean; PIX pfn 5 (word 1280, OUT) LD refused at fault 5120 + ST refused
  with the image word untouched. Deliberate BK-62/BK-63 symmetry: same
  target words, only the PTE flag (0x10 vs 0x8) and transform differ.
- **L3 plain-arm shared-consult parity + twin-side paddr-ness evidence** —
  plain PTE pfn 0/off 192 (RAM frame, word 192 IN) lands; plain PTE **pfn
  1** with vaddr 100 → paddr 356 (row 11, OUT) refuses at fault 1420 =
  356×4. Note the shape: word 100 itself is IN the tile (row 3, col 4) —
  a vaddr-side consult would have ADMITTED this load; the refusal proves
  the twin consults the TRANSLATED paddr (ruling clause 1), twin-side.
- **L4 non-vacuity** — `paged_paddr_out_of_tile` neutered (return false)
  in a TEMP-COPY module → L1b's exact program READS the canary again
  (r6=0x0ADF00D). Real tree md5-pinned before/after
  (f4c4e30b8836d1a039ff8370a7268a1a).
- **L5 family** — test_bk48_wgsl_ld_tile_fence.py (BK-48 twin LD fence +
  BK-51 ST fence inside) green via subprocess on this tree.

## RED-first (shown at landing time)

`.builder_queue/red_bk62_bk63_af3e.py` (kept): runs L1b/L1c's exact
programs + stamps against the TEMP-COPY neutered module —
- HILB LD: fault=0, r6=0x0ADF00D, mode=1 → L1b's assertions FAIL (RED).
- HILB ST: fault=0, canary LANDS at image word 1280 (0x0ADF00D), mode=1
  → L1c's assertions FAIL (RED).
That is the pre-fix walk shape (BK-66-twin's own RED baseline, probe
probe_bk66twin_red_af3e.py) reproduced under this gate's harness: the
refusal legs are falsifiable, not vacuous. Real tree md5 unchanged
through the probe.

## Harness deltas vs the BK-48 gate (disclosed)

1. `img_seed` — the frame arms read the IMAGE plane (mem_read on the
   decoded word), not ram; canaries for frame legs are stamped into the
   image (the same plane the read consults). L1a's first draft seeded
   ram[0] and read program text (0xec5050) — caught by the leg's own run
   before any number was claimed; fixed to word 192 + image stamp.
2. Tile (0,0,8,8) instead of BK-48's (5,0,2,4): d=0 HILB frames span
   words 0..255 (rows 0..7), so a row-0 tile admits a lawful d=0 frame
   while word 1280 (d=5 / PIX pfn 5) stays out.
3. L3's out-of-tile plain leg uses pfn 1 (vaddr 100 → paddr 356) rather
   than an identity mapping — v1 used vaddr 500 (vpn 1, no PTE → the
   walker's 0xFFFFFFFF sentinel, a translation fault not a fence
   verdict) and v2 used vaddr 100 identity (word 100 is IN the tile →
   landed clean, which IS clause-3-correct); the landed leg keeps the
   pfn-1 shape because it doubles as twin-side paddr-vs-vaddr evidence.
   All three drafts' wrong shapes were caught by the legs' own verdicts
   before landing; no number was claimed from a defective run.

## What this PASS does NOT prove

- Oracle side untouched this tick: glyph_isa_v2.py md5
  bc422443730e6851a2a41f42376e8830 (unchanged; the oracle's HILB/PIX
  consults were already gate-pinned by tests/test_bk66_paged_tile_fence.py
  L1/L2 and the BK-65 HILB flag legs).
- No engine/shader code changed: all THREE WGSL copies byte-identical at
  f4c4e30b8836d1a039ff8370a7268a1a before and after (triple-sync posture
  verified by md5, not assumed).
- The gate exercises the twin via seeded box_mmio tile words
  (BK-48/BK-51 harness shape), not a full spawn(tile=…) GPU posture —
  the twin has no process table; posture parity with the oracle's
  spawn path is by construct, not measured here.
- fault_addr discrimination L1b pins paddr-ness for the OUT-of-tile
  refusal; the in-tile L1a leg has fault 0 (no fault words written) —
  the vaddr-in-tile/paddr-out shape is covered oracle-side (BK-66 L1/L7)
  and now twin-side by L3's pfn-1 leg.
- BK-62/BK-63 backlog rows remain JERICHO-CLAIMABLE (backlog header
  rules): this gate is the twin legs those rows name; it does NOT
  promote the rows or close them — the oracle-side legs of BK-62/63
  (box-armed, non-tile posture) remain separate scope.
- R1.4 fleet convergence, BK-49 stack-path, BK-50 door posture, BK-76
  exemption posture (still awaiting Jericho's ruling): all untouched.

Numbers structural — rule-1 floors do not attach (no rate/cost claims).
Measured at HEAD 0f875164, RTX 5090 (wgpu default device).
