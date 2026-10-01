# TICKET SUPPLY STATE — Addendum 257 (HOLD tick ~122)

**When:** 2026-09-17 ~16:40 CDT · **HEAD at launch:** `7e70de3d` · **Lane:** builder-cron-af3e62239ce2 · **Action:** HOLD

## Row sweep (rc=0)

`python3 .builder_queue/scan_open_rows.py` → rc=0, no open rows.
`python3 tools/supply_census.py` → **TOTAL=77 OPEN=0**.
No eligible row; backlog exhausted; DEFECT-18(a) + DEFECT-17(d) already landed and
gated (`pytest tests/test_defect18_tick_regfile.py tests/test_defect17_x31_refusal.py
-q -p no:randomly` → **13 passed, 1.92s**, rc=0 this tick).

## Standing conjunction re-measured at 7e70de3d

`SEED=555786001 bash tools/arc_lega.sh` → **rc=0, 373 passed / 1 skipped /
9 deselected / 2 xfailed, 81.60s**, oom_kill_delta=0, journal_oom_kill_delta=0,
mem_peak=818012160 (~0.82 GB — note: the prior addendum recorded ~40 GB; both are
raw harness-reported numbers, cause of the difference not investigated this tick).
Artifact committed: `output/arc_lega_seed555786001_7e70de3d.txt` (tail carries
`ARC_RC=0`).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop (write_id 69, unchanged this tick — no re-emit)

Prior tick's emitter-tagged re-emit (write_id 69, writer
`builder-cron-af3e62239ce2/se021-maildrop-reemit`, written_at
2026-09-17T21:14:01Z) is still the newest write. Re-verified fresh (B-state,
meta before surface):

- `geos_surface_meta`: `write_id 69`, writer matches, `image_md5 3744eaa7…`,
  `age_seconds 895.8`, **tick=0** (machine not stepping — canvas is archaeology
  per teleop rules 1/2; no B-state conclusions drawn).
- Independent freshness: `stat /tmp/geos_observation/kernel_memory.npy` → mtime
  2026-09-17 16:14:01 CDT, 65,664 bytes, md5 `3744eaa7bff2f27d9f9f42444b77e635`
  — matches sidecar exactly.
- `geos_read_cell(700)`: word 700 = **0x3b00112a** at (x=30, y=24), region A —
  identical value to all prior holds. No re-emit needed (content identical).

## Maildrop state (A-state, unchanged)

`.geos/maildrop/content/hermes.0001.ruling.md` md5 **ab846c188b2a…** reproduced
(~68th hold, no ack); content dir still 5 files (newest other item:
`hermes.0002.status.md`, Sep 17 09:39); `geos_mailbox.py verify --to all` →
"all verified" (rc=0). No new inbound; SE021 reruling delivery remains
**BLOCKED-ON-JERICHO** per `BRIEF_se021_reruling_delivery.md`. No self-ratification.

## Environment

/home: 54G free (97% used). /var/crash: 3 files persist (not re-investigated).

## What this tick does NOT prove

- No GPU leg, no substrate write, no new gate — a pure re-measurement hold tick.
- The arc ran tree+dirty (sibling-lane WIP present in `git status`, 2,705 entries);
  the verdict describes that snapshot, not a clean HEAD.
- `tick=0` throughout: the machine is still not stepping; all B-state reads are
  of our own emitted snapshot, not a living substrate.
- The mem_peak discrepancy vs addendum 256 is unexplained (both self-reported).
