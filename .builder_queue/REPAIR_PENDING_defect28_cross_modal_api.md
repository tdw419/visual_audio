# REPAIR_PENDING — DEFECT-28 file (1): `tests/test_cross_modal.py` targets a `cross_modal` API that never existed

**Filed:** 2026-09-13 by builder cron `af3e62239ce2` (tick at HEAD `d3e6513`).
**Status: RULED 2026-09-13** — see `.builder_queue/RULING_format_authority_and_crossmodal.md` §2 (option 2 of
those listed below, in substance: fix the CLI drift test-side, re-point only where a REAL equivalent exists, xfail-with-reason
+ ticket where none does, never invent module API, never delete the test). Blocker marked RULED, header kept for the record.
**Follow-on:** `.builder_queue/DEFECT-29_cross_modal_tile_abi_missing.json` (the four phantom functions).
**Answers:** `.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md` § *Cheapest first (1)*, which asked
"identify what replaced `extract_tiles` in the `cross_modal` module and which CLI subcommand(s) `:165` should invoke".

## Measured (orchestrator's own runs, this tick)

```
/usr/bin/python3 -m pytest tests/test_cross_modal.py -q --tb=line
-> 6 failed, 2 passed in 0.56s
   :60  AttributeError: module 'cross_modal' has no attribute 'text_to_tiles'
   :86  :103 :124 :138   AttributeError: module 'cross_modal' has no attribute 'extract_tiles'
   :165 AssertionError: CLI failed: usage: cross_modal.py [-h] {from-image,from-audio,from-text} ...
```

1. **The test file is untracked and six weeks old.** `.gitignore:101 (test_*.py)` hides it; `git ls-files
   --error-unmatch tests/test_cross_modal.py` → *did not match any file(s) known to git*; `git log -- tests/test_cross_modal.py`
   is empty; mtime **2026-07-27 23:52**. The product module `tools/cross_modal.py` is **tracked**, mtime 2026-08-05,
   last touched by `c6a0b21`.
2. **Nothing replaced `extract_tiles` — it was never in `cross_modal`.** `git log -S"extract_tiles" --all` hits only
   `3b3d9a6` and `1eb4edd`, where the symbol is `extract_tiles_from_frame` in **`tools/pixel_dedup_optimized.py:45`** —
   a different module. `git log -S"tiles_to_audio_byteperfect" --all` → **no hits at all**. A repo-wide grep for
   `text_to_tiles|tiles_to_audio_byteperfect` finds no provider; the closest live shapes are
   `tools/cross_modal_minimal.py` (`image_to_tiles/tiles_to_audio/audio_to_tiles/tiles_to_image`, positional
   signatures) and `tools/cross_modal_mock.py` (`tiles_to_image(tiles) -> Image`). Neither exposes `extract_tiles`.
   So the six failing legs assert an API that exists in **no** committed revision.
3. **The CLI legs are real drift, but not enough to close the file.** The live contract is
   `cross_modal.py from-text TEXT --output-dir DIR` (measured `--help`), writing artifacts into that directory; the
   test passes `--output <image.png> --audio-output <audio.wav>` → argparse `unrecognized arguments` (rc=2). The
   other two CLI legs (`:171`, `:191`) already PASS, which is the 2/8 green count.
4. **Consequence for the row's gate:** `pytest tests/test_cross_modal.py -q` **cannot reach 8 passed** without adding a
   whole tile ABI (`text_to_tiles`, `extract_tiles`, `tiles_to_audio_byteperfect`, `tiles_to_audio_semantic`,
   `audio_to_tiles`, `tiles_to_image`) to the product module. That is inventing a feature, not fixing drift.

## Options (cheapest first)

1. **Retire the fixture as an orphan (recommended, ~5 min, no product change).** Move `tests/test_cross_modal.py`
   aside (e.g. `tests/disabled/test_cross_modal_tileabi_orphan.py`, the directory `EXCLUDE_DIR_NAMES` in
   `tools/suite_iso_harness.py:43` already excludes) with a one-line header naming this file; record in the DEFECT-28
   ticket and the SUITE-FIX-1 row that the 6 legs were assertions against a never-committed API, and that the row's
   `PASS 8/8` gate is not the right target. **Cost:** loses the file's (unexercised) intent; reversible via git-less
   rename back. **Needs:** your OK, because it changes the sweep's FAIL count on evidence you have not seen yet.
2. **Repoint the test at the live MFSK module (medium).** Rewrite the 6 legs against `tools/cross_modal.py`'s real API
   (`from_text_mode/from_image_mode/from_audio_mode`, `generate_mfsk_audio/decode_mfsk_audio`) — i.e. a NEW test of
   the byte and semantic round-trips, keeping the CLI legs with `--output-dir`. **Cost:** a real design call about what
   "byte-perfect" means for the MFSK path; a spec, not a patch.
3. **Build the missing tile ABI (largest).** Add the tile functions to `tools/cross_modal.py` so the July test passes
   unmodified. **Cost:** a product feature invented from an untracked test; `tools/cross_modal_minimal.py` /
   `_mock.py` suggest a lane once prototyped this and it never landed. Recommend against without a product intent.
4. **Leave it red and exclude it from the sweep** by extending the harness's exclusion rules. **Cost:** silently
   narrows coverage — the same class of blindness `SUPPLY-CENSUS-1` was filed for. Recommend against.

## Not decided here

Files (2) `tests/test_vcc_validation.py` and (3) `tests/test_griffin_lim.py` remain as ticketed in DEFECT-28; (3)
touches `src/griffin_lim.py`, so it is a real defect with a real gate, but neither was measured this tick (this tick
spent its measurement budget on (1), which the ticket ordered first). **Do not read this note as a claim that the
cluster is resolved.**
