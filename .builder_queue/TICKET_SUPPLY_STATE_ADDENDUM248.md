# TICKET SUPPLY STATE — Addendum 248 (HOLD)

**When:** 2026-09-17 ~15:18 CDT · **HEAD at launch:** `4750e37d` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/scan_open_rows.py`: rc=0, no open rows.
No eligible row; backlog exhausted; HOLD continues.
DEFECT-18(a) + DEFECT-17(d) remain already-landed (addendum 205 verification stands).

## Standing conjunction re-measured at 4750e37d

`SEED=64723 bash tools/arc_lega.sh`:

```
arc leg A :: seed=64723 head=4750e37d rc=0 crashes=0 secs=96
====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 83.90s (0:01:23) ======
env: oom_kill_delta=0 journal_oom_kill_delta=0 mem_peak=39993659392 loadavg_after=2.93 1.92 1.94
rc=0
```

Artifacts committed: `output/arc_lega_seed64723_4750e37d.txt` (+ json sidecar).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop re-emit (write_id 68)

```
emit rc: {'committed': True, 'word': 700, 'checksum': '3744eaa7bff2f27d9f9f42444b77e635',
          'tick': 1, 'write_id': 68, 'written_at': '2026-09-17T20:15:54.880547+00:00'}
```

- `geos_surface_meta`: `write_id 68`, `image_md5 3744eaa7…` == emit checksum,
  `age_seconds 12.9`, tick=0 (machine not stepping — canvas is archaeology per
  teleop rule 1/2). NOTE: the meta `writer` field reports `unattributed` this tick —
  the re-emit was run via the bare `.builder_queue/maildrop_se021_reruling.py`
  entrypoint (no writer tag in the intent), a deviation from the addendum 243
  emitter-tagged shape; content and checksum are byte-identical, pure re-signal.
- Independent freshness: `stat /tmp/geos_observation/kernel_memory.npy` → mtime
  2026-09-17 15:15:54.879 CDT, 65,664 bytes — matches `written_at` to the millisecond.
- `geos_read_cell(700)`: word 700 = `0x3b00112a` at (x=30, y=24), region A — identical
  value to all 67 prior holds; write_id monotonic over 67 (67→68).

Maildrop content unchanged since addendum 213 (md5 `ab846c18`, mtime 09-16 03:00);
this is a pure re-signal of the same ruling request.

## State

SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per `BRIEF_se021_reruling_delivery.md`.
No self-ratification; the maildrop emit is the disclosed sole substrate action.

## Process note (self-caught, no damage)

This tick the orchestrator accidentally executed a stale one-shot
(`.builder_queue/append_d24_ledger.py`, a leftover the D22-LEDGER-1 commit `259fab83`
supposed to have removed), which rewrote the DEFECT-22 ticket's `next_step` with stale
leg-#24 text (0/24) over the working-tree value (0/59). Caught within the same tick by
diff-vs-HEAD: only `next_step` differed; `.builder_queue/d22_ledger.py recompute`
derived the identical series_state (54/54 consecutive worker-scope green, legs_run 54)
from the ledger objects, and `next_step` was restored verbatim from HEAD —
verified `content equal: True` (semantic JSON equality against `git show HEAD:…`).
Zero lasting damage; ticket history untouched. Lesson filed: one-shot append scripts
in `.builder_queue/` are untracked-but-present landmines; the one-append-path rule
(D22-LEDGER-1) exists for exactly this — do not execute any `append_*.py` one-shot.
