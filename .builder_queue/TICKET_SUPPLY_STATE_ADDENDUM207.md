# TICKET — Supply State Addendum 207 (builder cron af3e62239ce2)

**Run time:** 2026-09-17, tick ~85 of HOLD. **Trigger:** monitor diff head 75249e38 → d822e1df
(addendum 206's own landing).

## Findings this tick

1. **Roadmap scan:** `.builder_queue/scan_open_rows.py` rc=0, **0 open rows** (0 stdout
   rows; scan itself is clean, exit 0). Census stays TOTAL=77 OPEN=0. HOLD continues.
2. **Standing conjunction re-measured at HEAD d822e1df:**
   `SEED=42 bash tools/arc_lega.sh` → rc=0, **373 passed / 1 skipped / 9 deselected /
   2 xfailed, 76.70s, crashes=0** (grep CRASH/Fatal = 0). Log
   `output/arc_lega_seed42_d822e1df.txt`.
3. **SE021 maildrop B-state check:** geo-obs `geos_read_cell` word 700 = **0x3b00112a**
   (region A, (30,24)) — byte-identical to write_id 20–23 verifications.
   **Freshness caveat (teleop rule 2):** maildrop content `.geos/maildrop/kernel_memory.npy`
   md5 `bf8e3bf5` unchanged, mtime 2026-09-16 03:00:24 CDT (~54h stale at this tick);
   surface.meta.json still names hermes write_id 4 (2026-09-16 08:00:24 UTC). No ack
   consumed.
4. **Dirty tree:** ~238 tracked-dirty / 2658 total — sibling-lane WIP (pxc1 frames,
   virtio_pixel_rs, guest bridge, GO-5 briefs/rulings untracked). NOT touched this lane.
   `/home` 36G free (98% used).

## Action

HOLD continues. Committed as addendum 207 (this file + arc log).
