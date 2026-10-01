# RULING_ps012 — option (c): stop at RV32. Record and close.

Issued: 2026-09-20 ~22:10 CDT by the reporting lane (Qoder observer), on
Jericho's in-channel decision ("RULING_ps012: (c) — stop at RV32, record and
close. Land RULING_ps012 with option (c)"). Cites:
GPU_CPU_EMULATOR_ROADMAP.md:338-346 (the three exits), RULING_ps009.md,
RULING_ps009_fork_cleared_ps010_go.md (060a03e8), PS009_BASELINE_RECEIPT.md,
PS009B_PAIRED_RECEIPT.md + its superseding re-verification (4c7d30f5
context), brief_ps010c_gpu_multihart.md, brief_ps010d_divergence_measurement.md,
brief_ps011_golden_trace.md.

## Decision

**PS012 = exit (c). The thesis is proven at RV32 scale. This roadmap closes;
record the evidence and stop.** No new PS-series phase is to be picked up,
promoted, or invented. (a) RV64 extension and (b) harvest into
`SPATIAL_RV64I.wgsl` are both **rejected as continuations of this roadmap** —
see "Why" below. PS013 remains barred and is now moot for this lane.

Jericho's reasoning, recorded as written:
- The thesis this roadmap set out to prove — instruction semantics generated
  once in Python, verified three ways, beating the semantics-in-WGSL drift bug
  class — is **proven at RV32 scale**, with PS009's correctness data and
  PS010/PS011's divergence and cross-validation data in hand.
- **(a) RV64** is real additional engineering with **no new architectural
  question** in it: W-suffix pitfalls and wider registers are more of the same
  discipline already validated, not a new risk worth the budget.
- **(b) harvest** is the more interesting option in principle — given that
  shader's real defect history — but it is a **separate, substantial
  engineering project in its own right** (porting generated tables into a
  3,432-line hand-tuned shader without breaking its performance property), not
  a natural continuation of this roadmap's remaining budget. The roadmap's own
  non-goals section already commits to not replacing that shader wholesale.
- Therefore: if a harvest project is wanted later, **it gets its own roadmap
  with its own gates** — it must not ride this one's momentum.

## Evidence the closure record must carry (re-verified by this lane)

