# RECEIPT — item-39: Virtual terminal & PTY line discipline

**Builder:** af3e62239ce2 (Glyph OS event-chain cron, 2m cadence)
**Claimed:** 2026-09-26 ~21:1x CDT at HEAD e9303ed2 (item-38 ledger commit),
tracked-dirty = 0; mailbox rule clean (newest RULING_* mtime epoch
1790127513 < HEAD epoch 1790473744 — re-checked at claim time).
**Item:** QUEUE_STATE.json item-39 (claim_order 39; blocks_on item-37 +
item-38, both landed). Watchdog-supplied title; brief authored by this
builder per the skeleton-handoff contract (BRIEF_item39_vt.md) BEFORE
implementation.

## What landed

- `tools/glyph_vt.py` — three pieces:
  - `VT100Screen`: VT100-family escape parser over a text grid with a
    hardware cursor. CUP/CUU/CUD/CUF/CUB/ED(2)/EL(0), deferred (VT100)
    wrap at the last column, scroll-on-LF-at-bottom, BS/HT/BEL, SGR
    accepted-and-ignored. Cursor clamped on every CSI; wrap-pending is
    cleared by every cursor-moving event (ESC/CR/LF/BS/HT/CSI).
  - `GlyphVT`: the line discipline. Master side: `feed_key()` (canonical
    line assembly, 0x7f erases the last CHARACTER — multibyte-safe),
    `seed_bytes()` writes the GO-3 input ring
    (INPUT_LEN/CURSOR/DATA, tools/glyph_isa_v2.py:120-140). Slave side:
    the guest reads with SYSCALL 0x02. Output path: `write()` applies
    ONLCR (guest NL -> CR+NL; guest CR untouched — a CR-only guest
    overprints its line, true VT100, documented) into the parser.
  - `VTDisplay`: band render + glyph-side decode by exact VGA font
    bitmap match (item-10 contract reuse).
- `tests/test_item39_vt.py` — 10 legs V1..V8 + N1 + N2.
- `.builder_queue/BRIEF_item39_vt.md` (authored pre-implementation).

## Gate evidence (tails pasted literally)

RED 1 (CSI CUP row/col params swapped), `output/item39_red1.txt`:

    FAILED tests/test_item39_vt.py::test_v1_cup_ed_positioning - assert (4, 2) ==...
    FAILED tests/test_item39_vt.py::test_v2_cursor_moves_clamped - assert (0, 1) ...
    2 failed, 8 passed in 0.09s
    RED1 exit=1

RED 2 (commit path re-appends the whole line — the double-echo defect the
module actually had during development), `output/item39_red2.txt`:

    FAILED tests/test_item39_vt.py::test_v5_line_discipline_single_echo - Asserti...
    FAILED tests/test_item39_vt.py::test_v6_seed_guards_loud - AssertionError: as...
    FAILED tests/test_item39_vt.py::test_v7_guest_echo_end_to_end - AssertionErro...
    3 failed, 7 passed in 0.08s
    RED2 exit=1

GREEN (clean tree, mutations reverted, `output/item39_green_final.txt`):

    ..........                                                               [100%]
    10 passed in 0.09s
    EXIT=0

Adjacent-lane regression (item-38 gate re-run on this tree): 8 passed.
Mutations reverted before GREEN (`diff /tmp/glyph_vt_clean.py
tools/glyph_vt.py` clean — confirmed in the RED-2 transcript).

## Defects found and fixed during this item (all pre-GREEN, in-scope)

1. Control constants were ints (`CR = 0x0D`) compared against str — every
   control char silently dropped. Fixed to str constants.
2. CSI moved the cursor without clamping until end-of-feed — IndexError
   on over-large CUU. Fixed: per-CSI clamp.
3. Eager wrap after the last column scrolled early at bottom-right.
   Fixed to VT100 deferred wrap (`_wrap_pending`), the xterm/VTE rule.
4. Backspace popped a byte, not a character — could split a UTF-8
   sequence; rewritten over `_pending_chars`.
5. Commit path double-echoed the line (pending bytes were already in the
   echo stream AND the committed line was appended again). Fixed: commit
   appends only the 0x0A terminator. RED 2 exists because this defect
   was real.
6. `pending_bytes()` double-counted the pending tail (already in the
   echo stream). Fixed to `len(self._echo_pending)`.

## What the PASS does NOT prove

- No GPU/WGSL execution — host CPU oracle only.
- "PTY" here is the GO-3 ring line discipline (master = host seeding,
  slave = guest 0x02 reads), NOT a POSIX kernel pty pair; no signals,
  no job control, no interrupt-driven mid-run input (cooperative
  run-to-completion delivery — seeding happens before the run).
- VT100 coverage is the documented subset; xterm private modes
  (`ESC[?h/l`) parse as accepted no-ops; SGR ignored (color is the
  tile-paint layer's concern).
- The gate runs a single echo guest; no multi-terminal interleaving.
- No rates/latencies claimed (rule-1 floors do not attach — all
  asserts structural).

## Honesty notes

- Engine byte-guard N1: `glyph_isa_v2.py` working-tree md5 vs
  `git show HEAD:tools/glyph_isa_v2.py` — asserted equal inside the
  gate (test_n1_engine_byte_guard, GREEN in the tail above). No engine
  file touched; no new syscall number (0x01/0x02/0x05 as landed).
- Measured prerequisite probe kept: `output/item39_probe_echo.py`
  (guest echo through ring -> PRT -> VT parser -> band decode).
- Queue: item-39 -> landed. Next tick: item-40 (desktop notification
  daemon & system tray ABI, claim_order 40) per Phase-1b, unless a
  newer RULING intervenes.
