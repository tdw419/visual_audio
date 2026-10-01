# RULING_ps009

Issued: 2026-09-20 03:46 CDT by the reporting lane (Qoder observer), on
Jericho's explicit direction in-channel ("Land it."), approving the
drafted text as written. Cites: PS009_BASELINE_RECEIPT.md (md5
6865bb54, incl. the ~03:10 verification addendum),
TICKET_SUPPLY_STATE_ADDENDUM340.md (lane's own request for this ruling
or a cadence change), GPU_CPU_EMULATOR_ROADMAP.md:67/:213-219.

## Decision: MEASURE-ONLY GO for PS009, split 009a/009b

1. **PS009a — GPU-resident single-hart FDE loop (correctness rung).**
   A generated-table-driven FDE loop executes on the GPU: shader
   internally iterates a decoded-instruction buffer, host re-dispatches
   on taken branches / halt. Gate: trace-diff of the FIB workload (and
   one >1k-insn straight-line program) vs the Python FDE AND the pixel
   CPU — 100% trace match. NO performance claim, NO fork arithmetic.
   This is the phase the roadmap text "the shader loops internally over
   a straight-line run" describes and must be BUILT (verified this
   lane: pyshader_wgsl is single-invocation 1x1x1, no instruction loop,
   _assert_ps001_shapes caps at 2 predecessors — nothing to
   parameterize).
2. **PS009b — batched-N measurement (the fork leg).** Batch N
   instructions per dispatch, straight-line runs between taken
   branches. Gate: FIB workload steps/s MEASURED with the landed
   probe's one_rep discipline, same-process pairing:
   (generated-batched) vs (Mode B hand-written 7,354-class reference)
   back-to-back in ONE process. Deficit = ModeB / generated. The
   [J-DECISION] fires ONLY if deficit >= 5x on that pairing.

## Fork-arithmetic clauses (all three fixes adopted)

- **PS007-as-context clause:** the "vs PS007" roadmap leg (:217) is
  REPORTED CONTEXT, never a deficit denominator. PS007 recorded no
  rate; this lane measured host run_fde at ~840-890k steps/s
  (pin-adjudicated), ~121x the batched shader — against the roadmap's
  own honest boundary (host interpretation beats GPU; non-goal section
  concedes it). A "deficit vs PS007" ratio would manufacture a 100x
  failure — the 600-800k failure class again. Fork denominator is
  SPATIAL_RV32I Mode B ONLY.
- **Same-process pairing:** session-bound absolutes excluded from
  fork arithmetic (md5 6865bb54 rule). No stored ratio, no stored
  threshold; the 1,471 figure and the reporting lane's 206/7,405 band
  are context only.
- **RED-first seam proof:** before any measurement, the builder
  proves the batching seam design RED-first: EITHER the generated
  emitter gains a data-driven instruction-index loop that
  _assert_ps001_shapes explicitly whitelists (a named new shape, not
  a loosening), OR the batch loop lives in hand-written WGSL wrapping
  the generated decode table. The choice changes what "harvest" means
  at the fork, so it is PROVEN (compiles + runs 1 batch) before
  PS009b's numbers exist. Never weaken the 2-predecessor guard — add
  a named shape or wrap outside.

## Unchanged

- [J-DECISION] remains Jericho's on PS009b's receipt; continue/harvest
  per roadmap :67, judged on the paired ratio.
- SE021 holds unaffected.
- The loop's 2-minute cadence stands (the HOLD cost is accepted).

## Builder proceeds (effect this order, nothing else)

009a build + trace-diff gates, then 009b build + paired measurement,
receipt with both tails, fork data to Jericho. The [J-DECISION] is NOT
this ruling's to make and the builder does not self-promote past it.

/s/ reporting lane, on Jericho's direction ("Land it.", 2026-09-20)
next: PS009a seam proof RED -> 009a trace-diff receipt -> PS009b paired
measurement -> J-DECISION package to Jericho
