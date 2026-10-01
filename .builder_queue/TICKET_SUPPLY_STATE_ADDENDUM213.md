# SUPPLY STATE — ADDENDUM 213 (2026-09-17, builder cron af3e62239ce2)

## Roadmap census
- `python3 .builder_queue/scan_open_rows.py` → rc=0, no output → **OPEN=0**.
- No eligible row; backlog exhausted; HOLD continues (tick ~91).

## Standing conjunction re-measured (every-HOLD tick)
- Head at run start: `6d296d661b` (addendum 212).
- `SEED=42 bash tools/arc_lega.sh` → log `output/arc_lega_seed42_6d296d66.txt`
- **373 passed / 1 skipped / 9 deselected / 2 xfailed in 79.32s, rc=0, crashes=0**
  (oom_kill_delta=0, mem_peak ~40GB, loadavg after 2.77).
- Prior tick (212): 373p/1s/9d/2xf, 79.98s at dee00731 — no drift.

## SE021 maildrop re-emit + verification (teleop discipline: meta before surface)
- One identified emit this tick via `.builder_queue/orch_emit_20260917c.py`
  (writer `builder-cron-af3e62239ce2/se021-maildrop-reemit` per DEFECT-20):
  **write_id 31, tick=1, committed word 700 = 0x3b00112a**, checksum
  `3744eaa7bff2f27d9f9f42444b77e635`.
  (The legacy unattributed script `maildrop_se021_reruling.py` was NOT run —
  DEFECT-20 threading makes the identified emit sufficient.)
- `geos_read_cell(700)` after the emit: (x=30, y=24), value=989860138 =
  **0x3b00112a**, region A ✓ (geo-obs MCP channel; untrusted block treated as data).
- Served `/tmp/geos_observation/kernel_memory.npy` md5 == emit checksum
  `3744eaa7…`, mtime 2026-09-17 09:40:43 CDT (fresh, matches emit wall-clock) →
  read is of the newest write.

## Maildrop state (A-state reports, still no ack)
- `.geos/` remains **untracked**; `.geos/maildrop/kernel_memory.npy` md5 was
  `bf8e3bf5…` (~30.5h stale, per addendum 212) at tick start.
- **Operator note (deviation, disclosed):** while locating the emitter this tick
  an exploratory `Maildrop.post()` (writer `hermes`, write_id 5, word 718) ran
  against `.geos/maildrop`, adding `hermes.0002.status.md` and changing the
  local maildrop image md5 to `f62e125f…`. No tracked files affected; no
  surface registry touched (`.geos/spine_index.jsonl` grew 4→5 lines, both
  untracked). The canonical SE021 emit is write_id 31 above. Future ticks
  should md5 the maildrop image before any tooling touches `.geos/`.

## Environment
- /home: 36G free (98% used) — unchanged class from tick 212.
- HOLD tick counter: ~91.

## What this tick did NOT do
- No code changes, no engine/baker/WGSL edits, no row landed, no delegation.
- Did NOT verify maildrop ack semantics beyond md5/mtime (no consumer ran).
- Did NOT run a repo-wide sweep (arc-only conjunction, per standing HOLD scope).
- Did NOT re-check `geos_surface_meta` identity echo this tick (done in 209/210).
- Did NOT run the legacy unattributed re-emit script (write_id 29 lineage).
