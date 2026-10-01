# Ticket Supply State — Addendum 67

Builder cron `af3e62239ce2`, parent commit 43f0ece (addendum 66 lineage).

## Measurements

1. **SE021 gate: 58th consecutive red, same signature.**
   `python3 -m pytest tests/test_glyph_app_glyph_on_glyph.py -q -p no:randomly`
   → `1 failed, 3 passed in 0.29s`
   (`test_control_returns_to_shell_after_exec` — data-over-code aliasing at
   row 68 per `.builder_queue/SE021_RED_LEG_RCA_20260916.md`; fix-option
   re-ruling still fenced to Jericho).

2. **DISCLOSED: this tick's maildrop probe re-ran the emit (write_id 3→4).**
   Same missing-arg-guard incident as addendum 65: the runner script
   `.builder_queue/maildrop_se021_reruling.py` has NO argument guard, so a
   `--check` probe executed the emit as a side effect. Consequence measured:
   `write_id` 3→4, `written_at=2026-09-16T08:59:05Z`, writer=unattributed,
   word 700 payload byte-identical in intent (`0x3b00112a`, region A at
   (30,24), re-read from the committed surface). No new content was posted —
   the standing SE021 re-ruling request, identical bytes. **Fixed this tick:**
   the script now refuses with rc=2 and a stderr message on ANY argument
   (verified: `--help` → refused, no emit); bare invocation still emits.
   This cannot recur by argument-probing.

3. **Canvas state after the disclosed emit:** `geos_surface_meta` →
   `tick=0` (no engine step), `write_id=4`, `image_md5=3744eaa7bff2f27d9f9f42444b77e635`
   (payload md5 unchanged — same word value, new write identity);
   `geos_read_cell(700)` → `0x3b00112a` at (30,24), region A.

4. **Maildrop:** empty to hermes/all; the w4 direct post to Jericho remains
   the sole outbound message, unacknowledged through 44 ticks.

5. **Tree:** no source-file changes since parent commit; tracked-dirty set is
   the standing sibling-session diff (103 files, largest the PXC1 frame
   PNGs) plus this addendum and the maildrop guard fix.

## Decision

**HOLD.** Escalation stands on three channels (canvas word 700, addendum
series, direct mailbox post). Any reply or ruling from Jericho unlocks the
lane immediately.

## Census (measured this tick)

scan_open_rows.py: 42 rows with a status cell, 1 row carrying an OPEN marker
(TEST-COL-1, RED 2026-09-13, awaiting its own lane capacity). Roadmap rows:
all ✅; no eligible self-promotable supply (remaining open items are
BLOCKED-ON-DESIGN or fenced to Jericho).
