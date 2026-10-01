# BRIEF — item-40: Desktop notification daemon & system tray ABI
# (asynchronous agent toast alerts, status bar reactive applets)

## Spec pointer

QUEUE_STATE.json item-40 (id item-40, claim_order 40, blocks_on
[item-38] — landed e9303ed2, HEAD bef36c77 pins it). Consumes ONLY
landed layers: item-38 GlyphCompositor (tools/glyph_compositor.py —
overlap-permitted placement, arrival-order z, reaped-window move()),
item-31 GlyphStratum fence semantics (spawn(tile=...) containment,
E-K1 + reaper), the item-33 guest-paint idiom (seeded words + guest
CMP3/JLT paint loop, glyph_shell.py:_bar_program shape), and the
cooperative commit-between-runs delivery model (item-26/34 doctrine).
Kernel-class host harvest of guest-produced words has direct precedent:
item-34 commit_guest_ring, item-37 wire-word->percept translation.
Pure consumer — NO new syscall number, no engine change, no edits to
any landed tool module.

## Scope (positive)

- NEW: tools/glyph_notify.py — GlyphNotifyDaemon over GlyphCompositor:
  submit()/harvest() toast queue (cap bounded, loud refusals),
  dispatch() placing toast windows as compositor tiles (stacked, above
  content), expire_top() with stack collapse via reaped-window move(),
  register_agent() + request-word harvest contract (magic | level |
  payload word in the agent's OWN tile), open_tray() + tray applet ABI
  (register_applet/set_applet_state, respawning tray task repaint).
- NEW: tests/test_item40_notify.py — the gate below.
- NEW: .builder_queue/RECEIPT_item40_notify.md
- Ledger: .builder_queue/PRODUCT_LANE_STATE.md (dated section),
  .builder_queue/QUEUE_STATE.json (item-40 -> landed + commit),
  .builder_queue/CURRENT_TICKET.json (reconciled).

## Scope (negative — must not touch)

- tools/glyph_isa_v2.py and any engine/WGSL file (no new syscall;
  N1 byte-guard pins glyph_isa_v2.py md5 = 5a672d7d5a94a7b20f927f554b8a90c0).
- tools/glyph_compositor.py, glyph_stratum.py, glyph_process.py,
  glyph_shell.py, glyph_vt.py, glyph_channel.py — every landed
  item-10..39 module (pure-consumer contract; the compositor's
  contract is USED, never overridden).
- Protected assets (voicebook/, .rts/, rs_fixtures.json).

## Gate command

PYTHONPATH=. python3 -m pytest tests/test_item40_notify.py -q
Expected exit 0; 10 legs stated in the gate clause.

## Gate clause

GREEN requires ALL of:

1. T1 Toast above content: a toast dispatched onto a plane that already
   holds a content window with an OVERLAPPING rect composites the
   TOAST's pixels in every contested cell (arrival-order z), and
   hit_test at a contested cell returns the toast wid.
2. T2 Guest-emitted alert end-to-end: a spawned agent guest COMPUTES a
   well-formed request word (magic<<24 | level<<16 | payload) and STs
   it inside its own tile; harvest() accepts it, zeroes the request
   slot (consumed), dispatch() places a toast whose painted fill count
   equals the guest's payload (guest-side fenced paint, not a host
   paint). A second harvest() of the same tile enqueues NOTHING
   (consumption is real).
3. T3 Stack + collapse: three dispatched toasts occupy three distinct
   non-overlapping stack rows; expire_top() closes the top toast AND
   re-stacks the survivors upward via compositor move() (every
   survivor's rect origin shifts by exactly one toast pitch; composite
   shows the moved paint; the closed window is gone from windows()).
4. T4 Level contract: distinct levels map to distinct toast color words
   (level color table); a submit with an out-of-range level is REFUSED
   loud (NotifyError) and enqueues nothing; a harvested word with a bad
   magic is REFUSED loud (quarantine) and the slot is consumed.
5. T5 Tray applet ABI + reactivity: open_tray() places the tray window;
   register_applet(slot,color) + set_applet_state paints the slot cell
   guest-side; a SECOND set_applet_state with a different state repaints
   the same slot with the NEW color (the reactive applet leg — respawn
   repaint, cooperative model).
6. T6 Tray capacity: registering more applets than TRAY_SLOTS is
   REFUSED loud and the tray record is unchanged (no partial slot).
7. T7 Queue bound: submitting past QUEUE_CAP refuses loud (NotifyError),
   and the first QUEUE_CAP submissions are all still queued and
   dispatchable (a refusal never damages held state).
8. T8 Fence still governs: an agent guest ordered to ST its request
   word OUTSIDE its own tile is reaped EXIT_FAULT (E-K1 + reaper), the
   daemon harvests nothing, and previously dispatched toasts still
   composite.
9. N1 Engine byte-guard: glyph_isa_v2.py md5 ==
   5a672d7d5a94a7b20f927f554b8a90c0 (no engine change).
10. N2 Non-vacuity: zero submissions -> dispatch() places no window and
    the composite equals the content-only baseline; harvest() on a
    registered agent with a zero request word returns no toast (a gate
    that cannot fail is decoration).

Leg count: 10 legs (T1..T8 + N1 + N2). GREEN = 10 passed, exit 0.

## Failure evidence (RED first)

Before landing: (RED 1) pin toast z to 0 (below content) — T1 MUST
fail; (RED 2) make harvest() NOT consume the request slot (skip the
zeroing) — T2 MUST fail (double-enqueue). Both REDs demonstrated as
failing legs on the mutated tree before GREEN is trusted; mutations
reverted before GREEN (diff-confirmed). A GREEN without demonstrated
REDs is not evidence.

## Failure protocol

Interfaces are LOCKED: compositor place/move/close semantics, stratum
fence + reaper contract, assembler mnemonics and the CMP3/JLT paint
idiom, engine MMIO addresses. If a locked contract blocks a leg, file
REPAIR_PENDING_item40_<topic>.md with 2-4 options cheapest-first and
pick the next eligible unit — never weaken a live guard to pass.

## Definition of done

RED tails + GREEN tail pasted literally in the receipt; ledger +
QUEUE_STATE + CURRENT_TICKET updated; single commit containing ONLY
the in-scope files (force-add tests/ past .gitignore).
