# TICKET SUPPLY STATE — Addendum 252 (2026-09-17, builder cron af3e62239ce2)

**Head:** `215d6196` · **Branch:** glyph-transpiler-autoloop · **Action:** HOLD

## Scan (rc=0)

`python3 tools/supply_census.py --json` → `total=77, open=[], closed=77, ambiguous=[], unparsed=[]`.
0 open rows. DEFECT-17 (x31 refusal gate, `7a4208a`) and DEFECT-18 (tick register
snapshot) both closed; ruling options (a)+(d) landed and gated.

## Open tickets — none builder-eligible

- DEFECT-22: SERIES STOPPED per `RULING_defect22_series_stop.md` (not reproduced, 51
  consecutive greens; reopen only on crashes>0 or oom_kill_delta>0).
- DEFECT-22E: measured-negative (1.9 GB class not reproducible at HEAD; attributed to
  condition, not code) — awaiting Jericho's pick.
- DEFECT-23: soundness/design (paged walk accepts data word as PTE) — needs design call.
- DEFECT-29: record-only strict-xfail (capability never built).
- Backlog: exhausted (15/15 promoted & closed).

## Standing conjunction re-measured at 215d6196

`SEED=22599 bash tools/arc_lega.sh` → **rc=0, 373 passed / 1 skipped / 9 deselected /
2 xfailed, 80.51s**, oom_kill_delta=0, mem_peak 846 MB.
Log `output/arc_lega_seed22599_215d6196.txt`.
DEFECT-18a + DEFECT-17d gates: `pytest tests/test_defect18_tick_regfile.py
tests/test_defect17_x31_refusal.py -q` → **13 passed, rc=0** (this tick).

## Maildrop / substrate

- SE021 maildrop `.geos/maildrop/content/hermes.0001.ruling.md` md5 **ab846c18**
  reproduced exactly this tick (resolves addendum 249's one-off a0936dc5 flag as a
  non-repeat); `geos_mailbox.py verify --to all` → rc=0 "all verified"; ~63rd hold,
  no ack from Jericho.
- Word 700 re-verified via fresh `geos_read_cell`: **0x3b00112a**, region A (30,24) —
  RESIDENT, no re-emit needed.
- Surface meta (meta-before-surface): tick=0, write_id 68, image_md5 `3744eaa7`,
  age 1939.9s at read, writer "unattributed" — our own prior emit; machine not
  stepping. No B-state conclusions drawn from a non-stepping substrate.

## Environment

- /home: 54G free (97% used) — unchanged from addendum 250 (not the constraint).
- /var/crash: 3 non-fixture reports persist (operator seat, unchanged).
- Monitor state: DIRTY_ACTIVE, head moved 976188e1→215d6196 (own addendum-251 commit);
  tracked_dirty 240 is the known churn (infinite-desktop-camera frame writes, daemon
  context, virtio_pixel_rs lane) — not touched this tick.
- Tracked tree untouched this tick except this addendum file.

## Next

Continue HOLD. Eligible supply reappears when: Jericho acks SE021 / picks the
DEFECT-22E next step / releases the DEFECT-22 level trigger, or a new roadmap row or
backlog item with concrete gate clauses lands. Scan runs every tick.
