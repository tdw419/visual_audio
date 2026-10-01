# BRIEF — item-39: Virtual terminal & PTY line discipline
# (ANSI/VT100 escape sequence parser, cursor movement, stdin/stdout IPC streams)

## Spec pointer

QUEUE_STATE.json item-39 (id item-39, claim_order 39, blocks_on [item-37,
item-38] — both landed: 3183e7f7, e9303ed2). Consumes the GO-3 MMIO input
ring (tools/glyph_isa_v2.py:120-140 — INPUT_LEN/CURSOR/DATA, the SYSCALL
0x02 source), the item-26 GlyphProcessTable (spawn/wait/output), and the
item-10 VGA font contract (tools/vga_font_8x16.py, glyph_text_console.py
precedent). Pure-consumer contract over landed layers only.

## Scope (positive)

- NEW: tools/glyph_vt.py — VT100Screen (escape parser + text grid +
  hardware cursor), GlyphVT (line discipline: canonical line assembly,
  0x7f erase, CR/NL handling, ring seeding), VTDisplay (band render +
  glyph-side font decode).
- NEW: tests/test_item39_vt.py — the gate below.
- NEW: .builder_queue/RECEIPT_item39_vt.md
- Ledger: .builder_queue/PRODUCT_LANE_STATE.md (dated section),
  .builder_queue/QUEUE_STATE.json (item-39 -> landed + commit).

## Scope (negative — must not touch)

- tools/glyph_isa_v2.py and any engine/WGSL file (no new syscall number;
  N-leg byte-guard pins glyph_isa_v2.py to HEAD).
- tools/glyph_process.py, glyph_compositor.py, any landed item-10..38
  tool module (pure-consumer contract).
- Protected assets (voicebook/, .rts/, rs_fixtures.json).

## Gate command

PYTHONPATH=. python3 -m pytest tests/test_item39_vt.py -q
Expected exit 0; 10 legs stated in the gate clause.

## Gate clause

GREEN requires ALL of:

1. V1 Escape basics: CUP (ESC[r;cH) + ED(2) position text on a cleared
   grid; the grid reads back the positioned string at exactly the
   addressed row/col.
2. V2 Cursor movement: CUU/CUD/CUF/CUB move the hardware cursor with
   clamping at grid edges (over-large moves pin to the edge, never
   IndexError); a printable after the move lands at the moved cell.
3. V3 Scroll: LF at the bottom row scrolls the grid up exactly one row
   (top line lost, cursor stays on the bottom row).
4. V4 Wrap: deferred (VT100) wrap — printing into the LAST column leaves
   the cursor there; the NEXT printable wraps to column 0 of the next
   row; printing at the bottom-right cell then wrapping scrolls.
5. V5 Line discipline (canonical): typed chars accumulate in the pending
   line; 0x7f erases the last CHARACTER (multi-byte-safe); CR commits;
   the seeded ring payload contains each keystroke byte exactly ONCE
   (no double-echo of committed lines) plus the NL terminator.
6. V6 Ring seeding: seed_bytes() writes INPUT_LEN + INPUT_DATA words of
   a fresh engine exactly; a second seed after the cursor advanced is
   REFUSED loud (VTRuntimeError); a payload over INPUT_DATA_CAP (64) is
   REFUSED loud (no silent truncation).
7. V7 Guest end-to-end (measured prerequisite, output/item39_probe_echo.py):
   a spawned guest reads its seeded line with SYSCALL 0x02, echoes it
   with SYSCALL 0x01, and the VT100-parsed screen shows the exact typed
   line; glyph-side decode of the rendered band recovers the same string
   (font-bitmap exact match — a host echo cannot pass this).
8. V8 ONLCR output translation: a guest PRT stream terminated with CR
   line endings scrolls the screen identically to NL endings (CR->NL
   translation on the output path).
9. N1 Engine byte-guard: glyph_isa_v2.py md5 == HEAD's blob (no engine
   change).
10. N2 Non-vacuity: a screen fed nothing decodes to empty lines; the
    line discipline actually consumed (mutating feed_key input changes
    the seeded payload) — a gate that cannot fail is decoration.

Leg count: 10 legs (V1..V8 + N1 + N2). GREEN = 10 passed, exit 0.

## Failure evidence (RED first)

Before landing: (RED 1) mutate the CSI row/col parse to swap params
(row<->col) — V1 MUST fail; (RED 2) mutate the commit path to re-append
the whole line to the echo stream (the double-echo defect this module
actually had during development) — V5 MUST fail. Both REDs demonstrated
as failing legs on the mutated tree before GREEN is trusted; mutations
reverted before GREEN. A GREEN without demonstrated REDs is not evidence.

## Failure protocol

Interfaces are LOCKED (GO-3 ring word addresses; SYSCALL 0x01/0x02/0x05
contracts; GlyphProcessTable.spawn signature; VGA font bitmaps). If a
locked contract blocks a leg, file REPAIR_PENDING_item39_<topic>.md with
2-4 options cheapest-first and pick the next eligible unit — never
weaken a live guard to pass.

## Definition of done

RED tails + GREEN tail pasted in the receipt; ledger + QUEUE_STATE
updated; single commit containing ONLY the in-scope files.
