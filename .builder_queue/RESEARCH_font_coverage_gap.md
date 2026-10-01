# RESEARCH — VGA font coverage gap: the floor's error strings display with holes (BK-19 candidate)

**Date:** 2026-09-22 ~23:1x CDT
**Builder:** af3e62239ce2 (Glyph GPU OS product lane)
**Trigger check:** ledger STATUS ACTIVE; CLAIM QUEUE EMPTY (rounds 1–3
closed); no RULING newer than HEAD 2a5a298a at tick start (newest RULING
mtimes 20:38, pre-landing); monitor CLEAN queue=0. Research tick per the
2026-09-22 standing directive; one item.

## Question

The DTF floor exit receipt (RECEIPT_DTF_floor.md:60-76, landing defect 2)
disclosed that the machine's own most important error string — the unknown-
command marker `ERR:UNKNOWN_CMD` — renders in the pixel band with a hole
(`ERR:UNKNOWN?CMD`) because `_` is absent from the VGA font atlas. That
disclosure was filed as "candidate queue supply" but never became a backlog
row. How big is the gap, exactly, and what does it affect?

## Method

Re-runnable probe: `.builder_queue/probe_font_coverage_gap.py` (exit 0 this
tick), driving the production font module and the production console:

- `tools/vga_font_8x16.py` — `VGA_FONT_8X16.keys()` vs printable ASCII 32..126.
- `tools/glyph_text_console.py` — the real render→decode round-trip used by
  every DTF-2 band (render `'ERR:UNKNOWN_CMD'`, decode it back glyph-side).
- Fixture blast radius: `COREUTILS_FIXTURES`
  (`tools/glyph_gpt/coreutils_port.py:227`) — all 15 expected-stdout values
  scanned for the missing charset.

## Findings (all structural counts or live round-trips; derivation command named per number)

- Font coverage: **85 glyphs of the 95 printable ASCII chars** (32..126).
  **Missing exactly: `[ \ ] ^ _ \` { | } ~`** — codes 91, 92, 93, 94, 95,
  96, 123, 124, 125, 126. Command: the probe's set difference, re-derivable
  with `python -c "from tools.vga_font_8x16 import VGA_FONT_8X16; ..."`.
  The docstring's "85 glyphs" claim is numerically correct — the gap is the
  10-char bracket/brace family, deliberate or not, it is real.
- The floor's unknown-command marker contains **1 missing char** (`_`).
  Live round-trip through the production console: `'ERR:UNKNOWN_CMD'` →
  rendered → decoded `'ERR:UNKNOWN?CMD'` — **lossy, by the renderer's own
  documented substitution** (glyph_text_console.py:111-112, missing char →
  `'?'`, "never a silent blank"). Decode is exact-match against font
  bitmaps, so the substitution round-trips faithfully-as-`?`: the band is a
  true record of a hole, not of the character.
- **Blast radius today is bounded at exactly one floor string**: all 15
  BK-11 coreutils fixture outputs (bump_alloc hex values, checksum lines,
  wc counts) contain ZERO missing-charset chars — measured, not assumed.
  But any future program printing braces, brackets, underscores in
  identifiers, or path globs (`{a,b}`, `arr[i]`, `foo_bar`) hits the same
  wall, and the machine CANNOT display its own error strings correctly —
  the class of strings most likely to contain unusual punctuation is the
  class the gap eats.
- Worst-case display string check: `ERR:UNKNOWN?CMD` decodes fine (the `?`
  glyph exists), so the current failure mode is *confusing*, not crashing:
  a day-2 operator reads an error code that does not match what the
  machine's dispatch layer actually printed (DTF-1 transcript vs DTF-2 band
  disagree by one character).

## The ONE candidate item (backlog format — proposal, NOT landed work)

| Field | Value |
|---|---|
| ID | BK-19 |
| Item | **Complete the VGA 8x16 atlas: add the 10 missing printable-ASCII glyphs `[ \ ] ^ _ \` { | } ~`** to `tools/vga_font_8x16.py` (bitmaps from the canonical IBM VGA 8x16 ROM table — the same source the other 85 glyphs came from; the font module's own header claims "complete IBM VGA 8x16 font (subset: printable ASCII 32-126)" — vga_font_8x16.py:15 — so this is completing a claimed subset, not extending scope). Update the "85 glyphs" coverage numbers in glyph_text_console.py:20 and glyph_text_console.py:85 to 95. The console renderer and decoder need ZERO code change (both iterate the font dict); the DTF-2 band decode becomes lossless for the full printable ASCII set. |
| Gate spec | `tests/test_bk19_font_coverage.py` — L1: printable ASCII 32..126 ⊆ VGA_FONT_8X16 (RED today by measurement: 10 missing); L2: each new glyph's bitmap differs from the `?` fallback bitmap AND from every existing glyph (collision-free, XOR-discriminable); L3: render→decode round-trip of the full 95-char printable set through TextConsole is byte-identical (RED today: `ERR:UNKNOWN_CMD` leg returns `ERR:UNKNOWN?CMD`); L4: non-vacuity mutation — delete one new glyph from the font dict in-memory → L1 and L3 both fire; L5: existing DTF-2 console gate (`tests/test_glyph_text_console.py` or its landed equivalent) stays green — no regression to the 85 existing glyphs. |
| Prereqs | None new — font module, console, decoder all landed and green (DTF-2 row done); canonical VGA ROM bitmaps are public constant data. |
| Source | RECEIPT_DTF_floor.md:60-76 (landing defect 2, "filed as candidate queue supply") + this receipt's measurements. |
| Explicitly NOT this item | Any change to the render/decode CONTRACT (the `?` substitution stays for genuinely unknown chars — e.g. future non-ASCII); any engine/shader change (the font is host-side glass-TTY tooling); the BK-17 spec-sync (separate row, separate scope). |

## Honesty

- Research only — no production line touched; probe + this receipt + backlog
  row are the entire diff (plus the ledger entry).
- Numbers here are structural counts (set differences, dict sizes, fixture
  scans) and one live round-trip on this machine — none is a rate/ratio/
  frequency, so no floors_authoritative.json citation is required (rule 1
  not triggered).
- NOT verified: whether the 10 missing glyphs were deliberate exclusions
  (an atlas-size decision) or drift — no commit message or doc in the tree
  records a decision; if deliberate, Jericho's approval of BK-19 reverses
  it, which is exactly why this is backlog, not a landing. NOT verified:
  bitmaps beyond existence/shape (the gate's L2 covers that at landing
  time). NOT verified: what the WGSL twin renders for these chars — the
  band is host-side glass-TTY; there is no shader font to sync (per
  RECEIPT_DTF_floor.md:86-88).
- Re-research check (rule 5): no existing RESEARCH_*.md or backlog row
  covers font coverage — BK-15/16/17 are user-surface/spec/oom; the gap was
  only *disclosed*, never receipted, before this tick.
