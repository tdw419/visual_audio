# SE024 Receipt — JNZ/JNE alias opcodes (2026-09-16, builder cron af3e62239ce2)

Ticket: `.builder_queue/SE024_TICKET.md` (promoted by Jericho in-channel:
"yes — build it and promote it"). Spec: `GLYPH_ISA_ROADMAP.md` §1.1.

## Summary

JNZ (jump-if-not-zero) and JNE (alias) landed as NEW opcodes in
`tools/glyph_isa_v2.py` (OpcodeMapV2 + assembler jump-arg handling +
GlyphCPUv2 dispatch), byte-exact twins in
`glyph_dispatch/src/glyph/glyph_isa_v2.py` (md5 `29b6adf3…`), and the WGSL
twin `tools/wgsl_glyph_isa_v2.py` / both dispatch copies (md5 `f7443477…`):
`_OPCODE_ORDER` += JNZ/JNE, shared `r0 == 0u` dispatch branch. JZ untouched
(color, encoding, semantics). Pinned colors: JNZ sienna (172,100,52), JNE
orangered (243,49,5) — asserted distinct from all 31 existing opcodes.

SEMANTICS: JZ jumps when CMP flag r0 is SET; JNZ/JNE jump when r0 is CLEAR
(exact boolean complement). Both polarities gated.

## Gate evidence (the 5-gate plan from the ticket)

**GATE 1 — RED at pre-patch HEAD `971261f`** (sparse worktree
/tmp/se024_red_wt, pre-change engine, JNZ count in engine = 0):
`output/se024_gate_run1_red.txt` — **8 failed / 4 passed** in 0.26 s,
failing for the right reason: `KeyError: 'JNZ'` / `KeyError: 'JNE'` from
`opcode_to_rgb` (opcode absent from map — assembler cannot assemble them).
The 4 passes are the JZ-unchanged regression guards, green on both sides
by design.

**GATE 2 — GREEN after** (working tree, py3.12):
`tests/test_se024_jnz_jne.py` **12 passed** in 0.14 s:
- L1/L2: JNZ/JNE in OpcodeMapV2, unique unreserved colors.
- L3–L6: both polarities of both opcodes (jump on r0==0, fall through on
  r0!=0).
- L7–L9: JZ semantics + color unchanged (GREEN both sides).
- L10: SE023 assemble-time jump-bounds check covers JNZ/JNE.
- L11: :label resolution forward AND backward.

One test-side fix during bring-up: `_run()` passed a raw string to
`assemble()` (signature: `List[str]`); iterating a str yields characters,
so the assembler died on `KeyError: 'L'` — an orchestrator-debug, not an
engine bug (`output/se024_dbg.py`). Fixed with `splitlines()` in the test
helper only.

**GATE 3 — blast radius** (all runs by me, on the working tree):
- SEED=202609161 `bash tools/arc_lega.sh`: **rc=0, crashes=0, 323 passed /
  1 skipped / 9 deselected** in 70.47 s, oom_kill_delta=0
  (`output/se024_arc_regression.txt`, sidecar
  `output/arc_lega_seed202609161_971261f.json`). First attempt used seed
  `20260916a` — non-integer seed rejected by pytest-randomly (rc=4); rerun
  with an integer seed. No test failures either run.
- Glyph+Transpiler differential (exactly the set the pre-commit hook
  globs): **38 passed** in 44.79 s.
- Coverage lint `tests/test_glyph_engine_coverage_lint.py`: **7 passed**
  (a table opcode missing from the WGSL `_OPCODE_ORDER` would be a
  finding).
- Twin sync: pre-commit `cmp` guard satisfied — md5 identical
  (tools/ vs glyph_dispatch/src/glyph/, both files).

**GATE 4 — non-vacuity** (`output/se024_nonvacuity_probe.py` →
`output/se024_nonvacuity_result.txt`): the parity program's JNZ decision
is load-bearing (jump → r10=0xAA; fall-through → r10=0x1). Measured:
unpatched Python r10=0xaa; a JZ-in-JNZ-slot program (what a confused
implementation produces) yields r10=0x1; WGSL twin r10=0xaa. The parity
assert therefore fires on any JNZ→JZ semantic inversion. DISCRIMINATING:
True.

**GATE 5 — WGSL twin leg** (`tests/test_se024_wgsl_parity.py`, **4
passed** in 0.98 s, live wgpu/mesa i915 backend — GPU stack, same
receipts path as BK-2): same program, same observable output (r10) on
both engines, for JNZ and JNE; plus table-membership and
generated-shader-contains-OPCODE_JNZ legs.

## Scope honesty (what this PASS does NOT prove)

- The WGSL leg ran on the mesa/i915 software path (skylake derivative,
  `VK_EXT_physical_device_drm` absent) — not the RTX 5090. The parity
  contract is engine-independent, but a vendor-driver run was not
  performed this session.
- `tests/test_se024_wgsl_parity.py` and the fixed test helper are
  untracked new files (`.gitignore` test_*.py rule) — force-added.
- JNE-as-alias redundancy is deliberate (reads naturally after CMP); no
  separate encoding.
- `tools/SPATIAL_RV32I.wgsl` + `tools/spatial_rv32i_cpu.py` carry
  UNRELATED in-flight virtio/vq_idx work from a parallel session — NOT
  part of SE024, excluded from this commit.
