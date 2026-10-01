# RECEIPT — R2.2 Toolchain UX: one command compiles + runs (2026-09-21, builder af3e62239ce2)

## Rung

PRODUCT_ROADMAP.md R2.2: "Toolchain UX: one command compiles a program to a
glyph/tile artifact and runs it. Target: someone who has never read this
repo."

## Deliverable

`tools/glyph_run.py` — single entry point over the LANDED stack
(bake_image → GlyphRunner → GlyphCPUv2, the same engines the frozen R2.1
box-ABI stack runs on). No new engine code; zero production lines changed in
baker/runner/isa (composition layer only).

    python3 tools/glyph_run.py program.glyph      # compile + run
    python3 tools/glyph_run.py program.glyph.png  # run artifact alone

Exit-code contract: 0 clean HALT · 1 fault · 2 assemble failure ·
3 budget exhausted · 4 I/O. `--json` for machine-readable receipt.
Worked example: `examples/sum_1_to_5.glyph` (sums 1..5, PRTs 15).

## Gate

`tests/test_glyph_run.py` — 8 legs (5 GREEN, 3 RED). Force-added past
.gitignore's test_*.py rule.

GREEN tails (landing run):
```
........                                                                 [100%]
8 passed in 1.42s
```
Lane regression (conformance + fleet + arrive + queue + resident + shell):
```
.............................................                            [100%]
45 passed in 3.49s
```

RED-first record (policy rule 4):
1. Pre-green failure the gate itself caught: `test_json_receipt` FAILED
   (json.decoder.JSONDecodeError: Expecting value: line 1 column 1) — the
   engine's PRT prints `OUTPUT: r5 = 15` straight to stdout, polluting
   `--json`. Fix: capture engine stdout during execution (receipt reports
   via cpu.output). Re-run: 7 passed.
2. Landing-time RED probe: corrupting the artifact's FIRST instruction
   pixel (0,0) with unknown-opcode color (1,1,1) → artifact-only run
   produces NO `output   : 15` (exit 0, silent early halt) — proves the
   artifact-only path executes THIS artifact's pixels, not a rebuilt
   program. This leg now lives permanently in the suite as
   `test_red_corrupted_artifact_produces_no_result`.
3. Probe-design note: the first RED draft corrupted the HALT pixel instead
   and FAILED TO DISCRIMINATE (unknown-opcode halt is by-design per ENG-1;
   output 15 had already been produced). Caught by the probe's own
   assertion before any verdict was drawn; rewritten to target
   instruction 0. Recorded because a RED leg that cannot fail is the
   failure mode this lane exists to prevent.

Stranger-flow end-to-end (live, at HEAD):
```
$ python3 tools/glyph_run.py examples/sum_1_to_5.glyph -o /tmp/r22_demo.glyph.png
artifact : /tmp/r22_demo.glyph.png
result   : HALT
steps    : 37
output   : 15
$ python3 tools/glyph_run.py /tmp/r22_demo.glyph.png
artifact : /tmp/r22_demo.glyph.png
result   : HALT
steps    : 37
output   : 15
```

## What this PASS does NOT prove

- WGSL shader-path parity: CPU oracle only (runner.run_wgsl untouched) —
  the WGSL twin divergence remains the lane's largest open defect.
- Box-ABI supervisor behavior: this is the plain single-box path; the
  frozen ABI (docs/BOX_ABI_v2.md) is not exercised here beyond sharing
  its engines.
- No rate/floor claims: nothing here quotes a rate → floors line N/A,
  check_regime N/A with that reason (no measurement flip risk).
- The `.glyph` dialect docs are the example + gate file; a stranger can
  run but the full ISA reference is still scattered (R5.2 problem).
- Fault exit-code leg: leg 5 exercises the budget path (exit 3), not a
  genuine E-K1 fault (exit 1) — the fault path is covered by the R2.1
  conformance suite, not re-covered here.

## Scope

Changed: tools/glyph_run.py (new), tests/test_glyph_run.py (new),
examples/sum_1_to_5.glyph (new), this receipt, PRODUCT_LANE_STATE.md.
NOT touched: baker.py, runner.py, glyph_isa_v2.py, agent_resident.py,
protected assets. Tracked-dirty noise from parallel sessions
(.hermes_guest_context/guest_state.json, frame_00230.png) left unstaged.
