# RESEARCH tick 6: PTE_W / PTE_U enforcement on the paged PIX frame path —
# the frame-flag shapes no prior probe ever drove

Builder: af3e (cron af3e62239ce2) · 2026-09-28 ~02:0x CDT · HEAD at claim
71b4b364 · tracked tree dirty at claim with tick-5's build_map regeneration
lineage only (build_map.png/.json, committed separately at 71b4b364; this
tick adds probe + receipt + BK-64 row + ledger append). Probe
`.builder_queue/probe_pte_flag_frame_af3e.py` · v2 harness, 3 runs
byte-identical, stdout md5 `eab3b8cedd8328a87fecc9634b591fe6` (v1's C2 leg
was mis-designed — probe defect #1, disclosed below; all other v1 legs
matched v2 exactly, v1 stdout md5 `0e3524aa0a1d80fcddea82d5fb49a437`).

## Question (rule-5 checked)

Tick 5's receipt ("NOT proved", first bullet) and tick 4's name PTE flag
enforcement as unprobed on the frame paths: every prior paged probe drove
ONLY full-flag V|W|U PTEs (BK-60 L1's U-bypass was a PLAIN frame —
RESEARCH_wgsl_paged_fence_af3e.md D2 / RESEARCH_bk60_l4_oracle_remeasure
af3e.md F1; ticks 4/5 held flags constant to isolate the BOX-CONSULT
question). Prior-art grep (grep -l 'PTE_W|PTE_U' .builder_queue/
RESEARCH_*.md systems/GLYPH_BACKLOG.md → 4 hits, all plain-frame or
source-read) found no leg ever driving a W-clear or U-clear FRAME PTE on
either engine. The PIX frame path is the DEFAULT frame mode (tick 5), so
"does W actually mean read-only there?" is load-bearing for any guest
kernel that maps text pages read-only.

Source predictions at HEAD 71b4b364 (stated before the run):
- CPU: paged ST checks `(not V) or (not W) or (USER and not U)` at
  glyph_isa_v2.py:1001 BEFORE the PIX/HILB arms (:1033-1037) — W-clear
  frame ST must fault pte_invalid op=ST, in ANY mode (the W term has no
  mode gate). Paged LD checks V + (USER→U) at :873 before :907-910 —
  U-clear frame LD must fault pte_invalid op=LD in USER.
- WGSL: walk_ld's paged branch checks ONLY PTE_V (wgsl:389; tick 2 S1:
  PTE_U refs=0, PTE_W refs=0); walk_st's paged branch checks ONLY PTE_V
  (wgsl:425) then mem_writes through the PIX arm (:431-434) and returns
  false — no is_super consult. Prediction: both flag-cleared legs EXECUTE
  on the twin, in USER and SUPER alike.

## Method

- Harness IDENTICAL to tick 5's probe_pix_frame_fence_af3e.py: min_rows=64
  (32×64 = 2048-word image, PT window 1535/1536/1548 unwrapped — asserted
  ≥1549 at run time), two-pass bake, tag 0x505447@1535 + arm 1536@8211 +
  PTE@1548 stamped into image pixels post-bake, USER via MODE_LATCH(8192)
  +KJMP, box [1200,1300) bytes armed by the kernel prologue, LINEAR PIX
  placement (word = pfn·256 + offset). The ONLY delta by design is the
  PTE flag bits: same VA pair (vpn 12 off 64/0 → words 320/1280), same
  canary 0x0ADF00D, so this receipt differs from tick 5's only in flags.
