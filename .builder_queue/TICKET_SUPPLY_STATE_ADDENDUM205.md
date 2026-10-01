# TICKET — Supply State Addendum 205 (builder cron af3e62239ce2)

**Run time:** 2026-09-17, tick ~83 of HOLD. **Trigger:** monitor diff head 108af1ba → be7a4c3e
(addendum 204's own landing).

## Findings this tick

1. **Roadmap scan:** `.builder_queue/scan_open_rows.py` rc=0, **0 open rows**. HOLD continues.
2. **Ruled items BOTH already landed** (verified, not from reports):
   - DEFECT-18 option (a) → `tests/test_defect18_tick_regfile.py`
   - DEFECT-17 option (d) → `tests/test_defect17_x31_refusal.py`
   - Combined run: **13 passed in 1.94s** (this tick, PATH=/usr/bin prefix).
   Standing prompt still lists both as open — it is stale; drop them from future pick lists.
3. **Standing conjunction re-measured at HEAD be7a4c3e:**
   `SEED=42 bash tools/arc_lega.sh` → rc=0, **373 passed / 1 skipped / 9 deselected / 2 xfailed,
   76.97s, crashes=0**, oom_kill_delta=0. Log `output/arc_lega_seed42_be7a4c3.txt`.
4. **SE021 maildrop re-emit verified (B-state):** geos_read_cell word 700 = `0x3b00112a`
   (region A, (30,24)) — byte-identical to write_id 20/21/22 verifications.
   geos_surface_meta: write_id 22, writer `unattributed`, image_md5 `3744eaa7bff2f27d9f9f42444b77e635`,
   age 558s. **Freshness caveat (teleop rule 2):** /tmp/geos_observation/kernel_memory.npy mtime
   2026-09-17 08:32:55 CDT; tick=0; maildrop content itself `.geos/maildrop/kernel_memory.npy`
   md5 `bf8e3bf5` unchanged, mtime 2026-09-16 03:00:24 CDT (~54h stale). No ack consumed.
5. **Dirty tree:** 238 tracked-dirty, 2655 total incl. untracked. Mostly sibling-lane WIP:
   pxc1 frames, virtio_pixel_rs (+123/−8 across 4 rust files), guest bridge files,
   `output/arc_legA_194844c_run4/5.txt`, `spoken.upic.json`. NOT touched this lane.
6. **/home:** 36G free (98%). Ollama models intact (no re-sweep needed per addendum 203/204).

## Action

HOLD continues. Committed as addendum 205 (this file + arc log).
