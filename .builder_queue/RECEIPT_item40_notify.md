# RECEIPT — item-40: Desktop notification daemon & system tray ABI

**Status: LANDED** (builder af3e62239ce2, glyph-teleoperation lane,
2026-09-26 ~22:1x CDT)

## Provenance at claim

- HEAD bef36c77 (item-39 pin commit); item-38 landed at e9303ed2 —
  item-40's only block_on was green. Tracked-dirty = 0 at claim.
- Mailbox rule clean: `find .builder_queue -name 'RULING_*.md' -newermt
  @1790475341` returned EMPTY (no RULING newer than HEAD's commit time).
- Watchdog supplied only a title; the brief was authored by this builder
  per the skeleton-handoff contract BEFORE implementation:
  `.builder_queue/BRIEF_item40_notify.md` — `tools/check_brief.py`
  PASS (exit 0) + `--self-test` exit 0 (validator proven able to fail).

## LANDED (this commit, on this exact tree)

- **tools/glyph_notify.py NEW** — GlyphNotifyDaemon over the item-38
  GlyphCompositor (pure consumer):
  - Toast ABI: submit()/held() bounded queue (QUEUE_CAP=8, loud
    refusals that leave the queue byte-identical), dispatch() placing
    each toast as a REAL compositor window (stacked TOAST_PITCH=2 rows
    apart, arrival-order z → later toasts sit above earlier-placed
    content in contested cells), expire_top() retiring the OLDEST toast
    (stack's top row) via set_visible(False) — the compositor's
    sanctioned removal, its records being append-only — and re-stacking
    survivors upward with compositor move().
  - Agent alert contract: register_agent(wid, request_cell) refuses
    request cells OUTSIDE the window's own tile (agents emit from
    inside their fence, never across it); the agent GUEST computes
    encode_request() = magic<<24 | level<<16 | payload and STs it
    inside its tile; harvest() reads post-run kernel-class (item-34
    commit_guest_ring precedent), CONSUMES the word (zeroes the slot —
    a second harvest enqueues nothing), quarantines bad magic/level
    LOUD (NotifyError) with the slot still consumed.
  - Tray ABI: open_tray() places the tray window (real fenced tile);
    register_applet/set_applet_state maintain the applet table and
    repaint via a FRESH tray task at the same locked rect (item-33
    refresh_bar respawn idiom adapted to the compositor's contract);
    registering past TRAY_SLOTS=4 refuses loud with the record
    unchanged.
  - Guest-side paint: toast tasks read their own TILE_ROW/TILE_COL
    (item-38 C7 self-tile pattern, addresses imported from
    glyph_isa_v2 — never hardcoded), compute their origin word, and
    ST payload fg cells + bg through the E-K1 fence. Tray tasks
    copy-through seeded cell words (zero words skipped).
- **tests/test_item40_notify.py NEW** — the gate (force-added past
  .gitignore's test_*.py rule).
- **.builder_queue/PRODUCT_LANE_STATE.md / QUEUE_STATE.json /
  CURRENT_TICKET.json** — ledger updates (item-40 → landed).
- **.builder_queue/BRIEF_item40_notify.md** — the pre-implementation
  brief (check_brief PASS).

## Gate: 10 legs, tails pasted literally

- Gate command: `PYTHONPATH=. python3 -m pytest
  tests/test_item40_notify.py -q`
- **GREEN (final, this tree): `10 passed in 0.08s`, EXIT=0**
  (output/item40_green_final.txt)
- **RED 1 (toast z pinned to 0, below content): rc=1, T1 FAILED —
  "1 failed, 9 deselected in 0.06s"** — the gate discriminates
  (output/item40_red1_red2.txt; driver output/item40_red_driver.py;
  module restored byte-exact, md5 d5cd0ed7b478e73954597d044ac7142f
  before/after asserted by the driver itself).
- **RED 2 (harvest consumption removed): rc=1, T2 FAILED —
  "1 failed, 9 deselected in 0.06s"** — double-enqueue is caught;
  consumption is load-bearing, not decorative.
- Adjacent regression on this tree: item-38 gate + item-39 gate →
  **18 passed** (output/item40_regress_adjacent.txt).

## Defects the gate caught during development (fixed in-scope)

1. `expire_top()` originally popped the NEWEST toast (bottom-most row)
   but re-stacked windows BELOW the expired row — a predicate that can
   never fire (T3 caught it: survivors' rows unchanged). Semantics
   fixed: retire the OLDEST toast (top row); survivors below slide up
   one pitch.
2. `_repaint_tray()` called a nonexistent `GlyphCompositor.close_window`
   — the compositor has NO removal (records append-only); switched to
   the sanctioned set_visible(False) (T5 caught it, AttributeError).
3. register_applet called _repaint_tray before any tray existed (T6
   caught it) — repaint now gated on the tray window being open.
4. First-draft T3 legs asserted moved-paint at the NEW rows — that
   contradicts the LANDED item-38 C4 doctrine (move() is word-anchored;
   a moved window composites its RAM at the NEW grid addresses so
   unrepainted cells go black). Legs corrected to assert the RECORD
   collapse + honest black-composite consequence; the landed guard was
   never weakened, the TEST was aligned to the landed contract.

## Honesty / what this PASS does NOT prove

- No GPU/WGSL execution — host CPU-oracle engine throughout (N1 pins
  glyph_isa_v2.py md5 5a672d7d5a94a7b20f927f554b8a90c0 = HEAD's blob).
- "Asynchronous" = the agent's alert is queued at its OWN run and
  harvested by the daemon afterwards (cooperative commit-between-runs,
  item-26/34 doctrine). NO mid-run preemption, no interrupts.
- Harvest is kernel-class HOST reading of guest-produced RAM words —
  the agent emits from inside its own fence (T2 guest-computed; T8
  proves an out-of-tile ST is reaped EXIT_FAULT and harvests nothing).
- Toasts are solid color words — no text/fonts on the plane (text
  lives in the PRT/console lanes).
- No rates/latencies asserted anywhere (rule-1 floors do not attach).
- expire-top re-stacking moves window records; per landed item-38 C4
  semantics the composite at the OLD rows goes black until a repaint —
  asserted openly by T3, not hidden.

## Queue state

- QUEUE_STATE.json: item-40 → landed (this commit).
- Next tick: item-41 (dynamic process lifecycle & spatial task manager,
  claim_order 41, blocks_on item-38+item-39 — both landed) per
  Phase-1b, unless a newer RULING intervenes.
