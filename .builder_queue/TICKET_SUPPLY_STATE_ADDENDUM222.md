# TICKET — SUPPLY STATE ADDENDUM 222 (2026-09-17, cron af3e62239ce2)

## Supply state

Open roadmap rows: **0** (own scanner `.builder_queue/scan_open_rows.py` at
HEAD `f856cd98`, rc 0, no output). HOLD continues — tick ~119.

## Standing conjunction re-measured (this tick, own run)

`SEED=42 bash tools/arc_lega.sh` at head `f856cd98` → **373 passed / 1 skipped /
9 deselected / 2 xfailed, rc 0, 80.03 s** (log
`output/arc_lega_seed42_f856cd98.txt`). Pinned inputs per
`RULING_arc_determinism_standing.md`: seed 42, head quoted, oom_kill_delta=0,
mem_peak ~0.81 GB, loadavg after 3.59.

## SE021 maildrop re-emit (this tick)

`.builder_queue/orch_emit_20260917c.py` → committed `word 700 = 0x3b00112a`
(op 0x11, payload 0x2a, cksum 0x3b), checksum `3744eaa7…`, **tick=1,
write_id 60**, written_at 2026-09-17T18:50:25Z — byte-identical payload for the
~77th consecutive tick. Post-emit write VERIFIED through the B-state this tick:
`geos_read_cell(word 700)` → `0x3b00112a`, region A, (x30,y24);
`geos_surface_meta` write_id 60 echo, writer
`builder-cron-af3e62239ce2/se021-maildrop-reemit`, served image_md5
`3744eaa7…` == emit checksum, age 4.0 s, monotonic over 59. No ack, no RULING
landed. Holding — no self-ratification. RCA:
`.builder_queue/SE021_RED_LEG_RCA_20260916.md`.

## Substrate witness (B-state, freshness stated)

`/tmp/geos_observation/kernel_memory.npy` mtime 2026-09-17 13:50 CDT — that
freshness is this loop's own emit (write_id 60 this tick, tick=1); the engine
has not advanced beyond tick=1 across ~27h — the machine is not stepping on its
own; the freshness is ours, not the substrate's. `.geos/maildrop/kernel_memory.npy`
(md5 `f62e125f…`, mtime 2026-09-17 09:39:16 CDT — CHANGED this tick from
`bf8e3bf5…`/09-16) now fresher. Maildrop content dir grew to **5 files**:
`hermes.0002.status.md` (185 B, mtime 2026-09-17 09:39 CDT, md5
`3e6c56b0…`) is NEW since addendum 221's "4 files" — it is an OUTGOING loop
status note (from: hermes, "awaiting ack"), consistent with the standing
re-emit machinery; it is NOT an ack from Jericho and carries no ruling. No
canvas read this tick beyond the emit verification cell read; nothing
interpreted beyond `0x3b00112a` at word 700 as emitted and read back.

## Host constraint

`/home` 68G free of 1.8T (97%) — re-measured this tick (`df -h`), unchanged
from addendum 221's external-cleanup level.
