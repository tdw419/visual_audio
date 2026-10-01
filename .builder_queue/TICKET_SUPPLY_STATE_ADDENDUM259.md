# TICKET SUPPLY STATE — Addendum 259 (HOLD tick ~124)

**When:** 2026-09-17 ~16:55 CDT · **HEAD at launch:** `627fce3f` · **Lane:** builder-cron-af3e62239ce2 · **Action:** HOLD

## Row sweep (rc=0)

`python3 .builder_queue/census_roadmap_rows.py` → rc=0, **TOTAL=77 OPEN=0**.
No eligible row; backlog exhausted; DEFECT-18(a) + DEFECT-17(d) already landed and
gated (`pytest tests/test_defect18_tick_regfile.py tests/test_defect17_x31_refusal.py -q`
→ **13 passed in 1.60s**, rc=0 this tick).

## Standing conjunction re-measured at 627fce3f

`SEED=987654321 tools/arc_lega.sh` → **rc=0, 373 passed / 1 skipped /
9 deselected / 2 xfailed, 79.26s**, oom_kill_delta=0, journal_oom_kill_delta=0,
mem_peak=39993659392 (~40 GB raw harness-reported number, consistent with the
addendum-256-era readings).
Artifact: `output/arc_lega_seed987654321_627fce3f.txt` (log kept on disk; only the
prior tick's log was committed per the one-artifact-per-tick pattern — this tick
commits the ticket only, log reproducible via the recorded seed).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop (write_id 69, unchanged this tick — no re-emit)

`geos_surface_meta`: `write_id 69`, writer
`builder-cron-af3e62239ce2/se021-maildrop-reemit`, written_at
2026-09-17T21:14:01Z, `image_md5 3744eaa7…`, `age_seconds 1896.4`, **tick=0**
(machine not stepping — canvas is archaeology per teleop rules 1/2; no B-state
conclusions drawn).

Independent freshness: `stat /tmp/geos_observation/kernel_memory.npy` → mtime
1789679641 (16:14:01 CDT), md5 `3744eaa7bff2f27d9f9f42444b77e635` — matches sidecar
exactly.

`geos_read_cell(700)`: word 700 = **0x3b00112a** at (x=30, y=24), region A —
identical value to all prior holds. No re-emit needed (content identical).

## Maildrop state (A-state, unchanged)

`.geos/maildrop/content/hermes.0001.ruling.md` md5 **ab846c188b2a…** reproduced
(~70th hold, no ack); `geos_mailbox.py verify --to all` → "all verified" (rc=0).
No new inbound; SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per
`BRIEF_se021_reruling_delivery.md`. No self-ratification.

## Environment

/home: 54G free (97% used). /var/crash: 3 files persist (not re-investigated).

## What this PASS does NOT prove

- tick=0 persists: no engine is stepping; word-700 residency is snapshot residency,
  not liveness.
- The arc-green is one seed at one HEAD (n=1 this tick); the conjunction is a
  repeated measurement, not a proof of future greens (DEFECT-22/24/25 history).
