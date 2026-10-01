# RULING — SE021 spawn interpreter resolution: option 1 ratified, ticket CLOSED

**Answers:** REPAIR_PENDING_se021_spawn_interpreter_resolution.md (filed
2026-09-16, builder cron af3e62239ce2, addendum 147)
**Ruled:** 2026-09-19 — Jericho (queue ruling session)

## Decision

OPTION 1 (test-side environment skip-with-reason) adopted — already landed
and receipted: `0f8b113b` (guard in `child_env`,
tests/test_glyph_app_glyph_on_glyph.py:87–99) +
`RECEIPT_se021_opt1_interpreter_guard.md`. The filing-time hold (engine =
sibling lane's WIP surface) measured stale 09-17, re-checked clean 09-19.
Ticket closed; no engine action owed.

## Evidence (from the receipt)

- Cause measured: buildroot host python3.14 lacks numpy → shebang resolves
  there under hostile PATH → rc=1 → `ERR:RUN_DENIED` — an environment
  artifact wearing a containment-failure signature.
- Guard: pinned PATH 4/4 passed; hostile PATH 1 pass / 3 skip with named
  reason, exit 0 (`output/se021_opt1_hostile_path.txt`). No assertion
  changed, no leg deleted.

## Not licensed

- Options 2/3: runner self-re-exec, engine-side interpreter pinning /
  `SYSCALL_RUN2` env confinement — containment surface needs its own ruling.
- Skip widening: environment-conditions only; a skip on the pinned-PATH
  sweep is a DEFECT, not a pass.
- This is NOT the SE021 mailbox-word re-ruling
  (`.geos/maildrop/content/hermes.0001.ruling.md`,
  `BRIEF_se021_reruling_delivery.md`, the `:158` RED leg) — separate, still
  held for Jericho.

## Standing gate

- `PATH=/usr/bin:$PATH python3 -m pytest tests/test_glyph_app_glyph_on_glyph.py -q`
  → 4 passed, exit 0; `child_env` keeps the which-python3+numpy skip probe.
