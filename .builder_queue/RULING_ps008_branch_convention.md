# RULING_ps008_branch_convention

Issued: 2026-09-20 ~02:3x CDT by the PS007/PS008 lane (Hermes/GLM,
skeleton author), on Jericho's explicit direction in-channel ("b. Re-pin
PS007 to spec semantics"). Cites:
REPAIR_PENDING_ps008_branch_convention_vs_ps007.md.

## Decision: OPTION (b) — SPEC branch semantics everywhere

Both executors adopt the RV32I-spec / pixel-CPU convention:

    taken-branch next pc = pc + imm // 4        (NO +1)

Rationale (Jericho's, concurred): PS010-PS012's trace-diff methodology
diffs against the pixel CPU/QEMU oracle — executors must agree with
the ORACLE, not with each other's idiosyncrasies. A permanently-armed
convention trap in PS009's composition is a worse standing risk than
one gated re-encode now, while the fixture is 7 words.

## CORRECTION TO THE TICKET (measured, before ruling)

The ticket's option-2 proposed word `0xFFFFFF10` is WRONG — it does
not decode as B-type at all (opcode 16, fmt '??' via decode_ref).
Independently re-derived encoding for `BNE x5, x0, -16`:

        0xFE0298E3   (decode_ref -> fmt=B, funct3=1, rs1=5, rs2=0, imm=-16)

Arithmetic check: branch at word 6 (byte 24); SPEC target word 2
(byte 8); imm = 8 - 24 = -16; -16//4 = -4; next pc = 6 + (-4) = 2 ✓.

## Verified end-to-end before issuing (this lane, on the current tree)

The 7-word program with word 6 = 0xFE0298E3, executed under the SPEC
convention in a standalone simulation driven by decode_ref:
42 executed instructions, x3 sequence 2,3,5,8,13,21,34,55, final
x1=34, x2=55, x3=55, x5=0 — the PS007 pin, EXACT and UNCHANGED. The
pin survives; only the word encoding and the executor line change.

## What the builder does on the next tick (un-HOLD, ordered)

1. `tools/pyshader_fde.py` `execute_one`: branch case becomes
   `pc + imm // 4` (drop the +1). Update the step-3 docstring/comment.
2. FIB word 6: `0xFE0298E3` (BNE x5,x0,-16). The docstring comment
   gains: "SPEC semantics (RULING_ps008_branch_convention): target =
   pc + imm//4 = 6-4 = 2."
3. `tests/test_pyshader_fde.py`: step-3 BNE polarity/bounds tests
   updated to SPEC arithmetic; FIB gate unchanged (42 steps, pin
   identical). RED first: run the FIB gate BEFORE the execute_one
   edit and paste the failure tail (it must FAIL under the old
   executor + new word, or the new word alone — either ordering is
   fine as long as both RED and GREEN tails are literal).
4. `tools/pyshader_ctl.py` (PS008): already SPEC — add one test
   asserting the two executors now agree on a shared branching
   program (the composition pre-gate PS009 needs).
5. Addendum this ruling to `RULING_ps007_fib_branch_offset.md` as a
   dated section (do not rewrite its text — audit trail stays).
6. Roadmap PS008 row: replace the "papered over" paragraph with a
   pointer to this ruling (resolved, not papered).

## Scope note

This is a skeleton-sign-off change per the contract; the builder
effects steps 1-6 exactly as written and NOTHING else. PS009 becomes
eligible only after both suites (fde + ctl) are green on the new
convention and the cross-executor agreement test exists.

/s/ skeleton author, on Jericho's direction
