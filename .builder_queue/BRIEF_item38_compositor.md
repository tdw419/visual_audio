# BRIEF — item-38: Spatial window compositing & z-order elevation
# (overlapping tile damage clipping, top-window focus, drag repositioning)

## Spec pointer

QUEUE_STATE.json item-38 (id item-38, claim_order 38, blocks_on [item-37] —
landed at 3183e7f7). Watchdog commit e23fdc7e replenished supply. Consumes
the landed item-26..37 layers (glyph_process/glyph_containment/
glyph_stratum/glyph_input/glyph_shell). GlyphStratum itself REFUSES
overlapping placement (tools/glyph_stratum.py:126-129, a live guard) —
item-38 is therefore a NEW compositor module with overlap-permitting
placement semantics; the stratum guard is never touched.

## Scope (positive)

- NEW: tools/glyph_compositor.py — overlapping windows over the word-grid
  plane: place (overlap permitted, z assigned by arrival), raise, move
  (drag), damage-clip composite in ascending z order, hit_test.
- NEW: tests/test_item38_compositor.py — the gate below.
- NEW: .builder_queue/RECEIPT_item38_compositor.md
- Ledger: .builder_queue/PRODUCT_LANE_STATE.md (new dated section),
  .builder_queue/QUEUE_STATE.json (item-38 -> landed + commit).

## Scope (negative — must not touch)

- tools/glyph_stratum.py (its overlap refusal is a LIVE GUARD — item-38
  never weakens it; the compositor composes the same layers directly).
- tools/glyph_isa_v2.py and any engine/WGSL file (host-side Phase-2
  composition; N-leg byte-guard pins glyph_isa_v2.py to HEAD).
- Any landed item-25..37 tool module (pure-consumer contract).
- Protected assets (voicebook/, .rts/, rs_fixtures.json).

## Gate command

PYTHONPATH=. python3 -m pytest tests/test_item38_compositor.py -q
Expected exit 0; leg count stated in the gate clause.

## Gate clause

The gate is DISCRIMINATING (RED leg shown first): corrupting the composite
z-order sort (ascending -> descending) MUST make the z-order leg FAIL, and
suppressing the clipping application MUST make the damage leg FAIL — each
RED demonstrated as a failing leg on the mutated tree state before GREEN is
trusted. GREEN requires ALL of:

1. Overlapping placement: two windows placed at overlapping rects both
   spawn fenced (TILE_* armed, MODE_USER), z assigned by arrival order,
   no error raised (the compositor permits overlap BY CONTRACT).
2. Damage clipping, bottom window: with top window's tile words painted
   opaque, the composited canvas shows the TOP window's color at every
   contested cell and the BOTTOM window's color at cells the top does not
   cover. The bottom window's covered cells are NOT rendered (clipped).
3. Z-order elevation: raise(bottom) moves it to top; the composite flips
   which window owns the contested cells; hit_test at the contested cell
   returns the new top window's id both before and after.
4. Drag repositioning: move(top_window, new_origin) updates its WCB row,
   the composite shows its paint at the NEW rect and NOT at the old one,
   and the newly uncovered bottom-window cells render the bottom color.
   Move to an out-of-plane origin raises CompositorError (loud) and the
   WCB is unchanged after the refusal.
5. Fenced paint still governs: a guest that stores outside its own tile
   traps (E-K1, reaper) and is reaped EXIT_FAULT; the out-of-tile word is
   never written; the composite still renders the innocent window.
6. Focus: hit_test at an overlapping cell returns the topmost visible
   window; a hidden (visible=0) window drops out of hit_test AND of the
   composite (its cells reveal the window beneath).
7. Guest-computed paint from the fence (measured prerequisite, probe
   output/item38_probe_selftile.py): a USER-mode guest LOADs its own
   TILE_ROW/TILE_COL words, computes its origin word, and paints there —
   the composited canvas shows the paint at exactly the window origin.
8. Non-vacuity: compositing zero windows returns a (0,0,3) canvas;
   compositing with all windows hidden returns all-black at the bbox.

Leg count: 8 legs (C1..C8). GREEN = 8 passed, exit 0.

## Failure evidence (RED first)

Before landing: run the two RED mutations described above on the staged
tree (sort flip; clip suppression), paste the failing leg lines into the
receipt, revert the mutations, then run the full GREEN and paste its tail.
A GREEN without demonstrated REDs is not evidence.

## Failure protocol

Interfaces are LOCKED (GlyphProcessTable.spawn(tile=), arm_tile,
GlyphStratum consumed unmodified). If a locked signature blocks a leg,
file REPAIR_PENDING_item38_<topic>.md with 2-4 options cheapest-first and
pick the next eligible unit — never weaken a live guard to pass.

## Definition of done

RED tails + GREEN tail pasted in the receipt; ledger + QUEUE_STATE
updated; single commit on glyph-transpiler-autoloop containing ONLY the
in-scope files.
