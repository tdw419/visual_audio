# REPAIR_PENDING_ps008_branch_convention_vs_ps007

Filed by: orchestrator cron af3e62239ce2, 2026-09-19, during PS008
(PS008 landed GREEN on the PS008-specific gates — this is a separate
skeleton-sign-off class observation, filed per the skeleton-handoff-
contract rule 3; the PS007 spec file was NOT edited.)

## The conflict

`tools/pyshader_fde.py` `execute_one` (PS007, landed) computes taken-
branch next-pc as:

    pc_next = pc + 1 + imm // 4          (insn units, +1 before offset)

RV32I spec (and `tools/SPATIAL_RV32I.wgsl` line ~957, the pixel CPU):
target BYTE address = branch's own byte pc + imm, i.e. in insn units:

    pc_next = pc + imm // 4              (no +1)

The PS007 pinned Fibonacci program (word 6 = `BNE x5,x0,-20`, RULING_
ps007_fib_branch_offset) is CONSISTENT with the +1 convention: its
hand-computed pin targets word 2 and 42 steps to the pinned final
state, so `tests/test_pyshader_fde.py` is GREEN under the +1
convention. Under SPEC semantics the same word would target word 1
and the pin would fail. Both engines are self-consistent; they
disagree about what an encoded offset MEANS.

`tools/pyshader_ctl.py` (PS008) implements SPEC semantics (pc + imm//4;
byte-granular link values), pinned against the pixel CPU via the
PS008 cross-validation leg. The two modules therefore interpret the
SAME instruction word differently. Any future consumer that mixes
them (e.g. PS009 batching over PS007's executor) inherits the
disagreement silently.

## Why I did not unilaterally "fix" PS007

PS007 is a closed row with a landed done-closure, a RULING artifact,
and 78 passing tests keyed to its pin. Changing its branch convention
changes the meaning of the pinned FIB program (word 6 would need
re-encoding to -24) — that is a skeleton-sign-off decision, not a
builder patch.

## Options (cheapest first)

1. **Document-only** (zero code): add a note to PS008/PS009 roadmap
   rows that `execute_one` (PS007) uses insn-granular "+1" branch
   offsets while `execute_ctl` (PS008) uses SPEC offsets; forbid
   mixing executors in one program image. Cheapest, but the trap
   stays armed.
2. **Re-pin PS007** (small): re-encode FIB word 6 to -24 (SPEC
   target word 2: byte 24 - 24 = 0... verify: branch at word 6, byte
   24, target word 2 = byte 8, imm = 8 - 24 = -16 → word 0xFFFFFF10),
   update FIB_EXPECTED_STEPS (unchanged: 42) and the RULING addendum,
   change `execute_one` to `pc + imm // 4`. Gate re-runs prove it.
3. **Keep both, name them** (medium): extract the branch-target
   function into one place with a `convention=` parameter; both
   modules call it explicitly. No behavior change, makes the fork
   visible in code.

Recommendation: option 2 — SPEC semantics is what the pixel CPU
implements, and the whole roadmap's oracle is the pixel CPU/QEMU;
diverging from it gets more expensive the later it is caught.
However PS007's landing used the +1 convention consistently, so this
is Jericho's call.

Status: RULED 2026-09-20 → .builder_queue/RULING_ps008_branch_convention.md
(option b, Jericho; effectuated in e649cddf — see the RULED section below
and the PS008 done-closure in GPU_CPU_EMULATOR_ROADMAP.md).

---

## RULED 2026-09-20 — see .builder_queue/RULING_ps008_branch_convention.md

Option (b) per Jericho (in-channel): SPEC semantics pc + imm//4 for
BOTH executors; FIB word 6 re-encoded to 0xFE0298E3 (the ticket's
proposed 0xFFFFFF10 was wrong — decode-verified not B-type). Effected
on the tree this date: execute_one +1 dropped, tests re-pinned to SPEC
arithmetic, cross-executor agreement test landed (tests/
test_pyshader_ctl.py::test_ps008_cross_executor_branch_agreement),
fde+ctl 30/30 green. PS009 eligibility condition satisfied.
