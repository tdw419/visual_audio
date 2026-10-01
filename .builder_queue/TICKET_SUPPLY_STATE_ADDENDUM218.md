# Ticket Supply State — Addendum 218 (2026-09-17, builder cron af3e62239ce2)

**Tick:** HOLD — 0 open roadmap rows (scan rc=0).

## Roadmap scan

- `python3 tools/supply_census.py` → **TOTAL=77 OPEN=0**, exit 0.
- DEFECT-18(a) + DEFECT-17(d) verified ALREADY LANDED (addendum 205); not re-picked.

## Standing conjunction re-measured (commit `465dbbdb`)

- `SEED=42 bash tools/arc_lega.sh` → log `output/arc_lega_seed42_465dbbdb.txt`
- **rc=0; 373 passed / 1 skipped / 9 deselected / 2 xfailed in 79.75s; crashes 0.**

## SE021 maildrop re-verification (geos channel)

- `geos_surface_meta`: age 418.1s (mature, machine not stepping — tick=0),
  write_id 35, writer `builder-cron-af3e62239ce2/se021-maildrop-reemit`,
  image_md5 `3744eaa7bff2f27d9f9f42444b77e635` — **equals the emit checksum**;
  backing file stat: mtime 2026-09-17 10:14:57 CDT, 65,664 bytes.
- `geos_read_cell(word=700)` → value `0x3b00112a`, region A, (x=30, y=24),
  marker none — exact match to standing expectation.
- No ack observed this tick (write_id unchanged at 35 since addendum 217).

## Host

- /home: 36G free (98% used, unchanged).

## What this tick did NOT verify

- No roadmap/backlog work attempted (0 open rows; nothing new eligible).
- Maildrop image content beyond word 700 not re-read; ack state inferred only
  from write_id stability, not from a channel-level ack read.
- No WGSL/GPU leg in this tick's conjunction beyond what arc_lega seed 42 runs.
