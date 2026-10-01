# TICKET SUPPLY STATE — Addendum 238 (HOLD tick ~114)

**When:** 2026-09-17 ~13:06 CDT · **HEAD at launch:** `f9a2d2a0` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/census_roadmap_rows.py`: **TOTAL=77 OPEN=0** (rc=0).
No eligible row; backlog exhausted; HOLD continues (tick ~114).

## Standing conjunction re-measured at f9a2d2a0

`SEED=42 bash tools/arc_lega.sh`:

```
arc leg A :: seed=42 head=f9a2d2a0 rc=0 crashes=0 secs=95
  Using --randomly-seed=42
  ====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 82.21s (0:01:22) ======
  log=output/arc_lega_seed42_f9a2d2a0.txt sidecar=output/arc_lega_seed42_f9a2d2a0.json
env: oom_kill_delta=0 journal_oom_kill_delta=0 mem_peak=1009446912 loadavg_after=1.76 1.55 1.93
```

Artifacts committed: `output/arc_lega_seed42_f9a2d2a0.txt` (+ json sidecar).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop re-emit (write_id 54, emitter-tagged)

Byte-identical re-signal of word 700 = `0x3b00112a` (cksum 0x3b = (0x11+0x2a)&0xFF |
op 0x11 | payload 0x2a) via `.builder_queue/orch_emit_20260917c.py` (arg-guarded,
writer `builder-cron-af3e62239ce2/se021-maildrop-reemit` per DEFECT-20):
**write_id 54, tick=1, committed 2026-09-17T18:04:01Z, checksum `3744eaa7…` —
monotonic over 53.**

Teleop-discipline verification (meta before surface, untrusted block treated as data):
- `geos_read_cell(word=700)` post-emit: value 989860138 = **0x3b00112a**, (x=30, y=24),
  region A ✓.
- `geos_surface_meta` echo: write_id **54**, writer matches, age 25.8s post-emit,
  image_md5 `3744eaa7bff2f27d9f9f42444b77e635` == emit checksum ✓ (served image is
  the newest write; no intervening writer).
- `stat` of `/tmp/geos_observation/kernel_memory.npy`: mtime 13:04:01 CDT, 65664 B —
  matches emit wall-clock.

## Maildrop state (A-state, unchanged)

`.geos/maildrop/` md5 `f62e125f…` — unchanged since addendum 213's disclosed
`hermes.0002` post (this tick's emit went through the emitter path, not the local
maildrop image). Content dir still 5 files; `geos_mailbox.py verify --to all` →
"all verified" (rc=0). No new inbound; SE021 reruling delivery remains
**BLOCKED-ON-JERICHO** per `BRIEF_se021_reruling_delivery.md`.

## Environment

/home: 68G free (97% used). HOLD tick counter: ~114.
