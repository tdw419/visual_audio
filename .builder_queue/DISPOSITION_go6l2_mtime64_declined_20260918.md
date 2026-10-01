# DISPOSITION — GO-6 L2 64-bit mtime widening: DECLINED-BY-DEFAULT, staged material intact

**Status:** DECLINED (not approved, not rejected-on-merits) · 2026-09-18 · policy D-3 of POLICY_decision_delegation_20260918.md
**Item:** RULING_go6l2_mtime64_DRAFT.md (option 1, scope-limited 64-bit mtime/mtimecmp widening in SPATIAL_RV32I.wgsl + Python twin).

## Why declined, not applied

The ruling's own constitution requires "Jericho ratifies option 1 in-channel" — a named hold-gate with a verbatim-word requirement. Standing rule (flagged 4x by Jericho on 2026-09-14): standing grants never backfill specific gates, and "you lead"/"make this work" are delegation-of-decisions, not per-gate ratification words. The conservative reading binds: the lane cannot self-ratify, and declining the change is the only action available that does not cross the line.

## Why NOT filed as engineering-rejected

The evidence for option 1 is strong: the QEMU reference run executed the identical kernel past the stall milestone; the engine measurably has no hi word at all (:22), both write paths drop it (:172-174, :882-883), the latch compare is 32-bit (:336), the tick is 32-bit (:998); the widening was pre-declared in the skeleton's own comment (:21-23); the erratum discipline (misread `1u` caught and corrected by cross-session citation check) is the ruling at its most trustworthy. Nothing in the measurement argues against it. What's missing is solely the constitutional word.

## Disposition mechanics

- The DRAFT ruling and brief `.builder_queue/brief_go6_mtime64.md` REMAIN in place, unchanged, inert as designed.
- The blocker note `REPAIR_PENDING_go6l2_mtime_64bit_widening.md` is marked RESOLVED-BY-DECLINE: the loop's seat is freed. No more holds counting on it.
- If Jericho ever says the ratification word ("option 1 ratified" verbatim), the staged material activates in one step exactly as drafted: rename ruling, remove DRAFT banner, open the roadmap row, run the T1-T5 gates.
- Zero engine lines changed. The GO-6 L2 gate (vd0 + dd round-trip) remains unmet — recorded honestly as an OPEN capability gap, not a hidden one. This is the cost of the constitutional boundary, and it is the correct cost.

## Executive summary for Jericho (if you ever read this)

One message — "option 1 ratified" — starts a fully-specified, fully-gated, pre-costed engine fix that unblocks the GPU-native L2 kernel boot. Everything is staged. Your move, whenever, or never.
