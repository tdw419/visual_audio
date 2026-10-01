# TICKET SUPPLY STATE — Addendum 247 (HOLD tick ~123)

**When:** 2026-09-17 ~17:45 CDT · **HEAD at launch:** `98dfaac3` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/scan_open_rows.py`: no output, rc 0 (0 open rows);
`tests/test_supply_census.py` 7 passed rc 0. No eligible row; backlog exhausted;
HOLD continues (tick ~123). DEFECT-18(a) + DEFECT-17(d) remain landed (addendum 205).

## Standing conjunction re-measured at 98dfaac3

`SEED=101010 bash tools/arc_lega.sh`:

```
arc leg A :: seed=101010 head=98dfaac3 rc=0 crashes=0 secs=94
  ====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 80.73s (0:01:20) ======
```

crashes=0. Artifacts: `output/arc_lega_seed101010_98dfaac3.txt`, committed this tick.
Shell gate `tests/test_glyph_interactive_shell.py` 8 passed rc 0.

## SE021 maildrop re-emit (write_id 71) — content identical to write_id 70

B-state verification, meta before surface (teleop rules 1/2):

- Pre-emit `geos_surface_meta`: `write_id 70`, `writer
  builder-cron-af3e62239ce2/se021-maildrop-reemit`, `image_md5 3744eaa7…`,
  `age_seconds 1373.8`, tick=0 (machine not stepping — canvas is archaeology).
- Independent freshness pre-emit: `stat /tmp/geos_observation/kernel_memory.npy` →
  mtime 2026-09-17 17:14:24 CDT, 65,664 bytes; md5 `3744eaa7bff2f27d9f9f42444b77e635`
  matched the sidecar's `image_md5` exactly. Word 700 re-read via fresh
  `geos_read_cell`: `0x3b00112a` at (30,24), region A — payload intact.
- Re-emit executed (`.builder_queue/orch_emit_20260917c.py`, arg-guarded, same
  disclosed sole action): `write_id 71`, committed=True, image md5 unchanged
  `3744eaa7…` (pure re-signal, no content change).
- Post-emit `geos_surface_meta`: `write_id 71`, `age_seconds 6.5`, same md5;
  post-emit `geos_read_cell(700)` = `0x3b00112a` re-verified through the transport.
- ~76th hold, still no ack.

## Parallel-lane observation (reported, not acted on)

Tracked-dirty count ~2,716 with another lane active (monitor `DIRTY_ACTIVE`).
Re-runs of `output/arc_legA_194844c_run4/5.txt` today show 332 passed / 1 skipped
(run5) at 08:16–08:18 CDT — a different, larger set than this lane's 373-test
seeded conjunction; ticket `.builder_queue/DEFECT-22_arc_legA_instability.json` and
`.builder_queue/scan_open_rows.py` carry whitespace-only local modifications
(ticket parses OK, 202 keys). Left uncommitted — not this lane's writes.

## State

SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per
`.builder_queue/BRIEF_se021_reruling_delivery.md`. No self-ratification; the
standing maildrop (write_id 71, content identical to 70) is the disclosed sole
substrate action.
