# BRIEF — SUITE-FIX-1 / DEFECT-28 file (1): `tests/test_cross_modal.py` CLI drift fix + capability xfails

## Spec pointer (read FIRST, in this order)

1. `.builder_queue/RULING_format_authority_and_crossmodal.md` **§2** — the decision you are implementing. It is in force.
2. `.builder_queue/REPAIR_PENDING_defect28_cross_modal_api.md` — the measured facts (now marked RULED with a pointer).
3. `.builder_queue/DEFECT-29_cross_modal_tile_abi_missing.json` — the ticket the xfail reasons must cite.
4. Roadmap row `SUITE-FIX-1` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355`, plus `DEFECT-28_suite_fix1_c4_drift_and_defects.md` line ordering "(1) … preserving every assertion".

## Scope — exactly ONE file

**MAY change:** `tests/test_cross_modal.py` (currently UNTRACKED, hidden by `.gitignore:101 test_*.py`).
**MUST NOT change:** `tools/cross_modal.py`, `tools/cross_modal_minimal.py`, `tools/cross_modal_mock.py`,
`tools/pixel_dedup_optimized.py`, any file under `glyph_dispatch/`, `src/`, `tools/glyph_gpt/`, any WGSL shader,
`tests/suite_iso_harness.py`, `pytest.ini`. Do NOT commit. Do NOT delete any test, do NOT remove any assertion,
do NOT create any new module or fixture file, do NOT invent any function in any product module.

## The two required edits

**(A) Fix the genuine CLI drift (must flip FAIL→PASS).** `test_cli_from_text_mode` (`:149-169`) passes
`from-text "Test" --output <image.png> --audio-output <audio.wav>`; the live CLI is
`cross_modal.py from-text TEXT --output-dir DIR` (both `-o/--output` and `--audio-output` are rejected by argparse).
Re-point it at `--output-dir` and assert the artifacts the live `from_text_mode` actually writes
(`tools/cross_modal.py:416-464`): `round_trip.wav` and `round_trip_output.png` inside that directory.
Keep asserting `returncode == 0` and that both files exist. This leg must pass for a real reason.

**(B) Mark the 5 capability legs `xfail(strict=True)` with a NAMED reason that cites `DEFECT-29`.**
Legs: `test_text_to_audio_to_image_roundtrip` (`:50`), `test_image_to_audio` (`:79`), `test_audio_to_image` (`:98`),
`test_semantic_encoding` (`:120`), `test_ppm_support` (`:133`).
The reason string must name the phantom callable (and its line) and the ticket path, e.g.
`reason="cross_modal.extract_tiles (+ tiles_to_audio_byteperfect / tiles_to_audio_semantic / text_to_tiles) exists in no committed revision — ticket .builder_queue/DEFECT-29_cross_modal_tile_abi_missing.json"`.
`strict=True` is required: a future XPASS must go RED, never silently green. Add the `pytest` import if needed.
Do NOT re-point these legs at `extract_tiles_from_frame` / `image_to_tiles` / `cross_modal_mock`: measured, none is a
drop-in equivalent (4096×4096 frame + PIL + 32px bytes vs a 16×16×4 PPM fixture asserting no-PIL support); changing the
assertion set to fit a mock is explicitly out of scope for this brief.
The two already-passing CLI legs (`:171`, `:191`) stay untouched.

## Gate command (run it yourself; paste raw output)

```
cd /home/jericho/projects/zion/projects/visual_audio
/usr/bin/python3 -m pytest tests/test_cross_modal.py -q -rxX
```

**Gate clause — expected, falsifiable:**
- exit code **0**; summary exactly `3 passed, 5 xfailed` — i.e. **0 failed** (pre-fix this file is `6 failed, 2 passed`).
- `-rxX` output carries **5 XFAIL lines**, each with a reason naming `DEFECT-29`.
- `round_trip.wav` and `round_trip_output.png` are asserted to exist by the fixed CLI leg (not just rc==0).

**Failure evidence — the gate must be shown able to fail (do this, paste it):**
1. RED-first: before editing, run the gate command and paste the `6 failed, 2 passed` tail (a copy is at
   `output/cross_modal_orch_RED_prefix.txt`).
2. Non-vacuity: after editing, run `/usr/bin/python3 -m pytest tests/test_cross_modal.py -q --runxfail`
   (or `-o xfail_strict=false --runxfail`) and confirm the 5 marked legs **still fail with the ORIGINAL
   `AttributeError`, at the same line numbers** — the marker, not a weakened body, must be what turns them green.
3. `git status --short tests/ tools/` — only `tests/test_cross_modal.py` may appear as modified/new.

## Return to the orchestrator

The raw gate tail (`3 passed, 5 xfailed`), the `--runxfail` tail, the 5 xfail reason strings, and
`git diff --stat`. Nothing else. Do not commit.
