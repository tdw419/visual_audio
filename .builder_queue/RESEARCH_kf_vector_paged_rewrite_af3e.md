# RESEARCH — the KFAULT_PC VECTOR WORD itself is paged-rewriteable: a
# tile-confined task rewrites the RAM word the trap arms vector THROUGH
# TRANSLATION (plain-page pfn, not even PIX), and the NEXT fault vectors
# wherever the task chose — composing with tick-12's pixel rewrite into
# full vector+trampoline control of the containment mechanism

- Tick: 2026-09-28 ~01:0x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
- HEAD at claim: 45a8ed79 (re-verified via git rev-parse; monitor
  fingerprint head matched — the delta vs tick 12's fbdef1be is my own
  tick-12 landing). Mailbox re-verified: newest RULING_*.md mtime
  1790550013 < HEAD commit time — no binding new work.
  QUEUE_STATE.json: 0 non-landed tickets; CLAIM QUEUE empty → Phase 1c
  eligible. Rule-5 prior-art grep BEFORE harness build: BK-52 (kf=0,
  unpaged), BK-53/55 (vector hijack via UNPAGED primitives —
  PARALLEL_ST / the twin's box_mmio door; the blind-WRITE variant was
  explicitly called "not dead" in RESEARCH_postfix_hijack_recheck), tick
  12 / BK-70 (trampoline PIXELS paged-rewritten; vector WORD left
  unmapped, UNMEASURED), BK-56 (USER MMIO READ returns 0 post-69a53298 —
  aim de-fang, write path out of scope). No row measures a paged USER ST
  landing IN the vector word. Net-new.
