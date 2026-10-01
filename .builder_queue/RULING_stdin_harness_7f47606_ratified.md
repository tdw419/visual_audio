# RULING: stdin harness commit 7f47606 — ratification of authorization citation

**Date:** 2026-09-15
**Seat:** Jericho (in-channel, this oversight session)
**Subject:** commit 7f47606 "feat(engine): interactive terminal for glyph apps - real SYSCALL_READ + echo shell"

## Dispute

7f47606's commit message cited `Jericho-authorized ("yes, build it")` — a grant
not present in the oversight channel where the authorization-boundary discussion
occurred. Under the specific-gate rule, a citation of seat authorization that
cannot be traced to Jericho's own word is treated as unproven, and the
keep-vs-revert question was escalated rather than acted on unilaterally.

## Verification performed (measured, not narrated)

- Gate re-run live: tests/test_glyph_interactive_shell.py + tests/test_glyph_isa_v2.py → 11 passed (includes non-vacuity leg).
- Ladder regression: test_glyph_app_echo/voice/assembler_labels → 10 passed.
- Artifact read-only review: SYSCALL_READ 0x02 de-stubbed (ring drain, real byte count, RAM-not-image write, bounded memory growth); experiments/glyph_interactive_shell.py batch mode never touches stdin (regression-sweep invariant holds).

## Ruling

1. **Authorization CONFIRMED by seat.** Jericho states the "yes, build it" was
   his, given in the session that performed the work. The citation in 7f47606
   is genuine. No defect in provenance.
2. **Commit 7f47606 is KEPT as-is.** No revert, no re-run; the work and its
   gates stand.
3. **The specific-gate rule itself is reaffirmed, not weakened:** a specific
   confirmation gate in a ticket/ruling requires that explicit confirmation.
   This case resolves as "authorization was real, cross-channel" — not as
   license to infer grants from context. Disputed citations still go:
   measure first (git/tests), then ask the seat; never revert unilaterally,
   never self-ratify.

## Disposition

Ticket: none required (retroactive ratification of an already-gated commit).
This file is the provenance record.
