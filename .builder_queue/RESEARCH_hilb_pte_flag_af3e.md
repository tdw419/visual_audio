# RESEARCH — PTE_W / PTE_U enforcement on the paged HILB frame path (tick 7)

- **Builder:** af3e62239ce2 · **Date:** 2026-09-28 ~03:0x CDT
- **HEAD at claim:** 84a23929 (tracked tree clean apart from this probe +
  receipt + backlog row + ledger append)
- **Probe:** `.builder_queue/probe_hilb_pte_flag_af3e.py`
- **3 runs byte-identical**, stdout md5 `5c977b4fe5634a8b5790195e140cb6fb`
  (results blob embedded; verdicts from image/RAM readback bytes and the
  CPU fault record, never stdout).

## Question

Tick 6 (RESEARCH_pte_flag_frame_af3e.md / BK-64) measured PTE_W/PTE_U
enforcement on the paged **PIX (LINEAR)** frame path only. Its NOT-proved
section names the HILB sibling explicitly: the shared pre-arm flag-check
site was pinned by check-order source read, not a measured HILB leg.
This tick drives the flag-cleared legs on the HILB arm.

Rule-5 prior-art grep: tick 2 = plain frames; ticks 4/5 = full-flag
V|W|U frame PTEs (flags held constant by design); tick 6 = PIX only.
No existing RESEARCH_*.md or backlog row closes the HILB flag legs.

## Harness

IDENTICAL to tick 6's `probe_pte_flag_frame_af3e.py` — min_rows=64
image, two-pass bake, tag/arm/PTE image-stamped, USER via
MODE_LATCH+KJMP, box [1200,1300) bytes armed by the kernel prologue,
CPU fault_reason via the tick-3 manual step-loop, twin verdicts from
receipt `memory[]` readbacks. ONLY deltas, by design:

- PTE flag = PTE_HILB (0x10) instead of PTE_PIX (0x8).
- pfn_field packed col|row<<8 for Hilbert placement: 0x1 → xy2d(1,0)=1 →
  word 1·256+64 = 320 (in-box); 0x300 → xy2d(0,3)=5 → word 5·256 = 1280
  (out-box). Same target words as ticks 4/5/6; these pfn encodings were
  CONFIRMED against both engines by tick 4's H1/H4 in-box controls.

## Legs and measured verdicts

| Leg | PTE | Op | CPU (oracle) | WGSL (twin) |
|---|---|---|---|---|
| H1w W-clear out-box ST | 0x30015 (V\|U, HILB, pfn 0x300) | ST canary→VA_OUT | FAULT `pte_invalid pte=0x30015 vaddr=0x3000 mode=USER op=ST` addr 12288, 21 steps, canary nowhere (img_out 0x0) | LANDS: img_out=0x0ADF00D, 25 steps, clean halt |
| H2w W-clear in-box ST | 0x115 (V\|U, HILB, pfn 0x1) | ST canary→VA_IN | FAULT addr 12544 `op=ST` | LANDS: img_in=0x0ADF00D, 25 steps |
| H1u U-clear out-box LD | 0x30013 (V\|W, HILB, pfn 0x300) | LD VA_OUT→r10 | FAULT `pte_invalid pte=0x30013 vaddr=0x3000 mode=USER op=LD` addr 12288 | RETURNS canary: r10=0x0ADF00D, 24 steps |
| C2 SUPER W-clear ST | 0x30015, no mode latch | ST canary→VA_OUT | FAULT `mode=SUPER op=ST` addr 12288, 10 steps | LANDS: img_out=0x0ADF00D, 11 steps |
| C1 unpaged E-K1 control | no PT | ST 4660→word 100 | FAULT addr 400, 18 steps | refuses, 18 steps, clean |

(C2 discloses tick 6's probe defect #1 shape: the PT-arm word 8211 is
read from RAM only per glyph :834, so the arm comes from the program's
own SUPER ST — image-stamped arms are invisible.)

## Findings

1. **W-bypass on HILB measured** — a W-clear HILB PTE is
   writable-through on the twin, in-box AND out-of-box, while the
   oracle faults both (`:1001` fires BEFORE the HILB arm `:1027-1032`).
2. **U-bypass extends to HILB** — U-clear HILB LD returns the canary on
   the twin; oracle faults `op=LD` in USER (`:873` before `:901-906`).
3. **SUPER W-clear lands on the twin** — walk_st's paged branch has no
   is_super consult; kernel read-only mappings are writable-through,
   HILB arm included (mirrors tick 6's PIX C2).
4. **C1 green on both** — the unpaged E-K1 fence is live; the gaps are
   flag-level, not harness artifacts.

## Consequence

The flag gap is in the SHARED pre-arm check site, confirmed by
measurement on both frame arms. BK-64's two predicate terms (PTE_W in
walk_st paged; PTE_U+is_user in walk_ld paged) sit before the frame
dispatch and therefore cover HILB with NO additional code — BK-65 is
filed as a measurement-completion row for BK-64 (its gate grows two
HILB legs; no new file, no new fix). Blast radius unchanged from
BK-62/63: image-plane writes are instruction-stream class under GH-8b.

## What this receipt does NOT prove

- No fix landed — research proposes, never lands engine/shader code.
- The twin has no fault channel (walk_st bool / walk_ld sentinel), so
  twin verdicts are readback-byte facts, not fault-record comparisons.
- Plain-frame and PIX flag legs are pinned by tick 6, not re-run here.
- paged×tile composition still unprobed (twin has no tile predicate
  until BK-51 lands).

## Rule-1 floors

Numbers structural (word values, md5s, step counts, byte-identity) —
no rate/cost claims; rule-1 floors do not attach.
