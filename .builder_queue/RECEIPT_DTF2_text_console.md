# RECEIPT — DTF-2 item 10: in-image text console (VGA-font text band in the observation image)

**Date:** 2026-09-22 ~20:0x CDT
**Builder:** af3e62239ce2 (product lane, claim-queue round 5)
**Base revision:** 9b5668dc (item-10 brief landed in ledger; no engine/app changes at base)
**Scope touched:** `tools/glyph_text_console.py` (NEW), `tests/test_glyph_text_console.py` (NEW, force-added past .gitignore), `experiments/glyph_interactive_shell.py` (repl signature + `__main__` only), `PRODUCT_LANE_STATE.md`, this receipt. No engine, codec, shader, or protected-asset changes.

## What landed

`tools/glyph_text_console.py` — `TextConsole`: a bounded row-ring (default
8 rows × 40 cols) of text rendered into an 8×16-px-per-cell pixel band using
the existing IBM VGA 8x16 font (`tools/vga_font_8x16.py`, 85 glyphs).

- **Input** is the PRT byte stream: `GlyphCPUv2.output` (glyph_isa_v2.py:586/1075)
  as collected per turn by `run_turn`. The shell's `repl()` grew an opt-in
  `console=` kwarg that feeds each turn's output bytes into the ring; the
  default (`console=None`) reproduces pre-DTF-2 behavior exactly.
- **Render** is bottom-anchored: oldest lines scroll off the top of the
  ring; `render_band()` emits (rows·16, cols·8, 3) uint8. Glass-TTY boundary
  honored per the amendment: the ring is a renderer concern, no blitter or
  hardware-scroll claims.
- **Decode is glyph-side**: `decode_band()` exact-matches every 8×16 cell
  against the font bitmaps themselves (built once from `VGA_FONT_8X16`, never
  against a stored copy of the input) and REFUSES on any foreign pixel or
  unmatched cell. Missing-font chars render as `?` (documented, never blank).
- **Compose/persist**: `compose_observation()` places the band below the
  program region (program left-aligned, untouched); `save_png()`/`load_png()`
  use the existing PIL container paths. `__main__` persists the session band
  to `$GLYPH_SH_CONSOLE_PNG` (default /tmp/glyph_sh_console_band.png).

## Gate legs (item 10's gate, from PRODUCT_LANE_STATE.md round 5 / SUPPLY_ROUND5.json)

### RED-first: blank-sentinel band read

`tests/test_glyph_text_console.py::test_red_blank_band_decodes_to_empty` —
a fresh console's band is all-black (the blank sentinel) and decodes to `""`.
Non-vacuity RED legs: `test_red_decode_refuses_mutated_band` (ONE pixel set
to a third color → decode raises `non-.../... pixel`), `test_red_decode_refuses_wrong_shape`,
`test_red_unknown_char_renders_as_question_mark` (`[` absent from the font →
band shows `a?b`, not `a b`).

### GREEN (a): transcript → band → exact glyph-side decode (not a host print)

`test_green_transcript_decodes_exactly` + `test_green_ring_scrolls_bottom_anchored`
(12 lines through an 8-row ring → decode returns exactly the retained 8,
bottom-anchored) + `test_green_turn_bytes_are_the_prt_stream` (`w payload` PRTs
nothing, `r` PRTs ` payload` — the band shows the PRT stream, never the typed
commands). End-to-end at the real entry surface:

```
$ printf 'e hello band\nw note text\nr\nquit\n' > /tmp/dtf2_session_input.txt
$ python3 experiments/glyph_interactive_shell.py < /tmp/dtf2_session_input.txt
  echo:  hello band
  echo:
  echo:  note text
  console band -> /tmp/glyph_sh_console_band.png
$ # decode the PNG glyph-side:
 hello band

 note text
BAND DECODE: OK   (band shape (128, 320, 3))
```

### GREEN (b): WGSL twin parity — same byte stream, byte-identical band

`test_green_wgsl_twin_band_parity` + reproduced standalone this session:
ECHO_SHELL assembled, run on `GlyphRunner.run_wgsl` (GPU twin) with
`input_ring=b"e hello band"` → twin PRT bytes `b'e hello band'`, halted;
Python engine leg for the same bytes; `render_transcript` of both streams →
`np.testing.assert_array_equal` byte-identical; decode recovers the exact
string. (Engine-level twin band leg, per the same-commit rule.)

### GREEN (c): regressions

```
pytest tests/test_glyph_text_console.py tests/test_glyph_app_shell_dispatch.py \
  tests/test_glyph_interactive_shell.py tests/test_glyph_isa_v2.py \
  tests/test_pillar21_abi_spec_rotguard.py tests/test_pillar23_parity_ci.py \
  tests/test_se022a_read_parity.py tests/test_gh20_fs_v2.py
→ 74 passed
```

Item-10 gate alone: `pytest tests/test_glyph_text_console.py` → **11 passed**.

### GREEN (d): batch invariant intact

`test_green_batch_invariant_console_off_default` monkeypatches
`sys.stdin` to an empty StringIO — if batch mode touched stdin, `input()`
would drain it and the run would hang/fail; it passes. The console feeds
only from `cpu.output` (engine PRT bytes), never from input paths.

## Landing-time defect found and held (NOT silently fixed)

`build_dispatch_shell` stamps its paths at fixed words [1024,1280), which
alias to pixel rows 64..80. Path LENGTH is load-bearing: with long paths
(~85 chars, e.g. pytest `tmp_path`) the program grows past row 64 and the
stamp loop clobbers instruction pixels at runtime — measured:
`steps=503`, halt `opcode-None pixel at (28,67): rgb=(0,0,99)` (a stamped
path byte over an instruction slot), turn PRT output empty. The existing
item-9 tests pass only because `test_glyph_app_shell_dispatch._fixed_paths`
uses short mkdtemp names. This session's tests adopted the short-path
convention and the receipt documents the hazard. **NOT fixed** — the
builder asserts against paths but does not reject long ones; filing as
queue supply for a future item (bounded fix: length check in
`build_dispatch_shell`'s assert, or region-B relocation as in
`build_exec_shell` v5/v6).

## What this PASS does NOT prove

- The band is rendered host-side from the engine's PRT stream (glass-TTY);
  no glyph program draws the band itself, and the WGSL twin does not write
  band pixels — the twin leg is parity of the byte stream feeding the
  renderer, not twin-side rendering.
- Batch-mode only in pytest; the interactive pipe was exercised via stdin
  redirection, not a human at a tty.
- No rate claims → floors not consulted (rule-1 N/A).
- Font coverage is 85 glyphs; the ASCII bracket/brace family renders as `?`.
- Scrolling is ring eviction, not preserved history — scrolled-off lines
  are gone (bounded ring by design).
