# RULING_ps010_bne_spin_polarity — Option 1 adopted (BNE → BEQ, word 2 of MAILBOX_PROG_B)

**Issued:** 2026-09-20, orchestrator cron lane (Glyph OS Event Chain af3e62239ce2)
**Disposes:** `REPAIR_PENDING_ps010_bne_spin_polarity.md` (filed 490bf8b8) — marked RULED with this pointer; the blocker file is NOT deleted.
**Authority basis:** this is a technical correctness ruling over a locked constant in the builder's own lane (not root/external/constitutional; no [J-DECISION] row is bypassed — PS010 rung 1 is GO per RULING_ps009_fork_cleared_ps010_go.md). Jericho may overturn in-channel; a later `RULING_ps010_*` supersedes this one and the pin reverts per its text.

## Decision

OPTION 1, exactly as recommended by the ticket: insn 2 of `MAILBOX_PROG_B`
(tools/pyshader_hart.py) changes `bne x5, x0, -4` → `beq x5, x0, -4`
(encodes `0xFE028EE3`), the image pin `MAILBOX_B_WORDS[2]` in
tests/test_pyshader_hart.py changes `0xFE029EE3` → `0xFE028EE3`, and the
program-text/comment/docstring sites naming "BNE" for that insn are
corrected to "BEQ". Every other locked signature, pin, and constant is
UNTOUCHED. Rationale: measured at HEAD edefc187, B-as-locked cannot
reach the hand pin either way (flag=0: falls through, 4 steps, x5=0/x6=6;
flag=1: spins to budget exhaustion at pc=2) — the docstring's own
timeline (spin while flag==0, fall through on flag==1) is BEQ semantics.

## Re-derivation before GREEN (hand trace, steps_per_round=1, order "ab")

Round 1: A insn0 (x9=1) | B insn0 (x10=0)
Round 2: A insn1 (x10=0) | B insn1 LW x5=0
Round 3: A insn2 SW dmem[0]=1 | B insn2 BEQ taken (x5=0) → pc=1
Round 4: A insn3 (x1=7) | B insn1 LW x5=1 → falls through, pc=3
Round 5: A insn4 SW dmem[1]=7 | B insn3 x6=1+6=7
Round 6: A insn5 JAL → pc=7 | B insn4 EBREAK halts (steps_b=5)
Round 7: A insn7 EBREAK halts (steps_a=6) → rounds=7
Final dmem [1,7,123,0,0,0,0,0]; A x1=7/x9=1/x10=0/x31=0; B x5=1/x6=7.
Executor sanity at this revision: BEQ-B alone on flag=1 completes
steps=4, x5=1, x6=7 (measured); alone on flag=0 spins (correct spin
semantics — the two-hart schedule is what unblocks it at round 4).

next: PS010 step 1 (run_two_hart double-buffer mechanics) under this ruling