| rung | result |
|---|---|
| PS009a | generated GPU-resident FDE loop, trace-match vs Python FDE and pixel CPU |
| PS009b | paired deficit ModeB/GEN **0.45x** — generated batching is ~2.2x *faster* than the hand-written batched core (the originally filed 6.15x measured call overhead; both host legs sat 9–14x under the device's own blocking-readback floor) |
| PS010a-d | two-hart mailbox completes; merge discipline adjudicated; sync recipe proven load-bearing; GPU multi-hart **bit-for-bit parity at all 15 cells** |
| PS010d | divergence-cost curve on a metric that moves: **1.780 (N=2) / 2.498 (N=64) / 1.760 (N=4096) / 1.715 (N=65536)**, floors attached, same-process pairing, non-vacuity mutant rejected |
| PS011 | golden-trace gate: 1252 transitions, `x1=31375 / x2=0`, **`spec_verdicts=[]`**; engine-vs-engine diff recorded, never used to adjudicate |

## Clause 1 — the PS010d verdict field must be fixed BEFORE closure wording settles

The curve's verdict is currently derived by an **endpoint rule**:
`tools/pyshader_measure.py:278-286` reads `ratios[-1]` and compares it to 2.0
(plus one low-N case). That throws away exactly the information the roadmap
asked the curve to carry: a single tail point cannot distinguish whether the
**N=64 peak of 2.498x** is a real warp-fill hazard at agent-relevant scales
below 65536 or an artifact, and it would read the same "tolerable" for a curve
that spikes 10x mid-range and settles.

Required, as a normal sized step of its own (RED first, guard replaced not
deleted, receipts updated by dated correction rather than silent edit):

1. Derive the verdict from the **whole curve**: max-over-N and **where** it
   occurs, the peak-to-tail relation, and the spread across the swept N — not
   the tail alone.
2. Keep the three roadmap :270-279 outcomes as the vocabulary, but make
   "tolerable" a **description of curve shape** (peaks then decays, never
   catastrophic at any measured N), not a boolean read off one number.
3. Non-vacuity: a forged curve carrying a large mid-range spike must **not**
   return the same verdict as a flat one. Name the forged cell in the failure,
   per this lane's existing pin discipline.
4. Until that lands, the closure record describes the divergence result as
   "1.7–2.5x across four orders of magnitude in N, peaking at N=64 and decaying
   toward ~1.72x at 65536" — **not** as "tolerable".

This is a methodology correction on a landed rung, not a reopening: the
numbers stand, only the reading rule changes.

For the record, and because it is the reason this fork is not being called on
bad data: 1.7–2.5x across four orders of magnitude is a genuinely good result
and a world away from the false 6.15x that would have fired a fork on a
measurement artifact.

## Clause 2 — what "record and close" means concretely

1. `GPU_CPU_EMULATOR_ROADMAP.md`: PS005–PS011 status lines closed with their
   receipt pointers; PS012 marked **RESOLVED = (c)** with this ruling cited;
   PS013 left as a stub and explicitly marked out of scope for this roadmap
   (not deleted — it is the pointer to the next one).
2. A short closure section at the top or foot of the roadmap: the thesis, the
   five rows of evidence above, and the two rejected exits with the reason for
   each, so a future reader cannot mistake (a) or (b) for deferred work on this
   roadmap. Keep the existing honest-boundary section intact — it is what made
   this closure legible.
3. Per protocol rule 4 (judgment escape hatch): with zero open rows the correct
   terminal condition for this lane is **stop and say so**. Do not self-refill
   from `GLYPH_BACKLOG.md` into a PS014, and do not promote a replacement
   roadmap. The glyph-transpiler lane goes idle-on-record until Jericho opens a
   new one.

## Housekeeping — recorded, not blocking, not PS-series

Surfaced so it does not get lost; none of it gates closure and none of it
should stall it:

- `/tmp` holds ~5.4G of orphaned per-lane scratch (`rung9_scratch` 2.1G,
  `go6_l2` 1.7G, `bm000_reverify_today` 717M, `r4head` 386M, `wt_pillar3`
  298M, `d22q` 204M) against a root filesystem at 90% and `/home` at 98%. This
  repo has a recorded history of disk-full causing real corruption; the cleanup
  pass belongs to whichever lane touches tooling next, across all three lanes,
  and needs the owner of each directory confirmed before anything is removed.
- Two harness suites are red by their own timing budgets, not by logic:
  `tests/test_harness_failname.py` (4F/1P) and `tests/test_suite_iso_harness.py`
  (6F/11P) fail in isolation because a child pytest cold-started from the repo
  cwd costs **18.8s** against per-file budgets in the low seconds (same file
  from /tmp: 1.77s). Harness code and both test files unchanged since
  `fb6558ce` (2026-09-14). No lane gates on them, so nothing surfaces them.
- Shared-tree operating convention, already self-caught and written up by the
  PS010d run: **never bare `git stash` in this tree** (three lanes commit into
  one working directory; a stash for a RED re-run swept sibling churn and the
  pop aborted). Use `git show HEAD:<file>` + restore. Recorded here so it stops
  being one lane's lesson.

## Not changed by this ruling

- Reserved decisions stay reserved: this ruling does not open PS013, does not
  authorize the harvest project, and does not re-state any [J-DECISION] other
  than PS012's.
- The PS010b step-4 correction (4c7d30f5) stands; clause 1 supersedes only the
  reading rule on PS010d's side.
- Cadence untouched. The lane may keep its HOLD ticks while clause 1-2 work
  lands; it is not to hunt for new work in the meantime.

/s/ reporting lane, on Jericho's decision ("RULING_ps012: (c)", 2026-09-20)
next: clause 1 (curve-shaped verdict, RED first) -> clause 2 (closure record)
      -> stop and say so
