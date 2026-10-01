# TICKET SUPPLY STATE — Addendum 236 (HOLD tick ~112)

**When:** 2026-09-17 ~12:47 CDT · **HEAD at launch:** `1d793172` · **Lane:** builder-cron-af3e62239ce2

## Row sweep

`.builder_queue/scan_open_rows.py` (v4, status-cell rfind): **0 open rows** (rc=0, no output).
Known cosmetic note unchanged: the scanner's working-tree edit is relative-path-only vs
`git show HEAD:.builder_queue/scan_open_rows.py` (same output); not committed, per prior addenda.

## Standing conjunction re-measured at 1d793172

`SEED=42 bash tools/arc_lega.sh`:

```
arc leg A :: seed=42 head=1d793172 rc=0 crashes=0 secs=96
  Using --randomly-seed=42
  ====== 373 passed, 1 skipped, 9 deselected, 2 xfailed in 82.12s (0:01:22) ======
  log=output/arc_lega_seed42_1d793172.txt sidecar=output/arc_lega_seed42_1d793172.json
env: oom_kill_delta=0 journal_oom_kill_delta=0 mem_peak=1017974784 loadavg_after=1.85 2.22 2.65
```

Artifacts committed: `output/arc_lega_seed42_1d793172.txt` (+ json sidecar).
BRIEF_se021_reruling_delivery.md landing conjunction remains **green at HEAD**.

## SE021 maildrop re-emit (write_id 52, emitter-tagged)

The maildrop's disclosed sole action is word 700 = `0x3b00112a` (cksum 0x3b = (0x11+0x2a)&0xFF |
op 0x11 | payload 0x2a). Re-emitted byte-identical, arg-guarded, via
`.builder_queue/orch_emit_20260917c.py` — the loop keeps signaling only that the request stands;
no self-ratification of the SE021 option pick.

- Meta-before-surface: pre-emit `geos_surface_meta` age 505.0s, write_id 51 (235's emit),
  writer `builder-cron-af3e62239ce2/se021-maildrop-reemit`, served md5 `3744eaa7…`.
- Freshness verified independently: `stat`/md5 of `/tmp/geos_observation/kernel_memory.npy`
  → `3744eaa7bff2f27d9f9f42444b77e635` == served image_md5 ✓.
- Emit result: committed=True, write_id 52, tick=1, writer tag echoed,
  written_at 2026-09-17T17:46:53Z.
- Post-emit `geos_read_cell(word=700)` → `0x3b00112a`, region A, (30,24) — matches the
  2026-09-11 marker-verified xy2d identity mapping ('>' (27,17)→750, '@' (29,17)→754,
  'X' (31,24)→703); read against the pre-emit-verified image, re-read post-emit.
- Post-emit `geos_surface_meta`: age 8.2s, serving write_id 52 (monotonic over 51), writer
  tag carried, image_md5 `3744eaa7…` == emit checksum — identity echo holds.
- tick=0 in meta vs tick=1 in the emit sidecar: machine not stepping — read is archaeology
  of our own committed write, no B-state residency claim (teleop discipline).

**Instrument note (new this tick):** `geos_verify_sentinels` on the newest committed image
returns ok=false — all five reference pixels (words 0 / 16383 / 5461 / 10922 / 8192) read 0.
Interpretation: the reference sentinels were never stamped on this `kernel_memory.npy` image
(it is a memory dump, not a sentinel-stamped demo canvas); this is a property of the artifact,
not a corruption signal — word 700's value AND region-A (30,24) decode both match the
marker-verified mapping, which independently pins orientation for the word we actually read.
Recorded so a future tick doesn't mistake this for an orientation failure or silently skip it.

## Maildrop content

Unchanged since 221: `.geos/maildrop/content/` holds the same 5 files; `hermes.0001.ruling.md`
md5 `ab846c18` — still no ack. `hermes.0002.status.md` mtime 09:39 today is the loop's own
outbound status (content unchanged since 221's snapshot: HOLD, 0 open rows, awaiting ack).
Mailbox CLI not re-probed this tick (carried instrument note: '(no messages)').

## Blocks (unchanged)

SE021 reruling delivery remains **BLOCKED-ON-JERICHO** per `.builder_queue/BRIEF_se021_reruling_delivery.md`
(option pick (a)/(b)+/(c)/GH-25 in-channel or as RULING_SE021_*.md). Jericho's other pending
picks unchanged: DEFECT-23 option 2, DEFECT-29, D22 series stop-condition, supply renewal.

## Host

`/home`: 68G free (df -h, was 47G at 235) — pressure eased.

## What this PASS does NOT prove

- Conjunction green proves the pinned deterministic arc at seed 42 only; GPU/network legs run
  non-blocking and are not exercised here.
- The re-emit proves the write landed and echoes identity; it does NOT advance SE021 — that
  needs Jericho's option pick.
- Sentinel check ok=false is uninterpreted beyond the artifact-property note above; no
  sentinel-stamped canvas is available in this channel to prove orientation independently.
