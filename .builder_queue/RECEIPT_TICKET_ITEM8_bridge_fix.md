# RECEIPT — TICKET_ITEM8 closed: WGSL twin 0x12 bridge exclusion

**Landed:** 2026-09-22 15:47 CDT, commit `97b7732d`, builder cron af3e62239ce2
**Ticket:** `.builder_queue/TICKET_ITEM8_0x12_bridge_false_success.md` → CLOSED
**One gate-able step = one run = one commit.** Queue now genuinely empty.

## Symptom → fix chain

1. Round-3 item 8 measured the twin lying twice on the RUN lane: the spec
   claimed `twin: UNIMPLEMENTED/-1` for 0x12, but the twin actually
   **returned 0 (false spawn-success)** — 18u fell into the GeOS
   reserved-range bridge `16u..255u → registers[rd]=0u`
   (tools/wgsl_glyph_isa_v2.py:829 pre-fix).
2. Item 8 corrected the spec to the measured truth (GAP + ticket) and
   filed the bounded fix: exclude 18u from the bridge → unknown path →
   4294967295u (-1), matching Python and the 0x07 NEGATIVE contract.
3. This session applied exactly that one-line fix to all three twin
   copies (tools/, glyph_dispatch/src/, glyph_dispatch/src/glyph/ —
   md5-identical `4c54de24d542615316fa85673b58d046`, pre-commit hook
   verified sync), re-synced the spec's 0x12 ABI block in the same
   commit, and re-armed the rot guard.

## Gate arc (real exits, in order)

- **Baseline GREEN:** rotguard 24 passed (pre-change tree).
- **RED shown at the right moment:** exclusion applied, gap pin still
  armed → `1 failed (test_l35_gap_pin_0x12_bridge_exclusion_absent,
  tests/test_pillar21_abi_spec_rotguard.py:333) / 23 passed`. The guard
  caught the shader change as designed and forced the spec re-sync into
  the same commit. (One landing-time defect: first pin draft had a bare
  implicit-concat across statement lines → IndentationError at lint;
  fixed to an explicit `anchor = (...)` before any test run.)
- **GREEN after re-sync:** rotguard 24 passed — new
  `test_l35_neg_pin_0x12_bridge_exclusion_landed` pins the exclusion,
  `test_l35_mutated_bridge_reversion_is_caught` proves non-vacuity
  (in-memory twin copy with `&& syscall_num != 18u` removed →
  pytest.raises AssertionError match "0x12").
- **Behavioral (live GPU, GlyphRunner.run_wgsl, probe re-run post-fix):**
  `0x12 RUN2 python=-1 twin=-1 (u32=4294967295) PARITY` ← defect closed;
  `0x07 RUN python=-1 twin=-1 PARITY` unchanged; 0x03/0x04 stub-0
  DIVERGENT (sanctioned NORMATIVE stubs, untouched by design).
- **Regression:** pillar23 parity CI 8 + rotguard 24 + bk2 WGSL syscall
  parity 4 = 36 passed; defect_d 32 + read_path 3 + ram_pixel_space 19 +
  r51 5 + r52 35 = 54 passed; gh15 IR transpiler 10. Pre-commit hook on
  landing: glyph/transpiler differential 38 passed (incl. 4 GPU GO-legs),
  3-copy twin sync verified, pillar23 parity 8 passed.

## What this PASS does NOT prove

- Single machine (Intel ARL iGPU via Vulkan), one probe invocation per
  row; the PARITY claim covers the containment-refusal path, not
  arbitrary inputs (0x12 has no success path on either engine — the
  refusal path IS the whole contract).
- No RUN2 spawn semantics were implemented on the twin; the normative
  contract is NEGATIVE (-1), same as 0x07. 0x03/0x04 stubs unchanged.
- No rate/floor claims → floors/check_regime N/A. WGSL engine copy used
  by GlyphRunner = tools/ copy; the two glyph_dispatch copies are
  distribution mirrors synced by md5, not separately executed.
