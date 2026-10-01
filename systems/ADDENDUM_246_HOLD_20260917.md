# TICKET SUPPLY STATE — Addendum 246 (HOLD tick ~122)

**When:** 2026-09-17 ~17:45 CDT · **HEAD at launch:** `840c8c55` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/scan_open_rows.py`: no output, rc 0 (0 open rows);
`.builder_queue/census_roadmap_rows.py`: TOTAL=77 OPEN=0 (rc 0); census gate
`tests/test_supply_census.py` 7 passed rc 0.
No eligible row; backlog exhausted; HOLD continues (tick ~122).
DEFECT-18(a) + DEFECT-17(d) remain landed (addendum 205 verification stands).

## Standing conjunction re-measured at 840c8c55

`SEED=101010 bash tools/arc_lega.sh`:

```
arc leg A :: seed=101010 head=840c8c55 rc=0 crashes=0 secs=91
  ====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 79.44s (0:01:19) ======
env: oom_kill_delta=0 journal_oom_kill_delta=0 mem_peak=39993659392 loadavg_after=1.44 1.36 1.41
```

crashes=0, oom_kill_delta=0, journal_oom_kill_delta=0. Artifacts:
`output/arc_lega_seed101010_840c8c55.txt` (+ json sidecar), committed this tick.
Shell gate `tests/test_glyph_interactive_shell.py` 8 passed rc 0.

## SE021 maildrop check (no re-emit this tick — write_id 70 content identical)

B-state verification, meta before surface (teleop rules 1/2):

- `geos_surface_meta` (80×25 @ origin): `write_id 70`, `writer
  builder-cron-af3e62239ce2/se021-maildrop-reemit`, `image_md5 3744eaa7…`,
  `age_seconds 1046.5`, tick=0 (machine not stepping — canvas is archaeology).
- Independent freshness: `stat /tmp/geos_observation/kernel_memory.npy` →
  mtime 2026-09-17 17:14:24 CDT, 65,664 bytes; md5 `3744eaa7bff2f27d9f9f42444b77e635`
  matches the sidecar's `image_md5` exactly.
- `geos_read_cell(700)`: word 700 = `0x3b00112a` at (30,24), region A —
  identical value to all prior holds; pure re-signal of the same ruling request,
  ~75th hold, no re-emit needed since the served image still carries write_id 70
  with the exact payload.

## State

SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per `.builder_queue/BRIEF_se021_reruling_delivery.md`.
No self-ratification; the standing maildrop (write_id 70) is the disclosed sole substrate action.
