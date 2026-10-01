# RESEARCH — DEFECT-31k: the GH-23 ECALL rewrite is adjacency-keyed on a lowered `LDI r17`; non-adjacent shapes leave a SILENT bare HALT mid-program

Builder: af3e62239ce2 · Date: 2026-09-26 ~01:4x CDT · HEAD at probe time: eb4dc784
Class: transpiler/loader contract gap (NEW op-class: the syscall lowering boundary — the family the BK-34 ledger entry named as the next unprobed class)
Rule 5: no existing RESEARCH_*.md or backlog row covers ecall lowering/loader interaction (the day-1 research docs cover user-surface verbs, not this).

## Question

The transpiler lowers `ecall` (0x73, funct12=0 → OP_ECALL) to a bare `HALT`
(tools/rv64i_to_glyph.py:1438-1440). The GH-23 loader then rewrites `HALT`
→ `SYSCALL r10` ONLY when the immediately-preceding emitted line starts
`LDI r17 ` (tests/test_gh23_libc_runtime.py:435-437), and a landing gate
ASSERTS that adjacency for its fixture (tests/test_gh23_libc_runtime.py:795-804).

Does the rewrite contract hold for ecall shapes OTHER than the fixture's
`li a7,N; ecall` — and what does the machine do when it does not?

## Method

Probe `.builder_queue/dbg_d31k_ecall_rewrite_af3e.py` (reuses the proven
d31f harness module for gcc-compile/by_pc/tree-vs-HEAD; custom main with
per-leg dual readouts). Program loaded through the REAL loader
`_load_posix_program` (the code under test), baked via
`libc_runtime_kernel_image`, run on GlyphRunner (16384 words).

Observables per leg:
- STATIC: count of `SYSCALL r10` in the loaded program (did the rewrite fire?)
- DYNAMIC: word 718 (GH-23 legacy stdout window mirror — written only if the
  write tile ran) and word 902 (post-ecall continuation marker store —
  reachable only if execution resumed after the ecall site).

Legs (deterministic; run 3x, identical output; tree==HEAD op-streams
byte-identical per pc in all 3):
- C01 control: `li a7,64; ecall` adjacent — the fixture shape.
- L02: one intervening op (`li x10,0`) between the a7 load and the ecall.
- L03: runtime syscall number — `mv a7,x5` (dispatch-wrapper shape).

Probe-defect disclosed (fixed before evidence taken): run-1 used word 901 as
the continuation marker — but word 901 (byte 0xE14) is the target of the
PRE-ecall store `sw x10,4(x18)`, so C01 "failed" on its own store. Corrected
to word 902 (byte 0xE18, the post-ecall store target); C01 then PASSes. The
first run's output was an artifact of the probe, not of the substrate.

## Findings (measured, HEAD eb4dc784)

| leg | rewrite fired | window[718] | marker[902] | verdict |
|---|---|---|---|---|
| C01 adjacent li | 1 | 0x1234 | 0x1234 | PASS — contract holds for the fixture shape |
| L02 intervening op | 0 | 0x0 | 0x0 | RED — SILENT mid-program halt |
| L03 runtime sysnum | 0 | 0x0 | 0x0 | RED — SILENT mid-program halt |

All REDs: halted=True, faulted=False — indistinguishable from a clean halt
(glyph_isa_v2.py:1320-1322; halt_reason=None per :616).

Static confirmation (listing read, separate verification pass):
- C01 raw-transpile HALT predecessor: `LDI r17 0x40` → rewrite fires.
- L02 HALT predecessor: `LDI r10 0x0` → adjacency broken, rewrite misses.
- L03 HALT predecessor: `ADD r17 r5` (mv lowers to `LDI r17 0; ADD r17 r5`)
  → adjacency broken EVEN THOUGH the LDI r17 is one op earlier.

Mechanism: the loader's rewrite is textual and adjacency-keyed; the
transpiler's ecall→HALT lowering loses the syscall intent entirely, so
correctness depends on a compilation accident (what gcc emits immediately
before the ecall). L02/L03 are ordinary optimized-code shapes: instruction
scheduling between the a7 load and the trap, and any syscall number not
known at compile time (dispatch tables, wrapper functions). Real code using
them stops silently at the first ecall.

Scope honesty:
- Latent-only at HEAD: every landed fixture uses the adjacent-li thunk shape
  (GH-23's SHIM_S, tests/test_gh23_libc_runtime.py:333-350), the landed
  adjacency assert (:795-804) passes, and no landed gate regresses.
- ebreak (→ `SYSCALL r10` unconditional, :1446-1447) is a DIFFERENT path and
  was NOT probed this tick; neither was the KSYS_PC-armed (E-K2 trap) leg —
  the probe exercises the un-armed in-process dispatcher path only.
- No WGSL twin leg (transpiler/loader-side, nothing spatial).
- No fix attempted (research never lands engine code, rule 5).

## Candidate (backlog format)

BK-35 — Loader/transpiler: make the ECALL→SYSCALL rewrite structural, not
adjacency-keyed. Fix shape (cheapest first): (a) move the rewrite INTO the
transpiler at the OP_ECALL arm (emit `SYSCALL r10` directly for ecall when a
module-level flag is set — the loader keeps its post-pass only as a safety
net); or (b) widen the loader match from "prev line is LDI r17" to
"dataflow scan: r17 is written on every path since the previous
branch/call boundary" (more general, more code); or (c) loud-fail: loader
emits a distinguishable HALT marker for unrewritten ecalls so a miss traps
loudly instead of silently. Gate: `tests/test_defect31k_ecall_rewrite.py` —
L02/L03 probe programs as fixtures (RED-first: bare HALT reached), C01
control, non-vacuity leg (neuter the new rewrite → L02/L03 RED). Prereq: none
new. Worktree isolation (engine-core transpiler) per AGENTS.md if (a).

SPEC: tools/rv64i_to_glyph.py:1438-1440, tests/test_gh23_libc_runtime.py:435,795-804,
tools/glyph_isa_v2.py:1121-1154,1320-1322 read 2026-09-26; implementation
ours from contract (no external spec adopted — citation gate N/A).

## Rule-6 honesty

All numbers are structural asserts (memory words, halted/faulted booleans,
static instruction counts) from real GlyphRunner runs this tick. No rates,
no latencies — rule-1 floors does not attach. Determinism: 3 runs identical
(gate tails saved: output/d31k_gate_run1.txt, output/d31k_gate_run2.txt).
NOT verified: no live xv6-nano or libc-fixture repro at HEAD (latent-only);
no WGSL twin; ebreak path unprobed; KSYS_PC-armed trap path unprobed.