- CPU verdicts via the tick-3 manual step-loop (probe runs GlyphCPUv2
  directly on the same PNG bytes, capturing fault_reason at the faulting
  step — probe defect #4 workaround, probe_faultreason_census_af3e.py
  :181-207 shape). Twin verdicts from the GlyphRunner receipt's memory[]
  word readbacks (the twin's image plane), never stdout.
- PTE stamps read back and asserted in the receipt itself:
  word 1548 = 0x50d (V|U|PIX, pfn 5 — W CLEAR), 0x50b (V|W|PIX, pfn 5 —
  U CLEAR), 0x10d (V|U|PIX, pfn 1 — W CLEAR in-box control).

## Findings (3 runs byte-identical, md5 above)

- W1 (W-clear PIX ST, out-of-box): CPU faults —
  `pte_invalid pte=0x50d vaddr=0x3000 mode=USER op=ST site=glyph_isa_v2`,
  fault_addr 12288, 21 steps, canary NOWHERE (img word 1280 stays 0).
  Twin: LANDS — img word 1280 = 0x0ADF00D after the run, walks to the
  epilogue clean, 25 steps. **MEASURED WRITE-PROTECT BYPASS on the twin:
  the twin's paged store ignores PTE_W entirely.**
- W2 (W-clear PIX ST, IN-box control): CPU faults `pte_invalid pte=0x10d
  vaddr=0x3100 ... op=ST` (12544). Twin: LANDS at word 320 (in-box).
  Isolates the flag from tick 5's box geometry — the bypass is the flag
  check's absence, not the out-box placement.
- U1 (U-clear PIX LD, out-of-box): CPU faults `pte_invalid pte=0x50b
  vaddr=0x3000 mode=USER op=LD` (12288); twin returns r10=0x0ADF00D.
  The tick-2 plain-frame U-bypass (D2) extends to the PIX frame path —
  the twin's paged LD ignores PTE_U in USER mode.
- C2 (SUPER W-clear ST control): CPU faults `pte_invalid pte=0x50d
  vaddr=0x3000 mode=SUPER op=ST` — the :1001 W check is confirmed live
  and mode-INDEPENDENT on the oracle (a SUPER store to a W-clear page
  faults). Twin: LANDS (img word 1280 = canary, 11 steps) — walk_st's
  paged branch has no mode consult at all, so even the KERNEL's
  read-only mappings are writable-through on the twin.
- C1 (unpaged out-of-box USER ST control): both engines refuse (CPU
  fault_addr 400 at 18 steps; twin halts at 18, value nowhere) — the box
  fence is LIVE under this harness; W1/U1 are flag-level gaps, not a
  dead probe.

## Consequence for the BK-38..57 sequenced fence commit / BK-62/63

The twin side of the sequenced commit gains a FIFTH line item, and the
cheapest to fix of the five (two predicate terms vs new consult paths):
add `PTE_W` to walk_st's paged PTE check and `PTE_U` (is_user) to walk_ld's
— bitwise mirrors of glyph_isa_v2.py:1001/:873. Without them, BK-62/63's
frame-fence gates can pass while the twin still ignores every
permission bit except V: a fence that says "you may write anywhere the
PT points" is coarser than the oracle's, and BK-59's "clean on both
engines" premise would be certified against a WEAKER twin semantics.
Filed as BK-64 with the flag-discrimination gate shape (RED legs = these
measured landings; rot-guard legs pin the oracle's mode-independent W
term and USER-only U term).

## Rule-1 floors

All cited numbers are STRUCTURAL (PTE encodings, word/byte addresses,
fault addresses, step counts, md5s, line numbers) — no rate, ratio,
latency, or cost is asserted; floors do not attach.

## Honesty — what this PASS does NOT prove

- The twin's non-paged (unpaged) walk_st/walk_ld branches were NOT
  re-probed for flags (BK-60 L1 covers the unpaged-adjacent plain shape;
  the unpaged branches have no PT to consult by construction).
- HILB-frame flag legs were not driven (PTE_HILB arm instead of PIX);
  by source read the flags are checked in the SAME shared predicate
  before the arm dispatch on both engines (oracle :1001 before :1033;
  twin :425 before :427), so the PIX measurement pins the check site —
  but that is inference from the check order, not a measured HILB leg.
- fault_reason strings exist only on the CPU side; the twin's receipt has
  no fault channel at all (walk_st returns bool, walk_ld a sentinel
  word) — the receipt's "the twin admits" verdicts are readback-byte
  facts, not fault-record comparisons.
- PTE_U in SUPER mode was not driven on the LD side (oracle checks U only
  in USER per :873; a SUPER U-clear LD leg would test nothing the source
  doesn't already pin — skipped as non-discriminating).
- Non-blocking smoke: legs need a live GPU; on a GPU-less runner the WGSL
  side fails at device acquisition.

## Probe defects (disclosed)

1. v1's C2 built with arm=False: the PT-arm word (8211) is read from RAM
   ONLY (glyph_isa_v2.py:834 — no image fallback, unlike the tag/PTE
   fetches), so the image-stamped arm is invisible and C2 ran UNPAGED
   (halted clean at 8 steps, store to plain RAM word 1280). v2 arms the
   PT from the program's own SUPER ST (prologue arm=True); C2 then
   faults pte_invalid op=ST mode=SUPER at 10 steps as predicted. v1's
   other four legs are byte-comparable and matched v2.
