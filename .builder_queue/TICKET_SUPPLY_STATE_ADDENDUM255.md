# TICKET SUPPLY STATE — Addendum 255 (HOLD tick ~120)

**When:** 2026-09-17 ~16:20 CDT · **HEAD at launch:** `91929381` · **Lane:** builder-cron-af3e62239ce2 · **Action:** HOLD

## Row sweep (rc=0)

`python3 .builder_queue/scan_open_rows.py` → rc=0, no open rows.
`python3 tools/supply_census.py` → **TOTAL=77 OPEN=0** (agrees; instrument gate
`tests/test_supply_census.py` 7 passed + `tests/test_supply_census_instrument2.py`).
No eligible row; backlog exhausted; DEFECT-18(a) + DEFECT-17(d) already landed and
gated (`pytest tests/test_defect18_tick_regfile.py tests/test_defect17_x31_refusal.py -q`
→ **13 passed, 1.57s** this tick).

## Standing conjunction re-measured at 91929381

`SEED=1745773251 bash tools/arc_lega.sh` → **rc=0, 373 passed / 1 skipped /
9 deselected / 2 xfailed, 80.81s**, crashes=0, oom_kill_delta=0,
journal_oom_kill_delta=0, mem_peak ~40.0 GB. Artifacts committed:
`output/arc_lega_seed1745773251_91929381.txt` (+ json sidecar).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop re-emit (write_id 69, emitter-tagged)

```
emit rc: {'committed': True, 'word': 700, 'checksum': '3744eaa7bff2f27d9f9f42444b77e635',
          'tick': 1, 'write_id': 69, 'writer': 'builder-cron-af3e62239ce2/se021-maildrop-reemit',
          'written_at': '2026-09-17T21:14:01.540865+00:00'}
```

Independently re-verified via geos tools (B-state, meta before surface):

- `geos_surface_meta`: `write_id 69`, writer matches, `image_md5 3744eaa7…` ==
  emit checksum, `age_seconds 3.3`, **tick=0** (machine not stepping — canvas is
  archaeology per teleop rules 1/2; no B-state conclusions drawn).
- Independent freshness: `stat /tmp/geos_observation/kernel_memory.npy` → mtime
  2026-09-17 16:14:01 CDT, 65,664 bytes, md5 `3744eaa7…` — matches `written_at`.
- `geos_read_cell(700)`: word 700 = **0x3b00112a** at (x=30, y=24), region A —
  identical value to all prior holds; write_id monotonic over 68 (68→69).

## Maildrop state (A-state, unchanged)

`.geos/maildrop/content/hermes.0001.ruling.md` md5 **ab846c18** reproduced
(~66th hold, no ack); content dir still 5 files; `geos_mailbox.py verify --to all`
→ "all verified" (rc=0). No new inbound; SE021 reruling delivery remains
**BLOCKED-ON-JERICHO** per `BRIEF_se021_reruling_delivery.md`. No self-ratification;
the emitter re-signal is the disclosed sole substrate action.

## Environment

/home: 54G free (97% used). /var/crash: 3 files persist (not re-investigated).
