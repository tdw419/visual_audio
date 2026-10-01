# RECEIPT — R2.1 Box ABI freeze (docs/BOX_ABI_v2.md + conformance suite)

**Date:** 2026-09-21, builder cron af3e62239ce2 · base HEAD 68b11265 (R1.3 PASS)
**Rung:** PRODUCT_ROADMAP.md R2.1 — "Freeze the box ABI: syscalls, register
layout, memory map, mailbox protocol — versioned, with a conformance suite
(GREEN + RED legs)."

## Deliverables
- `docs/BOX_ABI_v2.md` — the FROZEN spec: version word 0x00020026 @952,
  register layout (r17/r10/r11 marshaling, Bug-7 contract), MMIO control
  block at 0x8000 (offsets 0x00–0x4C + GO-2 tile 0x160–0x16C), E-K1 box
  predicate semantics (unset HI never matches; LD not checked — honesty
  note), full RAM memory map (boxes, guard gaps 717/735, RESERVED
  744–747, mailbox words, receipts, page-table/syscall-table/tile windows),
  GH-22 mailbox word format with check vector 0x3B00112A, arrival
  contract, frozen receipt values, change policy (major bump for frozen
  fields, minor for additive), §7 honesty exclusions.
- `tests/test_box_abi_conformance.py` — 7 legs: 5 GREEN (version+status
  words at halt; memory-map frozen words at fleet halt; mailbox format vs
  check vector + malformed-op rejection; E-K1 predicate on the real engine
  incl. unset-range confinement; arrival contract no-post-no-receipt) +
  2 RED non-vacuity (corrupted memory-map expectations fail; corrupted
  check vector fails).

## Method
Extracted the ABI from the LANDED implementation (agent_resident.py,
glyph_isa_v2.py, baker.py, geos_emit.py) — the spec describes what is,
not what should be; every FROZEN number is asserted against the real
baked image / real engine in the suite, not restated.

## Gate evidence (RED → GREEN, pasted)
RED (first run — my probe defect: reading word 750 from RAM before any
step executed; boot stores are instructions, so it was 0. The SPEC was
right, the probe was wrong — fixed by stepping until the prologue store
lands):

    1 failed, 6 passed in 1.07s
    E   AssertionError: seeded argv word @750 is 0x00000000

GREEN (after fix):

    7 passed in 1.04s

Lane regression (fleet/arrive/queue/resident/conformance):

    29 passed in 2.07s

RED legs 6/7 run IN-PROCESS (pytest.raises around corrupted assertions) —
per policy rule 4 practice established at R1.2/R1.3.

## What this PASS does NOT prove
- No behavior changed: the freeze documents the landed ABI; zero
  production lines touched (diff = 1 doc + 1 test file only).
- Read isolation still NOT claimed (LD unboxed); WGSL shader path still
  DIVERGENT (spec §7 carries the R1.3 honesty note forward); no
  rate/floor claims (check_regime N/A — nothing here quotes a rate);
  supervisor still kernel-in-guest with host seat.
- The suite gates future changes only insofar as it is RUN — it is a
  pytest file, not a substrate fence (teleop discipline: we are the
  containment layer).
- Full-repo pytest has 39 pre-existing collection errors in audio-stack
  tests (soundfile/scipy/mcp/librosa missing in this environment) —
  pre-existing, unrelated to this lane; lane suites run green.

## Decisions logged
- Words 744–747 marked RESERVED (this freeze) for future ABI growth —
  no landed image writes them (word-map audit carried from R1.2).
- Guard words 717/735 documented as USER-store-rejected / SUPER-promoted
  (the Bug-4/GH-16 mechanism), so nobody "fixes" 717 into a box again.
- No brief filed (check_brief): this session implemented its own rung
  directly from the ratified roadmap; the brief contract targets
  cross-context handoffs (skeleton-handoff-contract scope note).
