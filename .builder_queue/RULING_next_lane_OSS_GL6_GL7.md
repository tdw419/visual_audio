# RULING — next lane: OSS GL-6 + GL-7 (seat, 2026-09-12)

Ref: `.builder_queue/REPAIR_PENDING_lane_supply_exhausted.md`, `systems/GLYPH_OSS_ROADMAP.md`

## Decision

Next supply = **GL-6** (recorded/interactive demo, viewable without cloning) and
**GL-7**...[truncated]**Next supply = GL-6 and GL-7**, in that order.

Why these and not the alternatives:
- They are defined, gate-able, and product-facing (the OSS lane exists to show the
  work to strangers), so the loop needs no new scope invention.
- "Declare complete" produces nothing and would be false: the OSS lane has open rows.
- New spine items (retention, write registry, residency) are speculative: Tier C has
  no consumer, and no cross-directory write conflict has been observed.

## Conditions (these preserve the OSS lane's own fence)

The OSS lane declares it does not touch the builder cron. That fence stays intact:
the loop may be the *producer* of these artifacts, never a *dependency* of them.

1. Every artifact must be reproducible from the repo alone under the row's own gate
   (GL-6: plays back end to end; GL-7: methodology + raw numbers regenerable).
2. Publishing stays with Jericho: pushing/publicising, hosting a page, GL-12's
   writeup, any announcement. The loop prepares the artifact, not the publication.
3. GL-9+ (editor tooling, registry, paper) stay parked per the lane's own rule:
   no investment before GL-8 produces a stranger's real friction report.

## Secondary supply (if GL-6/GL-7 block)

The MCP-transport write-identity gate (ruled 994d2dd): today the gates call the
observation-server functions directly, so the DEFECT-20 fix is never exercised
through the transport the builder actually uses.
