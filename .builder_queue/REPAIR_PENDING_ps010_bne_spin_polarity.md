# REPAIR_PENDING_ps010_bne_spin_polarity.md

**Filed:** 2026-09-20, orchestrator cron lane (Glyph OS Event Chain af3e62239ce2)
**Step:** PS010 rung 1, brief `.builder_queue/brief_ps010_two_hart_mailbox.md`, row 1
**Status:** ~~BLOCKS step 1 (and 3–4).~~ **RULED 2026-09-20** —
`RULING_ps010_bne_spin_polarity.md` adopted OPTION 1 (bne→beq, word 2
`0xFE029EE3` → `0xFE028EE3`). Ruling landed and applied in the step-1
commit. This is a skeleton-sign-off change (locked constant
`MAILBOX_PROG_B` in `tools/pyshader_hart.py`).

## Symptom (measured, not reasoned — HEAD 30a7007c)

`MAILBOX_PROG_B` (tools/pyshader_hart.py:81-87) pins its spin as
`bne x5, x0, -4` (encoded word `0xFE029EE3`, decode-verified: fmt=B,
funct3=1, imm=-4). BNE branches when x5≠x0, so:

- Hart B run against `DMEM0` (flag=0) **never spins**: LW x5=0 → BNE
  falls through → x6=6 → EBREAK after **4** transitions. Measured:
  `steps=4, x5=0, x6=6, final_pc=4` (the pin says steps_b=5, x5=1, x6=7).
- Hart B run against flag=1 (post-A state) **spins forever** at pc=2 —
  `run_ctl_trace` budget exhaustion at 64 steps (measured).

The skeleton docstring's own timeline (tools/pyshader_hart.py:34-38:
"LW sees flag=0 … BNE taken (back to insn 1) … LW sees flag=1") requires
BEQ semantics — *spin while the flag is still zero*.

Also inconsistent: the brief's step-3 livock test specifies "hart B's
spin condition never satisfiable (flag word never written)" — with BNE
polarity, B alone on flag=0 trivially completes (4 steps), so step 3's
RED leg is unreachable with the locked program as-is.

Hart A is unaffected: measured `steps=6, dmem=[1,7,123], x1=7, x9=1,
x10=0, x31=0` — exactly its pin.

## Constraint

`tools/pyshader_hart.py` program text and its image pin are LOCKED
(brief scope; test `TestImagePins::test_prog_b_image_pinned` asserts
`0xFE029EE3`). I did NOT edit either.

## Options (cheapest first)

1. **Fix the constant + pin (RECOMMENDED).** Change insn 2 of
   `MAILBOX_PROG_B` to `beq x5, x0, -4` (encodes `0xFE028EE3`; measured
   via tools/rv32i_asm + decode_ref), update `MAILBOX_B_WORDS[2]` in
   tests/test_pyshader_hart.py, and correct the docstring text
   "bne"→"beq" (2 sites: comment at :80, program text :84). Hand pin
   (steps_b=5, rounds=7, x5=1, x6=7) then becomes reachable as written —
   no other pin changes. Smallest diff, keeps every locked signature.
2. **Re-pin to the BNE program as-is** (B completes in 4 steps with
   x5=0/x6=6; rounds=6; the "mailbox spin" story dies — B never waits).
   Rewrites the module docstring pin, brief pinned-facts, and step-3's
   RED-leg premise. Larger blast radius, weaker gate semantics.
3. **Spin on the payload pin instead** (`lw x7, 4(x10)` then
   `bne x5, x7, -4`): keeps a BNE but adds an insn, changing steps_b,
   rounds, and the image pin broadly. Most churn, no benefit.

## Requested ruling

Pick an option; return as `RULING_ps010_bne_spin_polarity.md`. Until
then I hold this file and take no further PS010 rows.
