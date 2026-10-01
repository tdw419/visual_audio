# REPAIR_PENDING_ps010c_blt_in_divergent_prog.md

**Filed:** 2026-09-20, orchestrator cron lane (Glyph OS Event Chain af3e62239ce2)
**Step:** PS010c, brief `.builder_queue/brief_ps010c_gpu_multihart.md`, row 3
**Status:** RULED 2026-09-20 ~18:2x —
`.builder_queue/RULING_ps010c_blt_in_divergent_prog.md` adopted
OPTION 1 (shader B-type extended to all six funct3, semantics verbatim
from the LOCKED `ref_ctl`). Blocker kept for audit trail.

## Symptom (measured, not reasoned — HEAD e7054570)

`DIVERGENT_PROG` (tools/pyshader_divergence.py:88-94) needs **BLT**
(funct3=4, pc 3, the spin loop; word `0xFE104EE3`, decode-verified) for
its not-taken population. The locked N-hart shader
(`_SHADER_HEADER`, tools/pyshader_multihart.py:76-79) implements
**BNE only** — `if (opcode == 99u)` guarded by `funct3 != 1u →
STOP_BAD_OPCODE`. Any hart that reaches the spin loop faults.

Host trace (LOCKED primitives, decode_ref/execute_one/execute_ctl,
/tmp/trace_divergent.py this run):

- taken (x5=4): `ctl pc0 BNE taken → pc3`, `ctl pc3 BLT not-taken → pc4`,
  EBREAK halt. Counted steps = **2** (matches the brief's pin).
- not-taken (x5=0): spins `pc2 → pc3 (BLT taken while x1>0)`, 18 counted
  steps, x1 drains to 0 (matches the brief's pin and PS010b's
  sampled_steps [2, 18]).

GPU run of the exact clause shape at HEAD e7054570 (literal):

```
steps: [1, 1, 1, 1, 3, 3, 3, 3]
rounds: 3
stops: [(0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3), (7, 3)]
AssertionError: PIN MUST FAIL (RED)
```

Every hart stops BAD_OPCODE(3); taken harts count 1 (the BNE) then fault
on the BLT; not-taken harts count 3 (addi, addi, first BLT) then fault.
The clause's pin [2,2,2,2,18,18,18,18] is unreachable under the lock set.
This also REDs the swapped-x5 discrimination leg planned for the receipt —
the fault fires before any assignment contrast can show.

PS010b never hit this because `sweep` drives the host CTL layer
(execute_ctl covers all six B-type funct3, tools/pyshader_ctl.py:16);
the GPU kernel is the first executor locked to the BNE-only subset that
this program's spin actually exercises.

## Options (cheapest-first)

1. **Extend the shader's B-type branch to all six funct3**, semantics
   verbatim from the LOCKED host primitive (tools/pyshader_ctl.py:140-160;
   BLT/BGE signed at :149, BLTU/BGEU unsigned at :153) — one WGSL branch
   inside `_SHADER_HEADER`, tools/pyshader_multihart.py (skeleton-sign-off:
   locked constant in the spec file). RECOMMENDED: keeps DIVERGENT_PROG
   and every downstream pin untouched — PS010b step-3/4 pins (steps
   [2,18], useful 80, slots 144, efficiency 0.5556 4dp, rounds 18) stay
   valid, and the GPU kernel's instruction subset becomes the same one
   PS008 already gated. Non-vacuity is already in hand: the BNE-only
   shader demonstrably faults on this exact program (evidence above).
2. **Re-spin DIVERGENT_PROG without BLT.** One-text edit in
   tools/pyshader_divergence.py, but the module's own comment (:86-87)
   records WHY the spin is BLT: a BNE-countdown wraps u32 past 0 and
   hangs (~2^32, probe-measured). A replacement needs a different loop
   construction, and EVERY derived pin moves: PS010b's locked
   step-3/4 pins above, the image pin in
   tests/test_pyshader_divergence.py:37, the brief's step-3/4 clause
   numbers (18, 80), and roadmap-referenced efficiency values. High
   downstream churn dressed as a small edit — more expensive than it looks.
3. **Narrow the step-3 clause to taken-path harts only.** REJECTED:
   the adversarial leg's whole purpose is the taken-vs-not-taken contrast
   (the not-taken spin IS the divergence); cutting it weakens a live
   guard to make a step pass — forbidden by the contract.

## Requested ruling

Adopt option 1 (or rule otherwise); until then PS010c steps 3-4 hold.
Mark this file RULED with a pointer when `RULING_ps010c_<topic>.md`
lands — never delete it.
