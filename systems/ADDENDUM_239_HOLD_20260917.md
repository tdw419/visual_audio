# TICKET SUPPLY STATE — Addendum 239 (HOLD tick ~115)

**When:** 2026-09-17 ~13:15 CDT · **HEAD at launch:** `011c30fd` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/scan_open_rows.py`: rc=0, no open rows.
No eligible row; backlog exhausted; HOLD continues (tick ~115).

## Standing conjunction re-measured at 011c30fd

`SEED=42 bash tools/arc_lega.sh`:

```
====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 80.47s (0:01:20) ======
rc=0
```

crashes=0, oom_kill_delta=0. Artifacts committed: `output/arc_lega_seed42_011c30fd.txt` (+ json sidecar).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop re-emit (write_id 55, emitter-tagged)

```
emit rc: {'committed': True, 'word': 700, 'checksum': '3744eaa7bff2f27d9f9f42444b77e635',
          'tick': 1, 'write_id': 55, 'writer': 'unattributed',
          'written_at': '2026-09-17T18:11:09.921622+00:00'}
```

Independently re-verified via geos tools (B-state, meta before surface):

- `geos_surface_meta` (24,14,12×16): `write_id 55`, `image_md5 3744eaa7…` == emit checksum,
  `age_seconds 10.0`, tick=0 (machine not stepping — canvas is archaeology per teleop rule 1/2).
- `geos_read_cell(700)`: word 700 = `0x3b00112a` at (x=30, y=24), region A — identical value to
  all 54 prior holds; write_id monotonic over 54 (53→54→55).

Maildrop content unchanged since addendum 213; this is a pure re-signal of the same ruling request.
SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per `.builder_queue/BRIEF_se021_reruling_delivery.md`.

## Disk

`/home` 68G free (97% used) — unchanged from addendum 238.
