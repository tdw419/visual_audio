# TICKET_SUPPLY_STATE — Addendum 287 (builder cron af3e62239ce2, 2026-09-18 ~11:0x CDT)

**Head:** b8300d7a (go6l2-mtime64 erratum, landed by another lane since addendum 286's
73d3d637). Scan scripts live in `.builder_queue/`, not `tools/` (286's erratum stands).

## Supply scan: 0 open rows

Roadmap `systems/GLYPH_SELF_HOSTING_ROADMAP.md`: no status cell matches ⏳/⚠️/DRAFT
without a `→ ✅` closure marker. Backlog `systems/GLYPH_BACKLOG.md`: same, 0 open.
No `BLOCKED-ON-DESIGN` rows. Queue holds `REPAIR_PENDING`/`RULING`/maildrop tickets
only — no implementable item. Standing DEFECT-18(a)/17(d) rulings verified LANDED on
disk (tests/test_defect18_tick_regfile.py + tests/test_defect17_x31_refusal.py exist;
addendum 280 correction stands). HOLD cadence continues.

## Standing conjunction (re-measured this tick at b8300d7a)

- **Arc leg A** (tools/arc_lega.sh, SEED=1452923546): **373 passed / 1 skipped / 9
  deselected / 2 xfailed in 81.93s, rc 0**; oom_kill_delta=0, mem_peak 23.77GB
  (lifetime-max cgroup counter — variance note from addendum 273 stands).
  Log `output/arc_lega_seed1452923546_b8300d7a.txt`.
- **DEFECT-18a+17d defense set** (same 7 files as 286): `tests/test_defect18_tick_regfile.py
  test_gh16_preemption.py tests/test_bk1_argv.py tests/test_bk2_wgsl_syscall_parity.py
  tests/test_gh26_resident.py tests/test_gh26_glass_box.py tests/test_defect17_x31_refusal.py`
  → **43 passed in 6.04s, rc 0** under `/usr/bin/python3`.

## SE021 maildrop

`.builder_queue/maildrop_se021_reruling.py` md5 **a0936dc5ebcdcf5c5aea185e379dd038**
unchanged. **BLOCKED-ON-JERICHO** — hold, no re-emit (content identical per standing rule).

## Substrate (B-state; teleop discipline: meta first)

- `geos_surface_meta`: **tick=0** (sidecar_tick=1), **write_id=73**, writer
  "unattributed", image_md5 **3744eaa7bff2f27d9f9f42444b77e635**, written_at
  2026-09-18T08:08:02Z, **age 28258s (~7.85h)** — machine NOT stepping.
- Independent: `stat` mtime 2026-09-18 03:08:02 CDT, size 65664, md5 **3744eaa7** —
  matches sidecar exactly (**5th consecutive tick unchanged**: addenda 279→287).
- `geos_read_cell(700)` → **0x3b00112a** at (30,24) region A — RESIDENT, byte-exact
  vs addenda 279–286. No write made (governance).
- Monitor delta this tick was the other lane's b8300d7a erratum commit, not loop activity.

## Next

No actionable supply. Next tick: rescan, re-measure conjunction at then-HEAD, hold.
