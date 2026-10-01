# RECEIPT — BK-55 RESOLUTION CLOSED (verify-and-resolve, DECISION_RULES §3 class (a), BK-53/BK-57 precedent)

**Tick:** 2026-10-01 ~11:5x CDT, builder cron af3e62239ce2
**Tree at verification:** HEAD a17a91d3, git status clean for tools/ + tests/ (product code untouched)
**Class:** (a) verify-and-resolve — the row's own STATUS note scoped this tick's work: "re-run probe_wgsl_mmio_read/ek1 shapes at HEAD, write RESOLUTION tail". No posture decision, no engine change, no gate authored.

## What was verified (live at HEAD a17a91d3)

- `python3 .builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py` re-run (RTX 5090, wgpu):
  **results md5 `6dd9a46fbe606aa5004d059d1a4c7f83`** — byte-exact match to BK-77's landed
  post-fix citation (commit 51902aad, ledger 2026-10-01 ~05:1x entry). stdout md5
  `8042e6c76b486e0f3fcce13ac6982b03` across 2 runs = deterministic.
- Verdict lines: D1 **no hijack** (fault 32772 = arming word's word<<2, canary nowhere,
  E-K1 refuses the box-only door arm), D2 **no landing** (trapped-into-SUPER path does not
  exist; canary never lands), D3 **no door** (door-only vector arm refuses), C1 control
  green (kf=0 loud halt, no output), C2 control green (plain OOB ST refused, ram[999]==0).
- Closure mechanism: BK-77's `box_confirmed()` scope widening (OR'd into
  `bk50_config_write_refused`'s scope bail and the ever_user latch,
  tools/wgsl_glyph_isa_v2.py) — landed 51902aad 2026-10-01 05:22 with its own 7/7 gate
  (tests/test_bk77_twin_boxonly_lock.py) and 5f/2p RED-first at landing.

## Module md5 drift, explained (not a regression)

tools/wgsl_glyph_isa_v2.py today md5 `c1fe18f6...` vs BK-77 landing `f95d3263...`:
one commit between them touches this file — **BK-56** (bd76198c, config-block READ
posture, landed 08:1x today, its own 13/13 x2 gate). `git log 51902aad..HEAD --
tools/wgsl_glyph_isa_v2.py` returns exactly bd76198c. The BK-77 lock is upstream of
BK-56's read consults; probe results byte-identical to the post-fix citation confirms
the widening survived the co-landing.

## What this PASS does NOT prove

- No live-kernel twin workload exists — the chain is dead in the proven harness shapes,
  not under a real WGSL kernel image.
- The BK-77 design-judgment flag (ever_user latch keys on ANY fence armed, box OR tile)
  remains LANDED behavior backed by its L5 boot-phase leg, not resolved by a real-image
  survey — still flagged for the next twin-kernel landing.
- The oracle BK-53 chain was already pinned DEAD (md5 8a8bcb6f..., BK-60's tick); not re-run
  here — this receipt covers the TWIN side only, per the row's class-(a) scope note.

## Bookkeeping landed this tick

- systems/GLYPH_BACKLOG.md BK-55 STATUS: open -> RESOLUTION CLOSED (this receipt).
- PRODUCT_LANE_STATE.md ledger entry prepended, STATUS ACTIVE.
- ZERO product-code changes. Gate cost: 2 probe runs (~4-5 min total wall, GPU legs).

Rule-1 floors do not attach: structural verdict asserts only, no rates/latencies cited.
