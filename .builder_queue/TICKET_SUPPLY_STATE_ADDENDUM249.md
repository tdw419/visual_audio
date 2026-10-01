# TICKET — Supply State, Addendum 249

**Run:** 2026-09-17 (~20:25 UTC), orchestrator cron af3e62239ce2
**Head at run:** `48798d2a` (addendum 248)
**Scan:** `python3 .builder_queue/scan_open_rows.py` → rc=0, no output = 0 open rows (third consecutive confirm)

## Status: HOLD (unchanged)

Standing rule (`RULING_lane_supply_20260912.md` § Standing): loop rescans, finds
nothing eligible, reports. Must not invent scope or poach another lane.

## Standing conjunction re-measured at `48798d2a`

- **Arc leg A** GREEN: `SEED=39881 bash tools/arc_lega.sh` → **373 passed, 1 skipped,
  9 deselected, 2 xfailed, rc=0, 79.99s**, 0 crashes, 0 oom-kills.
  Log `output/arc_lega_seed39881_48798d2a.txt`, sidecar `.json`.
- **Substrate:** tick=0 (machine not stepping), image md5 `3744eaa7bff2f27d9f9f42444b77e635`
  unchanged, write_id=68, `age_seconds≈470` at meta read. Word 700 = `0x3b00112a`
  re-verified RESIDENT via fresh `geos_read_cell` → region A (30,24). No re-emit needed.
- **SE021 maildrop:** `.builder_queue/maildrop_se021_reruling.py` unchanged vs git HEAD
  (blob md5 `a0936dc5…`, no local modification). **MD5 DISCREPANCY FLAG:** addenda 247/248
  recorded the maildrop md5 as `ab846c18…`, but the file at both HEAD and on disk is
  `a0936dc5ebcdcf5c5aea185e379dd038`. The `ab846c18` figure was not reproduced this run —
  it likely referenced a different (delivered/erased) copy or was a transcription error in
  the earlier addenda. No ack from Jericho; escalation stands on canvas word 700 + queue
  series. Not resolved by this run; noting rather than silently repeating.
- **/var/crash:** 3 non-fixture reports persist (git, udisksd, pytest) — L6c red, operator seat.
- **Disk:** /home 54G free (97% used) — unchanged.

## What this PASS does NOT prove

- The scan's rc=0 was not independently re-derived row-by-row this run (scan script is
  itself in the dirty tracked set); it matched the last two runs' result.
- Substrate word 700 residency is a fresh read of a tick=0 snapshot — it proves content
  persistence in the published image, not machine liveness.
- Maildrop md5 history (ab846c18) unresolved — see discrepancy flag above.

## Next

Unchanged: awaiting a ruling from Jericho (SE021 re-ruling or lane re-point), or new
backlog/roadmap supply. No eligible work this tick.
