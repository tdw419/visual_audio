# RULING_ps007_fib_branch_offset

Issued: 2026-09-19 ~21:35 CDT, by the PS007 lane (Hermes/GLM, skeleton
author) — this is the skeleton-sign-off decision the ticket requested.
Cites: REPAIR_PENDING_ps007_fib_branch_offset.md.

## Decision: OPTION 1 — word 6 = `BNE x5, x0, -20` (0xFE0296E3)

The ticket's measured conflict is CONFIRMED by independent
reproduction on this lane: the original `-8` pin in the skeleton
docstring was an authoring error (byte-offset vs insn-offset
confusion in the pin itself), and under execute_one's gated
pc+1+imm/4 convention neither -8 nor the brief's "-2 insns" reaches
pc=2. The ticket's probe and its 0xFE0296E3 encoding are correct.

## Independent verification performed before ruling (not taken on
## faith from the ticket)

- `decode_ref(0xFE0296E3)` → fmt=B, imm=-20, rs1=5, rs2=0, funct3=1 ✓
- The 7-word program with the new word 6, run through the BUILDER'S
  OWN step-5 `run_fde` at x5=8: 42 executed instructions, final
  x1=34, x2=55, x3=55, x5=0 — the brief's hand-computed pin, EXACT.
- (Probe note, for the record: the lane's first reproduction attempt
  failed the pin with x1=1/x2=1 — that was a transcription error in
  the probe's word 4 (0x00010113 = ADDI x2,x2,0 instead of
  0x00018113 = ADDI x2,x3,0), NOT a defect in the ruling, the ticket,
  or the builder's run_fde. The corrected probe passes. Second
  lesson today: expected-value arithmetic is where verifiers slip.)

## What changed

- `tools/pyshader_fde.py` line ~62: pinned word 6 is now
  `BNE x5, x0, -20` (offset -5 insns, word 0xFE0296E3), comment
  updated, ticket cited. This is the ONLY interface-affecting change;
  it is a pin correction, not a signature/State/convention change.
- The brief's `-2` (line 33 area) should be read as superseded by
  this ruling: -5 insns / -20 bytes. (Brief left unedited — the
  ruling + skeleton comment are the authority.)

## Builder instruction (step 6 un-HOLD)

Step 6 (`gate_fibonacci`) is ELIGIBLE again as of this ruling's
commit. Populate per the brief's step-6 clause; the FIB program
words are yours to construct from the corrected skeleton comment.
Mark the blocker note RULED with a pointer to this file per the
contract — do not delete it.

/s/ skeleton author, PS007 lane

---

## ADDENDUM 2026-09-20 — SUPERSEDED by RULING_ps008_branch_convention

The branch convention this ruling pinned (-5 insns / -20 bytes with
executor arithmetic pc + 1 + imm//4) is SUPERSEDED by
`.builder_queue/RULING_ps008_branch_convention.md` (Jericho, in-channel,
2026-09-20 ~02:3x): SPEC semantics everywhere — taken next pc =
pc + imm//4, NO +1. FIB word 6 re-encoded accordingly:
0xFE0296E3 → 0xFE0298E3 (BNE x5, x0, -16; -4 insns; target pc=2).

The hand-computed PIN (42 executed instructions, x3 seq
2,3,5,8,13,21,34,55, final 34/55/55/0) is UNCHANGED — verified
end-to-end on the landing run (RED first: old executor + new word
faults `IndexError: fetch: pc 7 out of bounds` at the FIB gate; GREEN
after the execute_one edit, pin exact). This addendum records the
audit trail only; the text above is preserved unedited per contract.
