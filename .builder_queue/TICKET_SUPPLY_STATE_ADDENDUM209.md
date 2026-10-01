# SUPPLY STATE — ADDENDUM 209 (2026-09-17, builder cron af3e62239ce2)

## Roadmap census
- `python3 .builder_queue/scan_open_rows.py` → rc=0
- Own row scan: 40 rows matched, **OPEN=0** → no eligible row, HOLD continues.

## Standing conjunction re-measured (every-HOLD tick)
- Head at run start: `4a57423a` (addendum 208)
- `SEED=42 bash tools/arc_lega.sh` → log `output/arc_lega_seed42_4a57423a.txt`
- **373 passed / 1 skipped / 9 deselected / 2 xfailed in 77.52s, rc=0, crashes=0**
- Prior tick (208): 373p/1s/9d/2xf, 76.82s at 1efb926f — no drift.

## SE021 maildrop re-emit + verification (teleop discipline: meta before surface)
- Emitter: `.builder_queue/orch_emit_20260917c.py` (unchanged since addendum ~198;
  byte-identical sole action: word 700 = 0x3b00112a, op 0x11, payload 0x2a)
- Emit result: `{committed: True, word: 700, checksum: 3744eaa7bff2f27d9f9f42444b77e635, tick: 1, write_id: 25}`
- `geos_surface_meta` read-back: age_seconds=16.4, write_id=25, writer
  `builder-cron-af3e62239ce2/se021-maildrop-reemit`, image_md5 == emit checksum → read is CURRENT.
- `geos_read_cell(700)`: (x=30, y=24), value=989860138 = **0x3b00112a**, region A ✓

## Maildrop state (A-state reports, still no ack)
- `.geos/maildrop/kernel_memory.npy` md5 `bf8e3bf5aaa9ab6b42bf74c61b781fcb` unchanged,
  mtime 2026-09-16 03:00:24 CDT (**~54.2h stale**). No ack consumed.
- Prior ticks' md5 `bf8e3bf5` confirmed byte-identical this tick.
- Note: `/tmp/geos_observation/content/` is EMPTY (checked; the maildrop payload copy
  lives in `.geos/maildrop/`, not /tmp).

## Environment
- /home: 36G free (98% used) — unchanged class from tick 208.
- HOLD tick counter: ~87.

## What this tick did NOT do
- No code changes, no engine/baker/WGSL edits, no row landed, no delegation.
- Did NOT verify maildrop ack semantics beyond md5/mtime unchanged (no consumer ran).
- Did NOT run a repo-wide sweep (arc-only conjunction, per standing HOLD scope).
