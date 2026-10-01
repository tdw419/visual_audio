# TICKET — Supply State Addendum 206 (builder cron af3e62239ce2)

**Run time:** 2026-09-17, tick ~84 of HOLD. **Trigger:** monitor diff head be7a4c3e → 75249e38
(addendum 205's own landing).

## Findings this tick

1. **Roadmap scan:** `.builder_queue/scan_open_rows.py` rc=0, **0 open rows**; census
   `TOTAL=77 OPEN=0`. HOLD continues.
2. **Standing conjunction re-measured at HEAD 75249e38:**
   `SEED=42 bash tools/arc_lega.sh` → rc=0, **373 passed / 1 skipped / 9 deselected / 2 xfailed,
   76.86s, crashes=0**, oom_kill_delta=0, mem_peak ~813 MB. Log `output/arc_lega_seed42_75249e38.txt`.
3. **SE021 maildrop re-emit verified (B-state):** write_id **23**, tick=1, committed=True,
   checksum `3744eaa7bff2f27d9f9f42444b77e635`. geos_read_cell word 700 = `0x3b00112a`
   (region A, (30,24)) — byte-identical to write_id 20/21/22 verifications.
   **Freshness caveat (teleop rule 2):** maildrop content `.geos/maildrop/kernel_memory.npy`
   md5 `bf8e3bf5` unchanged, mtime 2026-09-16 03:00:24 CDT (~59h stale), surface.meta.json
   still shows the hermes write_id 4 (2026-09-16 08:00:24 UTC). No ack consumed.
4. **Dirty tree:** ~238 tracked-dirty, 2660 total incl. untracked — sibling-lane WIP
   (pxc1 frames, virtio_pixel_rs, guest bridge, GO-5 briefs/rulings untracked). NOT touched this lane.

## Action

HOLD continues. Committed as addendum 206 (this file + arc log).
