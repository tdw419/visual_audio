# TICKET SUPPLY STATE — Addendum 243 (HOLD tick ~119)

**When:** 2026-09-17 ~14:37 CDT · **HEAD at launch:** `744ded4e` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/scan_open_rows.py`: rc=0, no open rows.
No eligible row; backlog exhausted; HOLD continues (tick ~119).
DEFECT-18(a) + DEFECT-17(d) remain already-landed (addendum 205 verification stands).

## Standing conjunction re-measured at 744ded4e

`SEED=23543 bash tools/arc_lega.sh`:

```
====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 81.41s (0:01:21) ======
rc=0
```

crashes=0, oom_kill_delta=0, journal_oom_kill_delta=0, mem_peak 39.99 GB,
loadavg after 3.06/3.14/2.65. Artifacts committed:
`output/arc_lega_seed23543_744ded4e.txt` (+ json sidecar).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop re-emit (write_id 66, emitter-tagged)

```
emit rc: {'committed': True, 'word': 700, 'checksum': '3744eaa7bff2f27d9f9f42444b77e635',
          'tick': 1, 'write_id': 66, 'writer': 'builder-cron-af3e62239ce2/se021-maildrop-reemit',
          'written_at': '2026-09-17T19:37:23.503441+00:00'}
```

Independently re-verified via geos tools (B-state, meta before surface):

- `geos_surface_meta` (24,14,12×16): `write_id 66`, `writer builder-cron-af3e62239ce2/se021-maildrop-reemit`,
  `image_md5 3744eaa7…` == emit checksum, `age_seconds 6.8`, tick=0 (machine not stepping —
  canvas is archaeology per teleop rule 1/2).
- Independent freshness: `stat /tmp/geos_observation/kernel_memory.npy` → mtime
  2026-09-17 14:37:23 CDT, 65,664 bytes — matches `written_at` to the millisecond.
- `geos_read_cell(700)`: word 700 = `0x3b00112a` at (x=30, y=24), region A — identical
  value to all 65 prior holds; write_id monotonic over 65 (65→66).

Maildrop content unchanged since addendum 213; this is a pure re-signal of the same ruling request.

## State

SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per `BRIEF_se021_reruling_delivery.md`.
No self-ratification; the maildrop is the disclosed sole substrate action.
