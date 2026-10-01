# RECEIPT — BK-19: VGA 8x16 atlas completion (10 missing printable-ASCII glyphs)

Claim-queue round-7 item 13 · builder cron af3e62239ce2 · 2026-09-23 ~13:1x CDT
Tree: visual_audio HEAD before landing `12db395a08be`, branch `glyph-transpiler-autoloop`
Supply: `.builder_queue/SUPPLY_ROUND7.json` item 13; gate text binding as written.

## What landed

- `tools/vga_font_8x16.py` — ADDED the 10 missing printable-ASCII glyphs
  `[ \ ] ^ _ ` { | } ~` (canonical IBM VGA ROM rows; source below). Existing
  85 glyphs untouched (ADD, don't swap). Header comment now says 95/95.
- `tools/glyph_text_console.py:19-22` — coverage docstring 85 → 95 (the
  `glyph_text_console.py:20` number named by the supply).
- `tests/test_glyph_text_console.py:72-80` — the `test_red_unknown_char...`
  leg fed `'['`, which is IN the font since BK-19; its ?-substitution intent
  is preserved with `'€'` (still absent from the font). The old assert would
  have been permanently wrong post-landing (`'a[b'` now decodes, not `'a?b'`).
- `tests/test_bk19_font_atlas.py` — NEW gate (8 legs), force-added past the
  `.gitignore:101` `test_*.py` rule.

## Source of the new rows (measured, not recalled)

Rows extracted programmatically from the in-tree Linux kernel font
`~/projects/zion/linux-riscv/lib/fonts/font_8x16.c` (`fontdata_8x16`,
256 glyphs, glyph index == ord(char) for the printable-ASCII half), by
`/tmp/extract_glyphs.py`-equivalent parsing (0x-hex byte scan, 16 rows/glyph,
4096 bytes total parsed). Extraction cross-checked every one of the repo's
85 pre-existing glyphs against the same kernel indices for uniqueness of the
ADDED set: all 85 repo patterns are internally unique and none of the 10 new
patterns collide with any existing pattern (decode is exact-match, so a
collision would make decode ambiguous — this is the safety property, since
the repo's 85 pre-existing glyphs intentionally DIVERGE from the kernel font
in 38 places and were NOT touched).

## Gate arc (all runs by this builder, one process per leg)

RED (pre-landing tree, `12db395a`):

```
FAILED tests/test_bk19_font_atlas.py::test_red_missing_chars_absent_from_font
FAILED tests/test_bk19_font_atlas.py::test_red_question_mark_substitution_discriminates
FAILED tests/test_bk19_font_atlas.py::test_green_added_rows_are_canonical_vga
FAILED tests/test_bk19_font_atlas.py::test_green_all_95_render_and_decode
FAILED tests/test_bk19_font_atlas.py::test_green_sample_string_exact
FAILED tests/test_bk19_font_atlas.py::test_green_wgsl_twin_band_parity_brackets
5 failed, 3 passed in 1.23s
```

(The 3 passes are glyph-independent legs: collisions-unique and
preexisting-strings — both true before and after, as designed. The WGSL leg's
RED failure detail is itself the live defect: twin PRT bytes were already
correct, band decoded `?code??sample?`.)

Stash-discrimination RED (fix stashed → same RED set; popped → GREEN):

```
git stash → 1 passed (test_red_unknown_char_renders_as_question_mark, old '[' version)
git stash pop → fix back in tree
```

GREEN (post-landing):

```
tests/test_bk19_font_atlas.py  8 passed in 0.85s
console+atlas together        19 passed in 1.07s
```

## Regressions (this tick, one pytest invocation each)

```
console + item11 grammar + dispatch shell + bk7 + gh10 shell + isa_v2 +
echo app + gh4/bk12/bk2/se024 WGSL parity + interactive shell + bk19:
74 passed in 2.60s
```

Live batch pipe (`output/bk19_live_pipe.py`, exit 0): `e [code]{sample} ~ ^_|`
through the item-11 dispatch shell with a console attached → band decodes
` [code]{sample} ~ ^_|` exactly (the operator's spot-check string, all
new-glyph families exercised).

## WGSL twin parity leg

`test_green_wgsl_twin_band_parity_brackets` runs `run_wgsl` on the ECHO_SHELL
with input ring `[code]{sample}`, requires the twin's PRT bytes == ring, and
requires the twin-rendered band `np.array_equal` to the Python-engine band for
the same bytes. This ran on the real wgpu backend this tick (not skipped).
Per the standing twin-boundary note: the console FONT is host-side; the twin
leg covers the PRT byte stream + band parity, not glyph rendering in WGSL.

## Honesty / what this PASS does NOT prove

- The 38 pre-existing divergences between the repo's original 85 glyphs and
  the kernel font were NOT reconciled — out of scope (ADD, don't swap);
  decode is self-consistent because it matches against the repo font itself.
- No non-printable/non-ASCII glyph was added; chars like `€` still render
  as `?` (gated by the preserved `test_red_unknown_char_renders_as_question_mark`).
- No floors/rate claims made → rule-1 floors N/A for this receipt.
- The gate does not prove print rendering on real VGA hardware — the repo
  font is its own decode authority; "canonical" here means byte-identical to
  the kernel's fontdata_8x16 rows for those 10 indices (asserted by
  `test_green_added_rows_are_canonical_vga` at every run).
- BK-16 (clock) remains backlog, untouched, per the round-6 note.
