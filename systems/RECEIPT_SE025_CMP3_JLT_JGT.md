# SE025 Receipt — CMP tri-state + JLT/JGT opcodes (2026-09-22, builder cron af3e62239ce2)

Ticket: GLYPH_ISA_ROADMAP.md §1.3 (J-DECISION: "file as SE025"), claimed via
PRODUCT_LANE_STATE.md CLAIM QUEUE item 3 (items 1–2 closed at HEAD 30da7716).
Additive discipline per §1.1/SE024 (systems/RECEIPT_SE024_JNZ_JNE.md).

## Summary

Three NEW opcodes landed in `tools/glyph_isa_v2.py` (OpcodeMapV2 + assembler
arg handling + GlyphCPUv2 dispatch), byte-exact twins in
`glyph_dispatch/src/glyph/glyph_isa_v2.py` (md5 `31d6828a…`) and the WGSL
twin `tools/wgsl_glyph_isa_v2.py` + both dispatch copies (md5 `8d8ef293…`):

- **CMP3 rd, rs2** — tri-state compare: `r0 = 0 (rd < rs2, SIGNED) / 1
  (equal) / 2 (rd > rs2)`. 32-bit wrap first (matches SHL/SHR), then
  two's-complement signed view — blt-faithful.
- **JLT target** — jump when `r0 == 0`.
- **JGT target** — jump when `r0 == 2` (equal falls through).

**CMP, JZ, JNZ, JNE are UNTOUCHED** (encoding, colors, semantics). JZ keeps
legacy meaning forever (roadmap Pillar-1 exit criteria). A legacy CMP after
CMP3 restores pure-boolean r0, so no existing program can observe a
difference unless it opts in via CMP3.

Pinned colors (FIXED_COLORS, twin parity): CMP3 dark slate gray (47,79,79),
JLT peru (205,133,63), JGT yellowgreen (154,205,50) — asserted distinct from
all existing opcodes (gate leg 4).

Assembler integration: CMP3 added to the 2-register-arg arm; JLT/JGT added to
the jump-target arms (bounds check SE023 + coord packing); CMP3 explicitly
invalidates r0's known-const status (it writes the flag register; args[0] is
the compared register, so the generic pop would miss it — tools/glyph_isa_v2.py:465).

WGSL twin: `_OPCODE_ORDER` += CMP3/JLT/JGT (auto-generated consts + color
checks); dispatch branches are bit-exact counterparts of the Python ones
(i32 conversion is two's-complement, matching the Python signed view).

## Gate evidence

**RED at pre-change HEAD `30da7716`** (working tree, engine unpatched):
`output/se025_gate_red_30da7716.txt` — **17 failed / 3 passed** in 0.33 s,
failing for the right reason: `KeyError: 'CMP3'` (×10) / `'JLT'` (×2) /
`'JGT'` (×1) from `opcode_to_rgb` (opcode absent from map). The 3 passes are
the green-both-sides regression guards (legacy CMP boolean ×3, WGSL-skip
importorskip order) plus label-program legs whose failure mode was
ValueError, recorded in the run1 log.

**GREEN after**: `tests/test_se025_cmp_tristate.py` **20 passed** in 0.74 s
(`output/se025_gate_green_run2.txt`):
- L1–L4: CMP3/JLT/JGT in OpcodeMapV2, unique unreserved colors, no collision
  with any existing opcode.
- L5–L7: CMP3 equal→1, signed less (0xFFFFFFFF vs 1)→0, greater→2.
- L8–L9: JLT and JGT both polarities (jump + fall-through).
- L10–L13: green-both-sides guards — legacy CMP still boolean, JZ/JNZ
  semantics untouched, JZ color distinct from the new three, SE023 bounds
  check covers JLT.
- L14: :label resolution forward and backward for JLT/JGT.
- L15: non-vacuity loop (count 5→1 via JGT, sum 15).
- L16–L17: WGSL `_OPCODE_ORDER` membership + generated-shader dispatch
  branches present.
- L18–L20: live GPU parity (wgpu), lt/gt/eq_fallthrough — same program,
  same r10 on both engines.

Test-side fixes during bring-up (both mine, both orchestrator-debug class,
not engine bugs): (1) jump targets written `0,6` instead of `col,row`
(`6,0`) — coord convention is index = y·cols + x; (2) labels written
`name:` instead of the assembler's `:name`-on-own-line form. Both were
ValueErrors at assemble time, caught immediately.

**Non-vacuity probe** (`output/se025_nonvacuity_probe.py` →
`output/se025_nonvacuity_result.txt`): the JLT decision is load-bearing
(jump → r10=0xAA; any of {JZ-in-JLT-slot, unsigned compare, inverted
encoding} → r10=1). DISCRIMINATING: True. The count-down loop lands 15; a
polarity slip yields 0 or divergence.

**Blast radius** (all runs by me, working tree at HEAD 30da7716):
- SE024 gate re-run on patched engine: r52/r51/r43/conformance/glyph_run/
  fleet-family subset — 43 passed (`tests/test_se025+se024+parity+fault*`).
- Pre-commit differential globs (exactly what the hook runs):
  `tests/test_rv64i_to_glyph*.py` + `tests/test_glyph_isa_v2.py` — **38
  passed** in 33.75 s.
- Coverage lint `tests/test_glyph_engine_coverage_lint.py`: **7 passed**
  (a table opcode missing from the WGSL `_OPCODE_ORDER` would be a finding).
- Triple-sync gate `tests/test_wgsl_triple_sync.py`: **2 passed**.
- Twin md5 sync verified: tools/ vs glyph_dispatch copies byte-identical
  (both files), satisfying the pre-commit `cmp` guard.
- Arc regression: SEED=202609221 `bash tools/arc_lega.sh` — result recorded
  below in the LEDGER-UPDATE section of the commit message (run in
  background; tail saved to output/se025_arc_regression.txt).

## Scope honesty (what this PASS does NOT prove)

- The WGSL parity legs ran on the local wgpu backend (mesa/software path),
  not the RTX 5090 — same caveat as SE024's twin leg; vendor-driver run not
  performed.
- The arc regression exercises the engine against the standing arc corpus;
  it does not exercise CMP3/JLT/JGT through the transpiler (the transpiler
  does not yet EMIT CMP3 — that is a future rung; the roadmap's exit
  criterion is that it CAN emit jump-only-on-condition idiomatically, which
  now has the opcodes available).
- No rate/floors claims made → floors/check_regime N/A.
- r0 semantics under CMP3 in SYSCALL-marshalled contexts (a7=r17 etc.) were
  not specifically probed; CMP3 only writes r0, same as CMP, so exposure is
  identical to the existing CMP surface.
