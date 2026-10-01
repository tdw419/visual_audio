# TICKET — Supply State Addendum 251 (builder cron af3e62239ce2, 2026-09-17)

Census re-measured this tick: `scan_open_rows.py` silent (OPEN_COUNT 0). NOTE:
the scanner on disk is a sibling session's uncommitted rewrite (last-transition-
marker logic vs the committed prefix-ID version); this tick ran THAT version and
it agrees with the committed one's verdict — 0 open rows either way. Not touched
by this lane.
Head at tick start `976188e1` (addendum-250). Tracked-dirty ~240 + ~2.4K total —
sibling/parallel churn, non-supply, not touched.

## Standing re-check (own run this tick)

- Arc leg A at HEAD `976188e1`, seed 2639, **rc=0**:
  373 passed / 1 skipped / 9 deselected / 2 xfailed, 81.03 s, crashes=0,
  oom_kill_delta=0, log `output/arc_lega_seed2639_976188e1.txt`.
- DEFECT-18 (a) + DEFECT-17 (d) + landing conjunction:
  `tests/test_defect18_tick_regfile.py` + `tests/test_defect17_x31_refusal.py`
  + `tests/test_glyph_app_glyph_on_glyph.py` **17 passed in 2.30s**
  (`-p no:randomly`). No new eligibility created.
- Backlog (GLYPH_BACKLOG) exhausted; nothing mechanical is eligible. HOLD
  continues (~62nd tick).

## SE021 re-ruling maildrop — HOLD

Maildrop content `.geos/maildrop/content/hermes.0001.ruling.md` md5 `ab846c18…`
UNCHANGED (no ack). Word 700 re-verified **RESIDENT** via fresh `geos_read_cell`
→ region A (30,24), value `0x3b00112a` — delivery stands, no re-emit needed.
No ack, no RULING landed. Holding — no self-ratification. RCA:
`.builder_queue/SE021_RED_LEG_RCA_20260916.md`.

## Substrate witness (B-state, freshness stated)

Meta-before-surface this tick: served image `/tmp/geos_observation/kernel_memory.npy`
md5 `3744eaa7…` write_id 68, written_at 2026-09-17T20:15:54Z, tick=0,
age_seconds 1521 at read — that is our own addendum-249-era emit, not engine
progress; the machine is not stepping on its own. Canvas read this tick:
`geos_read_cell(700)` only (the RESIDENT check above). Nothing interpreted
beyond the emitted word itself. No B-state conclusions drawn.

## Host constraint

`/home` 54G free (97%) re-measured this tick. `/var/crash` 3 non-fixture
reports persist (L6c red, operator seat).

## What this tick does NOT prove

- No sweep beyond the standing leg A + conjunction ran (none is due — no landed
  code this tick, docs-only).
- The maildrop emit (prior ticks) proves delivery to the substrate word, not
  that any resident agent consumed it (none has across the hold).
- The sibling scanner rewrite is UNVERIFIED by any gate this lane runs; only
  its agreement with the committed scanner on today's roadmap was observed.
