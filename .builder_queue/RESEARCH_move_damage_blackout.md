# RESEARCH — move() damage: a dragged reaped window composites 100% black

**Tick:** builder cron af3e62239ce2, 2026-09-26 ~23:1x CDT (Phase 1c research
tick — CLAIM QUEUE empty at HEAD dd3cdd26, mailbox rule clean, R1.4
re-verified LANDED, not open).
**Question:** is item-38's disclosed move() word-anchor ("a moved window
composites its RAM at the NEW grid addresses, so unrepainted cells go
black" — PRODUCT_LANE_STATE.md, item-38 section; C4 asserts it openly) an
edge case, or a product defect for the desktop the claim queue has been
building since item-31?
**Method (what was measured, all runs on HEAD dd3cdd26, tracked tree
clean before this tick's untracked-only additions):** probe
`.builder_queue/probe_move_damage_af3e.py` (this tick, untracked) drives
the landed `GlyphCompositor` (tools/glyph_compositor.py) through two
scenarios, composite() read back before and after a reaped-window
`move(wid, (20,10))`:
- (a) a task that paints ONLY its origin word (0xFF0000 at word 320,
  the C4 shape);
- (b) a task that paints its ENTIRE 3×5 tile from inside its own fence
  (USER-mode guest LDs TILE_ROW/TILE_COL from the MMIO block
  (glyph_isa_v2.py:122-125, BOX_MMIO_BASE=0x8000), walks r in 0..3 ×
  c in 0..5, stores 0xFF0000 at origin + r*32 + c — the item-37
  desktop-suite idiom). Exit status verified 0, no fence trap,
  pre-move composite lit 15/15 cells.

## Findings (numbers)

- (a) pre-move: canvas[10][0] = (255,0,0), lit cells 1. Post-move: lit
  cells **0** — the single paint is read from NEW grid word 650
  (= 20*32+10), which holds 0. Composite loses every lit pixel.
- (b) pre-move: lit cells 15/15, exit 0, no fault (the fence held; the
  first draft of this probe that painted outside the tile was correctly
  reaped EXIT_FAULT, fault_addr 0x14000 — the containment works).
  Post-move: lit cells **0 of 15 — 100% of the dragged window's pixels
  go black**. Verified non-fence cause: the task RAM still holds all 15
  red words at the OLD addresses; composite() reads
  `cpu.memory[rr * W_MEM + cc]` with the CURRENT (moved) rect
  (tools/glyph_compositor.py:213), so every read lands on a never-
  painted word.
- Blast radius: every landed consumer of move() — the C4 gate leg
  (tests/test_item38_compositor.py::test_c4_move_drag asserts the black
  cell as EXPECTED behavior) and item-41's GlyphTaskManager, whose
  task-manager tile is itself repositionable only via this path. Any
  user drag of a completed window destroys its image. item-38's gate
  codified the defect as contract (RED 1/RED 2 prove the clipping and
  z-sort, not the anchor).
- Adjacent regression this tick: item-38+39+40+41 gates 38 passed
  (0.16s) — the defect is latent behind a passing gate, which is why it
  survived five landings.

## Candidate item (backlog format)

**BK-36 — Snapshot-at-reap: make move() composite what the guest
actually painted.**
Cheapest-first fix options:
1. (recommended) At reap time (`run_all()`/`_run_task` completion hook
   in the compositor, tools/glyph_compositor.py:179-185), capture the
   tile pixels from the ORIGIN rect into the WCB (a (h,w,3) uint8 array
   or the 15-120 word list); `composite()` renders the snapshot when
   the window is reaped, RAM only while live. Blast radius: compositor
   module + its gate + item-41 legs that assert composite colors after
   reaping. No engine, no process-table change; guests still cannot
   store outside their fence.
2. Render moved windows from the OLD rect offset (translate reads by
   the origin delta): no snapshot memory, but the "moved" image then
   silently disagrees with the RAM view at the new addresses — a
   second word-anchor to document forever.
3. Status-quo + doc: forbid move() for windows whose tile is not fully
   painted (needs a paint-detection pass — more code than option 1).
Gate spec: `tests/test_bk36_move_snapshot.py` — L1 full-tile painter
moved → post-move composite lit 15/15 with the SAME colors at the new
rect (RED today: 0/15, per this probe's scenario b); L2 origin-painter
moved → the 1 paint follows (RED today); L3 pre-reap move still refused
loud; L4 live (un-reaped) windows still render from RAM (snapshot
inactive); L5 non-vacuity — snapshot neutered → L1 RED; L6 family —
item-38 + item-41 gates green. Prereqs: none (all landed).
Source: this receipt + tools/glyph_compositor.py:213.

## Honesty

- This receipt PROPOSES; it lands no engine/compositor code (the probe
  is untracked under .builder_queue/ and does not import wgsl).
- Numbers above are structural cell counts and exit codes from one
  process (this probe, 2 runs after the fix, deterministic); NO rate,
  latency, or cost claim is made — rule-1 floors do not attach. The
  probe's own development produced two RED-by-fence runs
  (dbg_fill_tile_af3e.py, exit 1 fault_addr 0x14000) that were PROBE
  bugs (3-operand ADD where the ISA is 2-operand, glyph_isa_v2.py:436-
  438), not product defects — noted because the assembler's silent
  arity-ignoring (extra operand dropped, no error) made the bug look
  like a fence failure; that silence is itself a candidate follow-up
  (assemble-time arity check), folded here rather than filed twice.
- R1.4 (WGSL convergence) re-verified LANDED this tick by direct run:
  probe_r13_wgsl_fleet.py exit 0, MATCH, halt @458, results
  {714:6, 728:12, 748:20, 763:30}; receipt
  .builder_queue/RECEIPT_R14_wgsl_convergence.md; conformance WGSL legs
  present (tests/test_box_abi_conformance.py:249+). The "halts@153 /
  fleet words 0" state in the standing directive text is stale.
- NOT verified: no WGSL/GPU execution involved in the move() finding
  (CPU oracle path only); interaction with item-39 VT repaint or
  item-40 toast re-stack after a drag untested.
