# REPAIR_PENDING — the other self-wake: a clock-driven hourly re-fire on a clean tree

**Status:** CLOSED 2026-09-14 — RATIFIED (seat: Jericho, via explicit delegated "you lead" grant
given this session against a written decision summary; ratified-as-landed, since the stricter
variant — bucket retired outright, not widened 1h→6h — was already on disk at `bdc084b`/`0658ca3`
with gate 3/3 vs live, discriminating vs pre-fix). The 15-min seat-blocker sensor covers the
stale-ticket visibility this bucket was built for.
**Seat:** Jericho. **Filed:** 2026-09-13 ~20:5x CDT by the orchestrator seat (cron `5ad75de3aac3`),
split out of `REPAIR_PENDING_monitor_scope_selftrigger.md` so it stays visible after that ticket's
mechanism half was ruled (`.builder_queue/RULING_monitor_scope_selftrigger.md`).
**Instrument:** `~/.hermes/scripts/glyph_build_chain_monitor.py` (md5 `5b868a9571f6f6b9b98dc92d80d82b31`),
cron `af3e62239ce2`, `every 2m`, enabled.

## The open half, measured by the sibling ticket (not re-measured here)

`:117-124`: on a **clean** tree with ≥1 `*.json` ticket, the fingerprint carries
`ticket_age_h = int((now − mtime) // 3600)` and the comment at `:111-116` says this level trigger is
deliberate — *"include its mtime age bucket in the fingerprint so it stays hot until the ticket is
resolved"*. The wake measured on the sibling ticket was a pure hour boundary: every other field identical,
`ticket_age_h` 0 → 1 as `DEFECT-22_arc_legA_instability.json` crossed 1 h of age.
Consequence: up to 24 wakes/day with nothing in-lane changed, while any ticket is open.

Probe and candidate patch exist and are **not applied** — evidence on the sibling ticket:
`output/monitor_ticket_age_wake_probe.txt` (`PROBE VERDICT: PASS`; L2 reproduces the arm at +1/+2/+3 h,
L3b shows the level trigger survives a wider bucket, L5 asserts the live script untouched),
held patch `.builder_queue/held_patches/monitor_ticket_age_bucket.held.patch`
(`TICKET_BUCKET_SECS = 6*3600`, field renamed `ticket_age_6h`).

## Why this is the seat's, not the lane's

The sibling ticket's ruled half was a printed field that contradicted the module's own documented contract.
This half does not: the bucket is documented as an intentional level trigger, so changing it picks a
**cadence** — and cadence is the seat's (`RULING_lane_supply_20260912.md` already records a seat ruling on
cadence: *"cadence changes save nothing (suppressed ticks cost 0 API calls)"*, which this measurement
complicates rather than settles, since these wakes are *not* suppressed).

## Options, cheapest first

1. **Widen the bucket** (held 6 h patch). Quiet window 1 h → 6 h; every other trigger untouched.
   Cost: one held patch, gate already probed. Risk: an open ticket can now sit 6 h before the level
   trigger re-fires — acceptable only if the ticket is also visible somewhere else (the seat-blocker
   sensor, 15 m, is that somewhere else today).
2. **Drop the age field entirely** from the fingerprint. Zero clock-driven wakes; the wake then depends on
   ticket *appearance/disappearance* (module docstring condition (c)) plus the seat-blocker sensor.
   Cost: the level-trigger guarantee for a stuck open ticket is gone — the 2026-09-09 GH-20 incident
   (4 h asleep with an open ticket) is the exact failure this field was added for.
3. **Leave it as-is** and accept ≤24 no-work wakes/day while any ticket is open.
   Cost: the same class of spend the sibling ruling just removed.

**Seat's recommendation:** option 1, *conditionally* — widen to 6 h only because the 15-minute seat-blocker
sensor now covers the "open ticket, nothing happening" state independently; option 2 is only safe if the
seat is content that a ticket's existence is signalled by the sensor and not by the watchdog.

## What is not licensed until ruled

No edit to `ticket_age_h`, its bucket, `STALL_SECS`, or any interval; no schedule change on `af3e62239ce2`.
