# RESEARCH — PTE_HILB frame-path fence posture: the paged HILB arms are fence-blind on BOTH engines (measured on-device, engine PARITY)

Builder: af3e62239ce2 · 2026-09-28 · HEAD at claim: dbee2164
Probe: `.builder_queue/probe_hilb_frame_fence_af3e.py` — 3 runs byte-identical,
full stdout md5 `0ec4bece7eda293bde66037542f572ce`.

## Question

BK-60's HONESTY section left one walk surface unprobed: "PTE_HILB frame-path
fence posture NOT probed ... same consult absence by source read, labeled."
This tick converts that label into a measurement. When a USER task's paged
access resolves through a PTE with PTE_HILB (0x10) set, does the frame-word
path respect the GO-2 box fence on either engine?

## Method

- Harness = the corrected BK-60 L4 discipline (image min_rows=64 → 2048 words,
  contains the PT window unwrapped; two-pass bake with the LDI-r30 placeholder;
  tag 1535 / PT-arm 8211 / PTE 1548 stamped into the image post-bake; USER via
  MODE_LATCH+KJMP; box [1200,1300) BYTES armed by the kernel prologue itself).
- Frame placement computed LOCALLY (Hacker's Delight xy2d replicated from
  `glyph_isa_v2.py:642-664`), then confirmed by the engines' own behavior:
  pfn_in = 0x1 (col 1, row 0, d=1) → frame word 320 = byte 1280 (IN box);
  pfn_out = 0x300 (col 0, row 3, d=5) → frame word 1280 = byte 5120 (OUT box).
  H1 returning the canary proves the probe's mapping matches both engines'
  `_hilb_frame_pix_word` / `hilb_frame_word`.
- Frame canaries stamped into the IMAGE (HILB frame words resolve on the image
  plane of both engines — scanline `addr_to_xy` shared, verified by readback).
- Verdicts from READBACK BYTES only: r10 for LD legs, post-run image words for
  ST legs (CPU `runner.image`; twin receipt `memory`), never handler stdout.

## Source-read facts (verified by direct read before probing)

- Oracle paged LD HILB arm `glyph_isa_v2.py:901-906`: after the PTE V/W/U
  checks (:872-876) the HILB branch does `_mem_read(image, pix_word)` — NO
  `_addr_in_box` consult (the consult exists only on the UNPAGED ST arm :1041).
- Oracle paged ST HILB arm `glyph_isa_v2.py:1027-1032`: same shape, no consult.
- Twin `walk_ld` HILB arm `wgsl_glyph_isa_v2.py:393-394` and `walk_st` HILB arm
  `:427-429`: direct `mem_read/mem_write(hilb_frame_word(...))`, zero
  `addr_in_box` references in the paged branch; `walk_st`'s HILB arm returns
  false before the E-K1 consult is ever reached.

## Findings (measured, RTX 5090 + GlyphCPUv2, 3× byte-identical)

| Leg | Shape | CPU | WGSL twin |
|---|---|---|---|
| H1 in-box frame LD (word 320) | control | r10=0x0ADF00D, clean | r10=0x0ADF00D, clean |
| **H2 out-box frame LD (word 1280)** | read outside box | **r10=0x0ADF00D** | **r10=0x0ADF00D** |
| **H3 out-box frame ST (word 1280)** | write outside box | **lands** (img_out=0x0ADF00D) | **lands** (img_out=0x0ADF00D) |
| H4 in-box frame ST | control | lands | lands |
| C1 unpaged USER ST word 100 | fence-live control | E-K1 fault_addr 400 | refuses, halts 18 steps |

- **The fence-blind read is engine PARITY, not a divergence**: both engines
  return the out-of-box canary through the HILB frame path (H2). This mirrors
  BK-60 D3's plain-frame result — the paged path has no box consult on either
  engine — now measured for the frame path GH-25 Hilbert workloads actually
  take.
- **The fence-blind WRITE is the new measured shape**: H3 lands the canary at
  image word 1280 (byte 5120, outside the armed box) on BOTH engines, clean
  exit, no fault record. The UNPAGED ST to the same box region E-K1s on both
  (C1) — so this is a genuine path gap, not a dead harness. A USER task whose
  page table maps a HILB PTE writes any frame word on the image, regardless of
  the GO-2 box the kernel armed.
- fault_addr=2880 on all PT-armed legs is the BK-60-disclosed epilogue artifact
  (receipt store word 720, vpn 2 unmapped → 720×4), uniform across H1-H4; the
  verdicts are image readbacks and are unaffected. C1 (unarmed) shows the real
  E-K1 (fault_addr 400), confirming the two shapes are distinguishable.
- Blast radius note: the image plane is shared state — frame words include
  kernel text pixels under GH-8b (pixels-are-fetch-truth). An out-of-box HILB
  ST is therefore in the BK-42/53 instruction-stream-corruption class, not just
  a data read/write: the same class BK-39's PUSH leg disclosed.

## Candidate item (backlog format) — BK-62

See the BK-62 row in `systems/GLYPH_BACKLOG.md`. Sequencing: joins the
BK-38..45/57 sequenced fence commit's consult-site map as its paged-HILB
member (with the PIX-frame sibling, source-read-same-arm, posture-decided-at-
landing). NOT claimable without Jericho per backlog header rules.

## What this receipt does NOT prove / not verified

- The PIX-frame arms (PTE_PIX, `glyph_isa_v2.py:907-909`/:1033-1035,
  `wgsl_glyph_isa_v2.py:396-397`/:431-433) are the same consult-free shape by
  source read but were NOT probed on-device — labeled, like BK-60's D3 was
  before tick 2.
- paged×tile composition still unprobed (the twin has no tile predicate at all
  until BK-51 lands).
- No engine or shader code changed: probe + receipt + BK-62 row + ledger only.
- Numbers structural (positions/flags/verdicts) — rule-1 floors do not attach.
- Self-assessed priority signals: this leg was picked because BK-60's HONESTY
  section names it as the remaining unprobed surface
  (`systems/GLYPH_BACKLOG.md:446-447`, the file:line that yielded the signal).
