# RESEARCH — PTE_PIX plane-path fence posture: the linear PIX arms are fence-blind on BOTH engines (measured on-device, engine PARITY — the HILB sibling measurement)

Builder: af3e62239ce2 · 2026-09-28 · HEAD at claim: 699e0734
Probe: `.builder_queue/probe_pix_frame_fence_af3e.py` — 3 runs byte-identical,
full stdout md5 `0046d2cec12b369ded117a0b3c57a578`, results md5
`e61510771d269ab895796adb25fca76e`.

## Question

Tick 4 (RESEARCH_hilb_frame_fence_af3e.md) measured the PTE_HILB frame path
fence-blind on both engines and left its sibling labeled: "the PIX-frame arms
are the same consult-free shape by source read but were NOT probed on-device."
This tick converts that label into a measurement. When a USER task's paged
access resolves through a PTE with PTE_PIX (0x8) set, does the LINEAR frame
path (pfn·256+offset) respect the GO-2 box fence on either engine?

## Method

- Harness IDENTICAL to tick 4's probe (the corrected BK-60 L4 discipline):
  image min_rows=64 → 2048 words contains the PT window unwrapped, two-pass
  bake with the LDI-r30 placeholder, tag 1535 / PT-arm 8211 / PTE 1548
  stamped into the image post-bake, USER via MODE_LATCH+KJMP, box
  [1200,1300) BYTES armed by the kernel prologue itself.
- Frame placement LINEAR (the only delta from tick 4, by design): word =
  pfn·PAGE_WORDS + offset. P1/P4: pfn 1, offset 64 → word 320 (byte 1280, IN
  box). P2/P3: pfn 5, offset 0 → word 1280 (byte 5120, OUT box). Deliberate
  symmetry: tick 4 placed its HILB frames at the SAME words (320/1280) via
  xy2d, so these two receipts differ ONLY in the PTE flag and the addressing
  transform — any verdict difference is attributable to the path.
- Verdicts from READBACK BYTES only: r10 for LD legs, post-run image words
  for ST legs (CPU `runner.image`; twin receipt `memory`), receipt fault
  fields for the E-K1 control. Never handler stdout.

## Source-read facts (verified by direct read before probing)

- Oracle paged LD PIX arm `glyph_isa_v2.py:908-910`: after the PTE V/W/U
  checks (:872-876), the PIX branch does `pix_word = pfn*PAGE_WORDS+offset`;
  `_mem_read(image, pix_word)` — NO `_addr_in_box` consult.
- Oracle paged ST PIX arm `glyph_isa_v2.py:1034-1036`: same shape, no consult.
- Twin `walk_ld` PIX arm `wgsl_glyph_isa_v2.py:396-398` and `walk_st` PIX arm
  `:431-434`: direct `mem_read/mem_write(pfn*PAGE_WORDS + offset)` — zero
  `addr_in_box` references in the paged branch; `walk_st`'s PIX arm returns
  false before the E-K1 consult is ever reached.

## Findings (measured, RTX 5090 + GlyphCPUv2, 3× byte-identical)

| Leg | Shape | CPU | WGSL twin |
|---|---|---|---|
| P1 in-box PIX LD (word 320) | control | r10=0x0ADF00D, clean | r10=0x0ADF00D, clean |
| **P2 out-box PIX LD (word 1280)** | read outside box | **r10=0x0ADF00D** | **r10=0x0ADF00D** |
| **P3 out-box PIX ST (word 1280)** | write outside box | **lands** (img_out=0x0ADF00D) | **lands** (img_out=0x0ADF00D) |
| P4 in-box PIX ST | control | lands | lands |
| C1 unpaged USER ST word 100 | fence-live control | E-K1 fault_addr 400 | refuses, halts 18 steps |

- **The fence-blind read is engine PARITY**: both engines return the
  out-of-box canary through the PIX path (P2). Same posture as tick 4's H2
  for the HILB path — the paged path has no box consult on either engine,
  now measured for LINEAR addressing too.
- **The fence-blind WRITE is the new measured shape for the PIX path**: P3
  lands the canary at image word 1280 (byte 5120, outside the armed box) on
  BOTH engines, clean exit, no fault record, while the UNPAGED ST to a word
  in the same box region E-K1s on both (C1: CPU fault_addr 400, twin refuses
  in 18 steps) — genuine path gap, not a dead harness. Combined with tick 4:
  BOTH frame modes (HILB + PIX) are write-fence-blind on both engines.
- fault_addr=2880 on all PT-armed legs is the BK-60-disclosed epilogue
  artifact (receipt store word 720, vpn 2 unmapped → 720×4), uniform across
  P1-P4 and identical to tick 4's H1-H4 legs — distinct from C1's real E-K1
  (400). The verdicts are image readbacks and are unaffected.
- Blast radius: unchanged from tick 4 — the image plane is shared state;
  kernel text pixels are fetch truth (GH-8b), so an out-of-box PIX ST is
  instruction-stream corruption class (BK-42/53 family). The PIX path is the
  DEFAULT frame mode for plain spatial workloads, so this is arguably the
  higher-traffic of the two fence-blind arms.

## Candidate item (backlog format) — BK-63

See the BK-63 row in `systems/GLYPH_BACKLOG.md`. Sequencing: co-lands with
BK-62 (its HILB sibling) in the BK-38..45 sequenced fence commit — the two
rows share the consult sites' decision structure and one gate family. NOT
claimable without Jericho per backlog header rules.

## What this receipt does NOT prove / not verified

- The PTE_U/W enforcement on the PIX path beyond the :872-876 shared checks
  was not independently probed (a PTE without W/U was never driven — same
  scope as tick 4).
- paged×tile composition still unprobed (the twin has no tile predicate at
  all until BK-51 lands).
- No engine or shader code changed: probe + receipt + BK-63 row + ledger
  only.
- Numbers structural (positions/flags/verdicts) — rule-1 floors do not
  attach.
- Self-assessed priority signal: this leg was picked because tick 4's
  receipt names the PIX arms as the remaining unprobed sibling
  (`.builder_queue/RESEARCH_hilb_frame_fence_af3e.md` § "What this receipt
  does NOT prove", first bullet) — the file:line that yielded the signal.
