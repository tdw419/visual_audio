# RECEIPT — item-31: GPU-first spatial window coordinator (GlyphStratum)

**Builder:** af3e62239ce2 · **Date:** 2026-09-26 ~10:2x CDT
**Worktree commit:** f69cb328 (item31-coordinator, base bc435c29) · **Main cherry-pick:** 83a1fceb
**Claim basis:** Phase-1b claim-queue-first, lowest claim_order unblocked
(item-31, blocks_on=[item-29, item-30] cleared last two ticks).
**Spec:** QUEUE_STATE item-31 / watchdog draft `items_30_33_draft.json`:
"Spatial Program Coordinator managing autonomous process windows as
rectangular instruction/framebuffer tiles on infinite 2D plane without
host compositor dependency."

## What landed

- `tools/glyph_stratum.py` NEW (231 lines, host-side, zero syscalls,
  zero engine change): `GlyphStratum` — window coordinator over the
  W_MEM=32 word-grid plane (the engine tile predicate's own vocabulary,
  glyph_isa_v2.py:734-747), composing the landed layers:
  - item-26 `GlyphProcessTable` — the process model (spawn/wait/reap).
  - item-29 `spawn(tile=)` — the per-window E-K1 fence.
  - item-30 `load_program` — the digest-verified disk transport.
- API: `open_window(image, plane_origin, size)` and
  `open_window_from_disk(png, path, ...)` — claim a rect, spawn the
  window's task FENCED to it; `close_window` / `raise_window` /
  `set_visible` / `hit_test` / `run_all` / `composite` / `output`.
- WCB rows: the geos_pixel_v5 `wcb.rs` field vocabulary (STATE/X/Y/W/H/
  Z/VISIBLE) in word-grid coordinates — the host table and the GPU
  window system name the same things.
- `composite()`: the plane rendered from task RAM words
  (word & 0xFFFFFF -> RGB), ascending z-order, black background. The
  framebuffer of a window IS its tile words; the composite IS the plane.

## Two containment mechanisms, both load-bearing

1. **PLACEMENT CONTAINMENT (host):** overlapping rects refused LOUD
   (StratumError); any rect overlapping the isolation MMIO block rows
   [256,264) refused — a window there could rewrite its OWN fence words
   (TILE_* live at BOX_MMIO_BASE+0x160..0x16C, glyph_isa_v2.py:122-125).
   Zero-extent and out-of-plane rects refused; refused opens leave no
   window record.
2. **THE FENCE (engine, item-29 unchanged):** each window task runs
   MODE_USER with its own tile armed; a cross-window paint attempt traps
   through the engine's E-K1 path — store never lands, FAULT_ADDR/
   FAULT_PC record the evidence, task reaped EXIT_FAULT — while the
   innocent neighbor's paint and composite are intact (W5).

**Design finding:** placement containment makes the plane DISJOINT by
construction — open rects can never overlap, so hit-test degenerates to
rect lookup; contested cells arise only across hide/close state changes.
Stated in the gate, not hidden.

## Gate evidence (10 legs, tests/test_item31_stratum.py, force-added)

- **RED-first:** implementation stashed -> `ModuleNotFoundError:
  tools.glyph_stratum`, 1 collection error in 0.09s
  (output/item31_gate_run0_absent_red.txt).
- **GREEN:** 10 passed in 142.25s (worktree f69cb328, pre-commit);
  main re-gate at 83a1fceb: **28 passed in 284.22s** (item31 10 +
  item29 10 + item30 8 — the full prerequisite chain), exit 0.
- **Non-vacuity** (output/dbg_item31_nonvacuity_af3e.py, rc=0,
  output/item31_nonvacuity_run3.txt): three neuter probes, each flips
  its leg RED and restores:
  - N1 overlap refusal neutered (`if False and ...`) -> W2 RED
    (DID NOT RAISE StratumError — the duplicate rect would open).
  - N2 MMIO refusal neutered -> W3 RED (an MMIO-row window would open).
  - N3 tile= pass-through dropped (tile=None) -> W5 RED (the
    cross-window store would LAND; the fence is the spawn contract).
  - Probe run2's restore-leg false-RED was a probe-harness race (stale
    rc comparison), re-run clean (run3 PASS); source byte-identical
    after restore. The neutered-source leg rc=1 evidence is real in all
    runs (W2 "DID NOT RAISE" tail captured in run output).
- **Mid-fix REDs, disclosed — all three GATE bugs, the implementation
  refused correctly each time:** (1) W4 asserted every rect cell colored
  but the painter stores ONE word (fixed: painted cell + rest black);
  (2) W6 opened an overlapping window and the coordinator correctly
  refused — that IS W2's contract (fixed: disjoint rects, hit-test
  semantics restated under placement containment); (3) W7's blue
  painter targeted a word outside its own tile and the fence correctly
  reaped it EXIT_FAULT (fixed: each painter targets its OWN first tile
  word). Debug probes: output/dbg_item31_w4_af3e.py, dbg_item31_w7_af3e.py,
  dbg_item31_restore_af3e.py.

## Migration + guards

- R1: item-29 containment gate re-runs GREEN in this tree (subprocess).
- R2: item-30 loader gate re-runs GREEN in this tree (subprocess).
- N1: tools/glyph_isa_v2.py sha256-identical to HEAD (engine-byte guard).
- ZERO new syscall numbers; no engine file touched (pre-commit hook:
  no core/WGSL/transpiler files in the change).

## What this PASS does NOT prove (rule 6)

- **No GPU/WGSL execution** — host CPU engine, Phase-2 doctrine, same
  boundary as items 26-30. "GPU-first" names the architecture target
  (the WCB vocabulary IS the geos_pixel_v5 window system's layout); the
  landed artifact is the coordinator CONTRACT over the CPU oracle.
- **No live compositing** — tasks run to completion (cooperative,
  item-26 shape), then the composite is taken over reaped state. No
  incremental/damage-tracked rendering, no vsync, no frame pacing.
- **No input routing** — hit_test is a query; nothing dispatches events
  into windows (that is item-32's lane, now unblocked).
- **No shell UI** — no status bar, launcher, or monitors (item-33).
- **"Infinite plane" honesty** — sparse coordinates, any non-negative
  origin, but bounded by memory_words (16384 words = 512 grid rows, the
  engine's RAM contract); placement refuses beyond it.
- **Hit-test z-ordering between simultaneously-open windows is
  unreachable** under placement containment (disjoint rects); the
  topmost-visible logic exists but is only exercised across
  hide/close state transitions.
- No rates/latencies asserted anywhere — all asserts structural; rule-1
  floors do not attach; check_regime not implicated.

## Queue state

QUEUE_STATE.json item-31 -> landed (blocks_on consumed);
CURRENT_TICKET.json reconciled; next tick claims item-32 (spatial input
router & focus manager: BM905 event dispatch into the focused active
tile) per claim_order.
