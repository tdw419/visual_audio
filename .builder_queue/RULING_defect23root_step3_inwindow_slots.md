# RULING — DEFECT-23-ROOT step 3: the in-window slot vector (G2/G3)

**Date:** 2026-09-14 · **Seat:** orchestrator ruling under Jericho's standing delegation
("your ruling = i want you the ai or the builder to decide things like this") · reversible
**Prior:** RULING_defect23_root_pte_acceptance.md (912ebe2) explicitly deferred this vector;
step 2 (window tag) landed 13d94a9. L1/L2 remain strict-xfail by design.

## Decision

**Producer-side bake-time table validation. Engine walk UNCHANGED.**

1. A shared `validate_page_table(memory, pt_base, max_frame)` helper (home: `tools/geos_aspace.py`,
   re-exported next to `stamp_page_table`) checks every slot in `[pt_base, pt_base+256)`:
   slot must be `0` (unmapped) **or** decode with `(pfn <= max_frame)` and `(pte & 0xFF) in
   {0x1, 0x3, 0x5, 0x7, 0x107, ...}`-style legal flag masks. Any violation FAILS THE BAKE.
2. All producers call it at the end of table construction: baker (all six table-setup modes),
   gh25 `_two_pass_bake`, geos_aspace `stamp_window` users.
3. The engine's walk contract is documented as-is: **flag-bit trust** — a tagged window's slots
   are trusted modulo PTE_V/W/U checks; damage is bounded by the 5b62955 ceiling. This mirrors
   real hardware: MMUs validate flag bits, OSes audit their own tables with tools.
4. L1/L2 keep strict-xfail, `reason=` updated to cite this ruling and the bake-time validator.

## Why (the fact that decides it)

- PTE decode is `pfn = pte >> 8`; flags live in the low byte. `0x...07` (V|W|U) is among the
  most common low bytes in arbitrary data, so **no flag-side check at walk time can
  discriminate** garbage from a valid entry. Per-slot discrimination at the engine requires
  per-slot tagging = the declined Option 2 (all-producers churn, receipts re-derivation).
- The defect that actually bit us was a **producer bug** (baker arming loop, fixed c7995a7),
  not an engine gap. The engine did exactly what its contract says; the producer wrote a
  non-PTE word into a table. Guards belong where the knowledge is: at bake.
- Baker zero-inits RAM at bake (:5116), so legitimate producers emit only clean-V or V=0
  slots today; the validator locks that invariant in against regressions.

## Definition of Done

- RED-first gate: new test seeds `0x00000907` into a tagged window's slot and asserts the
  bake-time validator REJECTS it (fails red against producer trees lacking the call).
- GREEN: all six baker modes + gh25 bake pass validation on their real tables.
- No PTE value changes; window tag semantics untouched; twins byte-identical (hook enforces).
- Engine probes (probe G2 verdict `SILENT_MISDIRECTION_CONFIRMED`) stay RED **on purpose** —
  the probe remains the canary for the engine-side contract; it is not expected green.

## Explicitly not adopted

Per-slot tagging (old Option 2) — declined on proportionality, unchanged. Shadow-slot parity —
layout churn with no incident to justify it. Sparse memory model (Option 4) — rejected.

## RATIFIED by Jericho (2026-09-14, chat + explicit confirmation)

Three answers, verbatim from Jericho's confirmation round:
1. Delegation: STANDING - "that whole class is ours to rule and land with gates."
2. Step 3 disposition: KEEP IT - ratified.
3. Future default: RULE AND LAND, THEN REPORT.

This supersedes the provisional status the ruling carried at issue time. The
challenge that triggered the confirmation (delegation scope) is acknowledged as
the correct process catch; the answer is now the seat's, not the delegate's
citation of itself. Commentary-issued "Seat Decision" blocks remain VOID - this
ratification covers Hermes/builder rulings under the standing delegation only.
