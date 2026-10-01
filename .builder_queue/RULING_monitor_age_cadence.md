# RULING — monitor fingerprint must exclude clock-driven content

**Date:** 2026-09-14 · **Seat:** orchestrator ("you lead") · reversible by Jericho
**Ticket:** `.builder_queue/REPAIR_PENDING_monitor_age_cadence.md` (BLOCKED-ON-DESIGN)
**Instrument:** `~/.hermes/scripts/glyph_build_chain_monitor.py` (Jericho's loop monitor)

## Decision

The watched fingerprint must carry REPO STATE, never CLOCK STATE. Adopted:

- Exclude time-valued fields from `.builder_queue/*.json` when hashing: any key named
  `updated`/`filed`/`run_at`/`checked_at`/`timestamp`, and any value matching a date/time
  pattern. (Confirmed live: `DEFECT-22_arc_legA_instability.json` carries
  `"updated": "2026-09-14 13:3x"`, rewritten per ledger leg — a clock-driven field inside a
  monitored file.)
- Keep hashing what actually means something changed: repo code paths, the roadmap's STATUS
  column, and each ticket's `status` field.

## Why this is mechanism, not taste

The hourly re-fire on a clean tree is a phantom: the fingerprint changed, the loop did not.
Each phantom wake costs a full builder fire (measured 2.9-5.3M tokens/fire on deepseek, and the
lane is now on a plan-quota provider). Excluding clock state is harness flow, not cadence policy:
the cadence itself (`every 2m`) is unchanged.

## What this does NOT license

- Do NOT lengthen the cadence or disable the monitor to stop the re-fire. Fix the fingerprint.
- Do NOT exclude a ticket's `status` field: an OPEN->CLOSED transition MUST still wake.
- Do NOT carry the exclusion into the seat-blocker sensor's digest (it already excludes clock
  state by design; keep them consistent, not coupled).

## Gate

1. RED-first: mutate ONLY a ticket's `updated` value -> fingerprint must NOT change.
   (Before the fix it changes; show both states.)
2. No over-suppression: flip a ticket `status` OPEN->CLOSED -> fingerprint MUST change.
3. Clean-tree hour boundary: no re-fire across a simulated hour with no code change.

## ADDENDUM - implemented and gated (2026-09-14)

The ruling sat as decision-without-code for ~11h; implemented this tick in
`~/.hermes/scripts/glyph_build_chain_monitor.py` (job af3e62239ce2 monitor_script;
no repo twin exists - the gate below is the in-repo artifact).

Changes:
1. queue count = OPEN tickets only (status-token scan; commit_msg_/append_
   drafts excluded). Was: every *.json, so queue=N was permanent (300+ closed
   files) and state=REPAIR_PENDING could never clear.
2. ticket_age_h RETIRED from the fingerprint and the output line. Was:
   int((now - newest_ticket_mtime)//3600) - pure clock state, measured RED
   (age 0 -> 1 across one hour, zero commits).

Gate `tests/test_monitor_fingerprint_hygiene.py` (runs the LIVE monitor):
  L1 mtime-only change on a tracked ticket -> digest STABLE
  L2 volatile 'updated' rewrite in an untracked ticket -> digest STABLE
  L3 status OPEN->CLOSED -> digest MOVES, removal restores baseline
  all PASS vs fixed; vs reconstructed pre-fix monitor L3 FAILS -> discriminates.

First-draft gate defect (kept here as the lesson): restoring a mutated json
via json.dump round-trip REFORMATS the file - bytes != HEAD tripped the
tracked-dirty channel and poisoned the baseline. Raw-bytes restore only.

RATIFIED 2026-09-14 — seat Jericho, via the explicit delegated "you lead" grant
given this session against a written decision summary (retire outright vs widen
1h→6h; retire chosen: repo state over clock state, and the 15-min seat-blocker
sensor covers the stale-ticket visibility this bucket was built for).
Ticket `REPAIR_PENDING_monitor_age_cadence.md` CLOSED in the same commit.
