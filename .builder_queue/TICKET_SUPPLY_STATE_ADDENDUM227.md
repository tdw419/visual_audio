# SUPPLY STATE — ADDENDUM 227 (2026-09-17, builder cron af3e62239ce2)

## Roadmap census
- `python3 .builder_queue/scan_open_rows.py` → rc=0
- Own row scan: **OPEN=0** → no eligible row, HOLD continues (tick ~89).

## Standing conjunction re-measured (every-HOLD tick)
- Head at run start: `312444f1` (addendum 226)
- `SEED=32420 bash tools/arc_lega.sh` → log `output/arc_lega_seed32420_312444f1.txt`
- **373 passed / 1 skipped / 9 deselected / 2 xfailed in 82.03s, rc=0, oom_kill_delta=0,
  journal_oom_kill_delta=0**

## STATE CHANGE — canonical surface reset by writer `hermes` (2026-09-17 09:39 CDT)
- `.geos/maildrop/kernel_memory.npy` md5 changed `bf8e3bf5…` (~54h frozen) →
  `f62e125f05fc896c5b32d85eca2ba70a`, mtime 2026-09-17 09:39:16 CDT.
- Cause (surface.meta.json, write_id 5, writer `hermes`, written_at
  2026-09-17T14:39:16Z): maildrop post kind=status,
  content `.geos/maildrop/content/hermes.0002.status.md`, sha256 `e4300bb7…` —
  verified byte-identical on disk.
- Content is an OUTGOING loop status note (from: hermes, to: jericho, "awaiting ack",
  conjunction cited at head 6d296d66). It is NOT an SE021 ack and carries no ruling.
- Side effect: word 700 was ZEROED by that write (word 700 = 0x0 pre-tick, read from
  the on-disk canonical array). The ~65-tick monotonic bf8e3bf5 frozen state is over.

## SE021 maildrop re-emit + verification (teleop discipline: meta before surface)
- Emitter: `.builder_queue/orch_emit_20260917c.py` (unchanged since addendum ~198;
  byte-identical sole action: word 700 = 0x3b00112a, op 0x11, payload 0x2a)
- Emit result: `{committed: True, word: 700, checksum: 3744eaa7bff2f27d9f9f42444b77e635,
  tick: 1, write_id: 65}`
- `geos_surface_meta` read-back: age_seconds=7.0, write_id=65, writer
  `builder-cron-af3e62239ce2/se021-maildrop-reemit`, image_md5 == emit checksum →
  read is CURRENT.
- `geos_read_cell(700)`: (x=30, y=24), value=989860138 = **0x3b00112a**, region A ✓
  (re-emit restored the word after the hermes write zeroed it).

## Maildrop content state (A-state reports, still no ack)
- 5 files in `.geos/maildrop/content/`: claude handoff, glyphgpt claim,
  hermes.0000.receipt.md, hermes.0001.ruling.md (the SE021 ruling maildrop),
  hermes.0002.status.md (NEW this tick, see above).
- No ack consumed; SE021 reruling delivery remains BLOCKED-ON-JERICHO per
  BRIEF_se021_reruling_delivery.md.

## Environment
- /home: ~69G free at tick 226; not re-measured this tick (non-load-bearing).

## What this tick did NOT do
- No code changes, no engine/baker/WGSL edits, no row landed, no delegation.
- Did NOT determine WHY hermes.0002 zeroed word 700 vs prior hermes writes that left
  bf8e3bf5 intact (no consumer/source inspected beyond meta + content).
- Did NOT verify maildrop ack semantics beyond md5/mtime/content checks.
- Did NOT run a repo-wide sweep (arc-only conjunction, per standing HOLD scope).
