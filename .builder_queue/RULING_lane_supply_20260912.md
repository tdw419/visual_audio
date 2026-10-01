# RULING — lane supply (2026-09-12, seat: orchestrator)

Ref: `.builder_queue/REPAIR_PENDING_lane_supply_exhausted.md`

## Ruled now — one item authorized (no design judgment, gate-able)

**MCP-transport write-identity gate.** Today every gate calls the observation
tool *functions* directly, so the DEFECT-20 identity fix is never exercised
through the transport the builder actually uses. Add a gate that drives
`tools/geos_observation_server.py` over stdio and asserts the surfaced
`write_id` / `writer` for a known publish, plus a negative leg (an
unattributed read must fail loudly). Mechanical, falsifiable, no taste
required. File as a backlog item and promote under the standing rule.

## Reserved to Jericho — product direction, not a builder call

1. **Take the OSS lane's GL-6 / GL-7** (recorded demo viewable without
   cloning; honestly-reported benchmark) — gate-able, but publication-facing.
2. **Declare the self-hosting lane complete** and re-point the cron.
   Note: cadence changes save nothing (suppressed ticks cost 0 API calls).
3. **Write new spine items** (retention policy for per-write archives; global
   cross-directory write registry; residency/Tier C stays parked).

## Standing

Until (1)-(3) is ruled, the loop rescans, finds nothing eligible, and reports.
It must not invent scope and must not poach another lane.

## RULED 2026-09-13 (Jericho, "You lead"; drafted by Hermes)

Item (3) was acted on — the two named spine items were authored as a **skeleton round**, and the four design
questions left open by that work are now decided:

- `RULING_oskel_step9_space_lifetime.md` — OPTION 1, refcount-only teardown (space owns its asid).
- `RULING_spine_wirein.md` — OPTION 2, `publish()` best-effort append + operator CLI; default policy is
  explicit-plan-only; refusal = written plan + exit 2; failed append labeled `unattributed: true`.
- `RULING_gh12_gate_determinism.md` — OPTION 3, split the claim (deterministic leg in the arc, live draft as
  non-blocking smoke).
- `RULING_arc_determinism_standing.md` — STANDING RULE: the arc is deterministic or it isn't evidence. Leg A runs
  only via `SEED=<n> bash tools/arc_lega.sh`; receipts carry head + seed; `-p no:randomly` is never a global default.

Items (1) publication and (2) declaring the lane complete remain open and reserved. 
