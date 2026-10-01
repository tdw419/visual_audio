# RECEIPT — item-38: Spatial window compositing & z-order elevation (GlyphCompositor)

**Claim queue:** item-38 (claim_order 38, blocks_on item-37 — landed 3183e7f7;
watchdog replenish commit e23fdc7e). Brief: BRIEF_item38_compositor.md.
**Builder:** af3e62239ce2 (Glyph OS Event Chain cron), 2026-09-26 ~21:0x CDT.
**Tree:** glyph-transpiler-autoloop, HEAD at claim e23fdc7e (verified clean of
tracked modifications; mailbox rule clean — newest RULING_* mtime epoch
1790127513 < HEAD epoch).

## What landed

- tools/glyph_compositor.py — GlyphCompositor: OVERLAP-PERMITTING sibling of
  GlyphStratum (whose live overlap-refusal guard at tools/glyph_stratum.py:126
  is untouched, not weakened). Windows placed on overlapping rects, each task
  still FENCED to its own rect via spawn(tile=...) (item-29 arm). z assigned
  by arrival; raise_window() elevation; move() drag of reaped windows (the
  task's landed fence is never re-armed — move relocates the record+composite
  placement only, refuses running windows and out-of-plane origins loud);
  composite() damage clipping: DESCENDING-z paint with an occupancy mask so
  the top window claims its damage region first and lower windows are clipped
  out of contested cells; hit_test() top-window focus.
- tests/test_item38_compositor.py — the 8-leg gate (C1..C8).
- .builder_queue/BRIEF_item38_compositor.md — the authored brief (the
  watchdog supplied only the QUEUE_STATE title; brief written by this builder
  per the handoff contract before implementation).
- output/item38_probe_selftile.py — measured design prerequisite.

## Measured prerequisite (design-deciding)

Question: can a USER-mode fenced guest compute paint FROM its own fence?
Answer: YES — LD of TILE_ROW/TILE_COL words out of the isolation MMIO block
is not store-fenced; the guest computes origin=row*W_MEM+col via
LDI/MUL/ADD and STs there (probe output/item38_probe_selftile.py, tile
(10,4,2,4): "exit: 0", "word at origin (10*32+4=324): 0xff00"). This makes
C7 a real guest-computed-paint leg, not a host-painted fake. Probe finding
cost: the assembler's LD is register-indirect only (LD r10 <addr> raises
OverflowError at glyph_isa_v2.py:547; LD r10 r<reg> is the working form).

## Gate evidence (all run on THIS tree, PYTHONPATH=.)

RED 1 — z-sort flipped ascending (composite pass order): FAILED as required
(output/item38_red1.txt): "FAILED tests/...::test_c2_damage_clip_top_wins",
"FAILED tests/...::test_c3_raise_flips_ownership" — 2 failed, 6 passed.
The mutated tree lets the bottom window overpaint the top; C2's
green-origin assert is exactly what catches it.

RED 2 — clip suppressed (occupied skip removed): FAILED as required
(output/item38_red2.txt): same two legs fail ("assert (np.uint8(0),...,
np.uint8(0)) == (0, 255, 0)") — without the skip the lower window's unpainted
(black) damage region overpaints the top window's green. Both mutations were
reverted before GREEN; the landed mechanism is the reverted one.

Honesty note recorded: an EARLIER mechanism shape (ascending-z + occupancy
mask) had a DECORATIVE clip — RED 2 did not discriminate against it (the
ascending overwrite order alone produced the correct pixels). The mechanism
was restructured to descending-z-claims-first BEFORE the trusted RED/GREEN
pair so the clip is load-bearing. The pre-restructure runs are preserved as
output/item38_green_pre.txt (1 failed on the then-wrong C3/C4 expectations)
and output/item38_green_pre2.txt (8 passed under the decorative mechanism —
superseded, untrusted as final evidence).

GREEN — final mechanism (output/item38_green_final.txt):
"8 passed in 0.07s", EXIT=0. Engine byte-guard N1 equivalent verified:
md5sum tools/glyph_isa_v2.py = 5a672d7d5a94a7b20f927f554b8a90c0, identical
to `git show HEAD:tools/glyph_isa_v2.py | md5sum`. git diff HEAD (tracked):
empty — only the new in-scope files are added.

Legs (8): C1 overlap-permitted placement, both tasks fenced (TILE_* armed,
MODE_USER), z by arrival; C2 damage clipping (top wins contested; bottom
shows only uncovered cells); C3 elevation flips hit_test AND composite
ownership (contested cell renders the elevated window's RAM — green
DISAPPEARS from the contested cell: the clip is pixel-observable);
C4 move(): reaped-only (running refused loud), WCB updated, old-rect paint
gone, out-of-plane refused with record unchanged; moved window composites
its task's RAM at the NEW grid address (word 670, unpainted -> black — paint
is WORD-anchored, not frame-anchored, and the receipt states this plainly);
C5 fence still governs overlap: rogue top storing into the bottom's word 320
traps (EXIT_FAULT), store never lands, innocent window composites; C6 focus/
visibility: hidden window drops out of hit_test AND the composite bbox
shrinks (13x5), cells reveal beneath; C7 guest-computed paint from its own
fence words (the probe pattern, placed at (40,2): word 322 -> 0x00FF00,
canvas (40,2) green); C8 non-vacuity: zero windows -> (0,0,3); all-hidden ->
(0,0,3); hidden-window composite renders black everywhere unpainted.

## What the PASS does NOT prove

- No GPU/WGSL execution: host-side Phase-2 composition over the CPU-oracle
  engine (same boundary as items 26-37); no engine change, no new syscall.
- No incremental/dirty-rect damage tracking: composite() recomputes full
  occupancy per call; "damage" is per-composite clipping.
- move() is a record/composite move of a REAPED window, not live dragging
  of a running guest (delivery stays cooperative, item-26 shape).
- move() does not preserve on-screen paint: paint is anchored to plane
  words; a moved window shows its RAM at the new rect's addresses (the C4
  assert documents this: the green word 355 stays at word 355 in RAM but is
  no longer composited anywhere after the move — recorded as the honest
  semantic of this item's move(), a candidate refinement, not hidden).
- No rates/latencies asserted (rule-1 floors do not attach).
- GlyphStratum and all item-25..37 modules unmodified (pure consumer).

## Queue/ledger

QUEUE_STATE.json item-38 -> landed (this commit). Next tick: item-39
(claim_order 39) per Phase-1b.
