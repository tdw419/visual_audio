# RULING_ps010_steps_b_pin — steps_b pin corrected 5 → 6; ALU-branch step counter fix authorized

**Issued:** 2026-09-20, orchestrator cron lane (Glyph OS Event Chain af3e62239ce2)
**Companion to:** RULING_ps010_bne_spin_polarity.md (word-2 polarity).
**Authority basis:** technical correctness (pin arithmetic + a counter bug
in this lane's own step-1 work-in-progress); no [J-DECISION] bypassed;
PS010 rung 1 is GO per RULING_ps009_fork_cleared_ps010_go.md. Jericho may
overturn in-channel.

## Measured facts (probes in .builder_queue/probe_ps010_*.py, HEAD edefc187 + step-1 WIP)

1. **Faithful round-loop trace** (probe_ps010_labeled.py — exact copy of
   the landed double-buffer loop, order="ab", spr=1):

```
round 1: a ALU pc->1        b ALU pc->1
round 2: a ALU pc->2        b CTL pc->2            (B lw, x5=0)
round 3: a CTL pc->3 WROTE dmem[0]=1   b CTL pc->1 (B beq TAKEN, x5=0)
round 4: a ALU pc->4        b CTL pc->2            (B lw AGAIN, x5=1)
round 5: a CTL pc->5 WROTE dmem[1]=7   b CTL pc->3 (B beq not taken)
round 6: a CTL pc->7        b ALU pc->4            (B addi x6=7)
round 7: a HALT pc=7        b HALT pc=4
```

   A = 6 transitions (r1..r6, EBREAK r7 uncounted) — matches the pin.
   **B = 6 transitions** (addi, lw, beq-taken, lw, beq-not-taken, addi;
   EBREAK r7 uncounted), rounds = 7, final dmem [1,7,123,0,...],
   A x1=7/x9=1/x10=0/x31=0, B x5=1/x6=7 — every pin value holds EXCEPT
   steps_b.

2. **The docstring's 5 is a trace slip** (tools/pyshader_hart.py:34-38):
   after the r3 BEQ is taken, B's r4 instruction is the LW at pc=1 — the
   docstring narrative ("Round 4: LW sees flag=1, falls through") then
   treats the BEQ as if it were still ahead of the LW, dropping one spin
   iteration. Under the PS008 convention the docstring itself cites
   (every dispatched insn counts; the halting EBREAK does not), B = 6.
   Same error family as the brief's own step-3 pc slip and the PS007
   fib-offset slip — both corrected by ruling.

3. **Counter bug in the step-1 WIP** (found by the pin refusing to
   leave RED): `_drive_one` incremented `steps` only on the CTL branch,
   so ALU instructions double-executed per round (hart races ahead;
   measured rounds=5, steps_a=3, steps_b=4). The fix is one
   `steps += 1` in the ALU branch of tools/pyshader_hart.py.

## Ruling

1. `steps_b` pin: **5 → 6** everywhere it gates (docstring pin lines,
   test gate clause). `rounds=7`, `steps_a=6`, all reg/dmem pins
   UNCHANGED. The docstring's B timeline is corrected to the measured
   r1..r7 trace above. The brief's step-table text (line 65) stays as
   history — superseded by this ruling, per the PS007
   blocker→ruling precedent (REPAIR text is never rewritten to match).
2. The one-line ALU-branch counter fix in `run_two_hart`'s helper is
   authorized (builder's own WIP code, not a locked interface).

## What this changes about step-1 evidence

RED evidence for step 1 remains the captured NotImplementedError tail
(stub in place). The mid-run RED chain (rounds 5≠7 from the counter bug;
steps_b 6≠5 pin conflict) is receipt material, pasted in the commit.

next: PS010 step 1 GREEN under this ruling (steps_b==6)
