# RULING_ps010c_blt_in_divergent_prog

Issued: 2026-09-20 ~18:2x CDT, by the PS010c lane (Hermes/GLM, skeleton
author — the same lane that authored the skeleton at 99bd417b, per the
RULING_ps007_fib_branch_offset precedent that the skeleton-author lane
issues the sign-off after independent reproduction). Cites:
REPAIR_PENDING_ps010c_blt_in_divergent_prog.md.

## Decision: OPTION 1 — extend the shader's B-type branch to all six funct3

Semantics verbatim from the LOCKED host oracle `ref_ctl`
(tools/pyshader_ctl.py:127-156): BEQ eq, BNE ne, BLT/BGE signed,
BLTU/BGEU unsigned; funct3 2/3 still STOP_BAD_OPCODE. SPEC target
convention unchanged: `npc = (pc*4 + signed_imm)/4`
(RULING_ps008_branch_convention). One WGSL change inside
`_SHADER_HEADER` (tools/pyshader_multihart.py) plus the module
docstring's instruction-subset line. Nothing else moves.

## Independent verification performed before ruling (not taken on
## faith from the ticket)

- Code-level: the locked shader faults funct3 != 1
  (tools/pyshader_multihart.py:132-136) — confirmed by read at HEAD
  429b3b7a. `ref_ctl` covers all six funct3 (tools/pyshader_ctl.py:140-153)
  — the oracle the shader would now mirror.
- Decode-level (probe, this run): word 3 of DIVERGENT_PROG =
  0xFE104EE3 → fmt=B, funct3=4 (BLT), imm=-4 bytes — the ticket's
  decode claim CONFIRMED, not re-derived from memory.
- Host-level (probe, this run): host_reference(DIVERGENT_PROG, x5=4)
  → final pc=4, x1=0, x5=4; x5=0 → final pc=4, x1=0, x5=0. The
  [2, 18] step-count split matches the ticket's host trace and
  PS010b's sampled_steps; the step-3 gate will machine-check it.
- GPU-level (probe, this run, HEAD 429b3b7a): run_multihart_gpu
  N=8, x5=[4,4,4,4,0,0,0,0] → steps [1,1,1,1,3,3,3,3], rounds 3,
  stops = 8× (hart, 3) — the ticket's fault EXACTLY reproduced. The
  brief's pin [2,2,2,2,18,18,18,18] is measured unreachable under
  the BNE-only lock.

## Rationale

Option 1 keeps DIVERGENT_PROG and every downstream pin untouched
(PS010b steps-3/4 pins, the divergence-image pin, the brief's 18/80
clause numbers, roadmap efficiency values). Option 2's churn is real
and measured (the ticket's option-2 list); option 3 is refused as a
weakened guard. The GPU kernel's instruction subset becomes the same
one PS008 already gated against ref_ctl — no new semantics are being
invented, only mirrored.

Non-vacuity is already in hand: the BNE-only shader demonstrably
faults on this exact program (GPU probe above).

## Effectuation

The skeleton-author lane effectuates this as its own commit (the
e649cddf precedent: skeleton-side, not a builder signature change):
the shader branch block + docstring line only. Steps 1-2 gates
(exercise no branches) must stay green across the change. The step-3
builder run then lands `test_ps010c_adversarial_parity_n8` per the
brief, with the pre-ruling fault as its RED evidence.

## What this ruling does NOT authorize

- Any change to signatures, State shape, layout constants, or the
  pinned program texts (DIVERGENT_PROG's BLT stays exactly as-is).
- Any weakening of the funct3 2/3 STOP_BAD_OPCODE refusal.
- Treating this as precedent for builder-side edits to locked
  constants — the ruling authority is the skeleton-author lane (or
  Jericho), never the run that is blocked.