- QUESTION (tick 12's own NOT-proved list, item 1): can the task rewrite
  KFAULT_PC (word 8193 = BOX_MMIO_BASE/4+1) itself, so the NEXT trap
  vectors to a PC the task chose — not just into a trampoline it
  rewrote, but anywhere in the image?

## METHOD

- Probe: .builder_queue/probe_kf_paged_af3e.py (untracked, landed
  modules only, HEAD 45a8ed79). Harness = the REAL
  GlyphProcessTable.spawn(image, tile=(256,19,1,2)) posture (item-29):
  the TABLE arms KFAULT_PC = 30<<16 = 1966080 (read back in every
  control leg) and wrap_with_reaper plants HALT (word 16737095) at pixel
  (0,30) = image word 1920 (w=64, cols_instrs=16, engine cols_instrs=16
  — see probe-defect disclosure). PT armed by the task's own lawful
  in-tile ST to word 8211; tag 0x505447 image-stamped at word 1535, PT
  base word 1536. Verdicts from exit_status + cpu fault fields +
  cpu.output + kf RAM readback + redirect-pixel image readback BYTES,
  never stdout. PRT opcode color resolved at runtime from OpcodeMapV2.
- ADDRESSING KEY (source-read, then measured): the paged arm applies to
  every USER access when pt_base != 0 (glyph_isa_v2.py:836 LD / :968 ST
  — the SUPER MMIO exemption is USER-scoped). The vector word is RAM,
  so the rewrite uses a PLAIN page (PTE = V|W|U, pfn 32, 0x2007 at PT
  word 1569): vaddr (33<<8)|1 = 8449 → paddr = 32*256+1 = 8193, landed
  by the plain-page ST arm :1038-1074. A PIX PTE (run-1) targets the
  IMAGE and wraps mod w*h — measured landing at image word 1, NOT RAM;
  probe defect caught pre-evidence and corrected.
- Results: my re-run of the probe at this HEAD reproduced the on-disk
  results file byte-identically (file md5 0ed2499041b6da0226ac48dab43fb6a3;
  deterministic results md5 4724518667afe20696053e53f6be56a8). The
  originally-pinned run md5 6cd043ba1ce078a3714ad9a3b891b0dd was from a
  pre-final iteration and is superseded by the verified number.

## FINDINGS (all measured at HEAD 45a8ed79)

- V1 THE VECTOR WORD IS PAGED-REWRITEABLE: one USER ST (vaddr 8449,
  plain-page PTE) writes the packed PC (30<<16)|8 = 1966088 INTO RAM
  word 8193 — readback kf_word_after == 1966088, replacing the planted
  1966080. The task then takes a pte_invalid fault on an unmapped vpn
  (vaddr 5120, pte=0x0) and the pte_invalid vectoring arm :890 reads kf
  LIVE from RAM: final_pc = (32, 30) — pixel x=32 = 8*INSTR_WIDTH, the
  task's chosen col, NOT the planted trampoline (0,30) where C1/C2
  park. The engine opcode-None-halts at (32,30) (payload row is zero in
  this leg — disclosed); exit 1, mode SUPER. THE REDIRECT IS THE
  FINDING: the trap arms to attacker-chosen coordinates because the
  arm value itself was rewritten through translation.
- V2 THE FULL COMPOSE EXECUTES: same V1 vector rewrite PLUS PIX-frame
  stores (vpn-12 PTE pfn 7, vaddrs 3232..3235 → image words
  1952..1955) painting attacker `PRT r6` at pixel (32,30) — exactly
  where the redirected vector lands. After the fault: cpu.output ==
  [3235] — the attacker PRT EXECUTED AT THE TASK-CHOSEN VECTOR in
  SUPER mode (PRT prints r6 = 3235, the last store address; the
  immediate pixel held 52, disclosed — same operand-placement note as
  tick 12). Loud tail: opcode-None halt at (36,30) on the zero pixel
  after the 4-pixel payload (the tick-9-F2 shape). Redirected
  readback [16208720 (the REAL PRT color), 6, 52, 0]. VECTOR WORD AND
  TRAMPOLINE PIXELS BOTH REWRITTEN THROUGH TRANSLATION — the task
  controls where the trap goes AND what executes when it gets there.
- C1 NO-TRANSLATION CONTROL: vpn-33 PTE left 0 — the rewrite ST itself
  faults `pte_invalid pte=0x0 vaddr=0x8404 mode=USER op=ST` (fault_addr
  33796), vectors to the REAL trampoline (0,30), kf word still 1966080,
  planted HALT intact: the fence/translation path is what carried the
  rewrite, probe discriminating.
- C2 ROT-GUARD (tick-12 R1 verbatim): arm paging, no rewrite, unmapped
  LD vectors to the REAL HALT at (0,30), kf 1966080 — the honest reaper
  shape stays green (never weaken a live handler).
- Probe-defect disclosures (both caught pre-evidence, before the pinned
  runs): (1) run-1 used a PIX PTE for the rewrite — it landed in the
  IMAGE (word 1 via the mod-w*h wrap), not RAM; corrected to a plain
  page after reading the ST arm ordering. (2) run-2/3 baked
  cols_instrs=8 with a 16-instr-row layout — the engine's row_width
  wrapped instructions mid-sequence and corrupted a stored immediate
  (r6 read 0xC8B for a 3209 LDI, caught by the per-step trace landing
  the payload at the wrong word); corrected to cols_instrs=16 on BOTH
  baker and GlyphProcessTable. (3) the redirect target (x=32) was
  outside the 32px-wide run-2 image — walk-off before the payload could
  run; widened.

## CONSEQUENCE

The containment posture's last fixed point is gone: tick 12 showed the
trampoline PIXELS are paged-writable; this tick shows the vector WORD
is too — through the PLAIN page arm, so even a hypothetical
"protect the trampoline rows" fix leaves the arm itself attackable
(the vector can simply be pointed AWAY from any protected row). BK-56's
read de-fang is confirmed irrelevant to the write side (the task never
reads 8193: blind rewrite). The E-K1/pte_invalid trap arm reads kf LIVE
with zero validation (:851/:890/:983/:1016/:1061/:1086 — every site
reads memory[KFAULT_PC_ADDR>>2] and vectors), so the kernel's own
control flow is guest-data-driven in every paged posture. This binds
BK-66's flagged consult-posture decision AND BK-52's vector-guard row
to the same composition: any fix must cover BOTH the vector word (RAM
side) and the trampoline pixels (image side), and must survive the
paged arms — not just the unpaged E-K1 path BK-52 originally targeted.

## CANDIDATE BK-71 (filed to systems/GLYPH_BACKLOG.md)

Measured-completion composition row: BK-66/BK-70's gate grows KF legs
(same file family as BK-70's RPR legs — tests/test_bk66_paged_tile_fence.py
or a sibling tests/test_bk71_kf_vector_paged_rewrite.py): KF-L1 the
KFAULT_PC RAM word must not be paged-writable from a tile-confined USER
task (RED today: V1 kf_word_after == 1966088); KF-L2 post-trap PC must
equal the kernel-armed vector, not a guest-chosen one (RED today:
final_pc (32,30) != (0,30)); KF-L3 C2's honest-catch shape stays green
(never weaken a live handler); KF-L4 C1 no-translation rot-guard green.
Takes BK-66's consult-posture decision MECHANICALLY once decided (the
same paddr-side consult that protects words 960..963 protects 8193) —
no new design judgment.

## What this receipt does NOT prove

- Oracle only. Twin side not probed (no tile predicate, BK-51; also no
  spawn(tile=...) posture on-device).
- The SUPER MMIO exemption itself (:836/:968) was not probed — a
  SUPER-mode task writing the MMIO window directly is a different
  posture (spawn(tile=...) is USER by construction).
- Whether a pfn ceiling fault (pfn > 65536) or pt_tag mismatch in the
  rewrite ST also re-vectors correctly: not probed (the tag-mismatch
  site :851 and ceiling site :1061 read kf the same way by source
  read, labeled not measured).
- The GH-16 tick-handler arm (KTICK_PC) and KSYS_PC: same LIVE-read
  family by source read (:1166, :1364), not probed this tick.
- Steps not pinned (engine run() bookkeeping); verdicts are
  exit/fault/output/PC/readback facts.
- No fix landed — research proposes, never lands engine/shader code.
- Rule-1 floors do not attach (all numbers structural — word values,
  coordinates, md5s; no rate/latency/cost claims; floors file not
  cited).

## ARTIFACTS

- .builder_queue/probe_kf_paged_af3e.py (probe md5
  256763c7988d7493381abe5bd4e0214e; re-run at HEAD 45a8ed79 byte-identical
  to the pinned runs — verified by this session)
- .builder_queue/probe_kf_paged_af3e_results.json (results + deterministic
  results md5 4724518667afe20696053e53f6be56a8; file md5
  0ed2499041b6da0226ac48dab43fb6a3)
- systems/GLYPH_BACKLOG.md: BK-71 row (this receipt is the source)
