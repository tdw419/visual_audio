# REPAIR_PENDING — GO-5 SCENARIO 11: PTR_TABLE collides with `.bss`; the address map is over-committed

Filed 2026-09-15 ~08:0x by builder cron af3e62239ce2. **This is a skeleton-sign-off /
address-map design change** — it needs a ruling before any core file is touched.
Delegate attempt #1 (claude, `output/claude/claude_impl_20260915_075749.log`, exit 3)
correctly stopped per-brief; orchestrator independently verified every claim below.

## Measured defect

- Gate RED: `output/go5_gate_run1_red.txt` — `test_go5_e2e_on_gpu[11]`: `g_clen
  Glyph 3 != GPU 7` (`tests/test_rv64i_to_glyph_xv6_nano.py:943`). 1 failed / 12 passed.
- Root cause (delegate diagnosis, orchestrator-confirmed by section dump):
  SCENARIO 11 `.bss = [0x1f00, 0x3000)` **overlaps `PTR_TABLE_BASE = 0x2000`**
  (`tools/rv64i_to_glyph.py:67`). Runtime `.bss` writes corrupt packed jump
  targets (delegate observed entry for `s11_t1e` = `0x3`, not its real PC), so
  `switch_to`'s resume jump lands in garbage → the Glyph twin (oracle) dies
  mid-script while the GPU twin (no table) runs on. SCENARIOs 8/9/10 `.bss`
  end at 0x1e00/0x15d8/0x1950 — all clear; only SCENARIO 11 collides.

## Why it is not a one-line raise (all measured this tick)

- DEFECT-17 goldens stay byte-identical under a raised base (probe:
  tiny fixtures carry no computed jumps) — **not** the blocker.
- BK-1's real C program is base-insensitive (no indirect calls) — not the blocker.
- No committed `.glyph` golden embeds a base literal — not the blocker.
- **The blocker is the GH-23 lane:** `tools/glyph_gpt/baker.py:5207` maps vpn
  0..10 = words [0, 2815) for libc programs, with `GH23_HEAP_BASE = 2560`
  (`tools/glyph_gpt/libc_runtime.py:45`) placed above the table *on purpose*
  (receipts dbg_gh23_cron60..64: heap at 2048 overwrote the table → jalr into
  kernel text). SCENARIO 11's `.bss` starts at **word 1984** — inside the GH-23
  window. So "table within the GH-23 mapping window" and "table clear of
  SCENARIO 11 `.bss`" are mutually exclusive. Also `sp = 0x4000` grows down
  (`tools/glyph_isa_v2.py:37-38` comment), bounding a raised table from above
  unless it goes past the MMIO block (byte 0x8000+).

## Options (cheapest first)

1. **Lane-local table override (additive):** give `transpile_rv32i_to_glyph` /
   `transpile_elf_to_glyph` an optional `ptr_table_base=None` param (default =
   module constant → zero behavior change for every existing caller); the
   xv6_nano harness (`_run_glyph`, and `build_pointer_table` seeding) passes a
   high base (e.g. 0x6000 bytes: above `.bss`+stack, below MMIO 0x8000, within
   the Glyph twin's 16384-word RAM; the GPU twin never touches the table).
   GH-23 keeps 0x2000 and every receipt stands. Touches ONLY
   `tools/rv64i_to_glyph.py` + the test harness — still a core file →
   worktree-isolation rule applies.
2. **Global raise + GH-23 window re-derivation:** move the constant, re-map
   vpn window + `GH23_HEAP_BASE`, re-run the dbg_gh23 receipt chain. Honest but
   expensive; re-derives landed receipts for a producer nobody emits yet.
3. **Shrink SCENARIO 11 `.bss` below 0x2000:** delegate measured it cannot be
   done by reordering globals (~4 KB genuinely needed: proc table + `g_grid`
   2048 B + `g_fb` + console; non-.bss already reaches 0x1f00). Only viable if
   `g_grid` itself shrinks — a fixture-behavior change needing Jericho's OK.

Ruling requested: pick an option (or rule a different map). Gate to re-run
after any fix: `/usr/bin/python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py
-q -p no:randomly` → 13 passed, all five clauses of
`.builder_queue/brief_go5_e2e_gpu_os.md` § Gate clause.

## Current tree state (left untouched)

`tests/fixtures/xv6_nano.c` + `tests/test_rv64i_to_glyph_xv6_nano.py` remain
dirty (the sibling's GO-5 composition work, last write 07:45:27). Not committed,
not reverted by the orchestrator — ownership belongs to the GO-5 lane.
