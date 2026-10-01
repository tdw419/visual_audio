# TICKET SUPPLY STATE — ADDENDUM 204 (builder cron af3e62239ce2)

Run time: 2026-09-17 08:32 local. Head `108af1ba` (addendum 203). Branch
`glyph-transpiler-autoloop`.

## Census (this tick)

`python3 .builder_queue/scan_open_rows.py` → no output, **rc=0**: **0 open
rows.** Holding per the standing rule — no backlog promotion available, no
ruling outstanding that the loop may implement unilaterally.

Standing conjunction re-measured at this head (SEED=42, pinned per
addendum 70):

```
SEED=42 bash tools/arc_lega.sh   # head 108af1ba, output/arc_lega_seed42_108af1ba.txt
373 passed, 1 skipped, 9 deselected, 2 xfailed — rc=0, crashes=0, 76.66 s
oom_kill_delta=0, mem_peak=39993659392, loadavg_after 1.48
```

## SE021 maildrop re-emit (this tick)

`.builder_queue/maildrop_se021_reruling.py` → committed **word 700 =
0x3b00112a, tick=1, write_id 22**, written_at 2026-09-17T13:32:55Z —
byte-identical payload, **82nd consecutive tick**. Post-emit write
VERIFIED through the B-state: `geos_read_cell(word 700)` → `0x3b00112a`,
region A, (x30,y24). No ack, no RULING landed. Holding — no
self-ratification. RCA: `.builder_queue/SE021_RED_LEG_RCA_20260916.md`.

Backing maildrop image `.geos/maildrop/kernel_memory.npy` md5 `bf8e3bf5`
mtime 1789545624 — **the consumer-side snapshot stays ~53.9 h stale**; the
engine is not stepping, so freshness is only by this loop's own emit.

## Disk pressure (watch item, post trash-incident)

`/home`: 98 % used, **36 G free** (eased from 5.9 G at the 07:57 incident
window; unchanged from addendum 203). `ollama_models_moved` (48 G) intact,
no re-sweep observed.

## Not verified this tick

- WGSL GPU legs (as every prior tick on this conjunction).
- No SE021 ack/ruling: maildrop content unchanged; Jericho's word is still
  the only thing that can resolve it.
