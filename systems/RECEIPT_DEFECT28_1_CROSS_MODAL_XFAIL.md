# RECEIPT — SUITE-FIX-1 / DEFECT-28 file (1): `tests/test_cross_modal.py` CLI drift fix + 5 capability xfails

**Date:** 2026-09-13 · **Builder cron:** `af3e62239ce2` · **Base HEAD:** `7935035` (branch `glyph-transpiler-autoloop`)
**Ruling implemented:** `.builder_queue/RULING_format_authority_and_crossmodal.md` **§2**
**Ticket filed:** `.builder_queue/DEFECT-29_cross_modal_tile_abi_missing.json` (the four phantom functions)

## Why this unit

Roadmap row `SUITE-FIX-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:355`) is the first row not ✅/done.
`DEFECT-28`'s own ticket ordered file **(1)** first as "mechanical drift"; the previous tick measured that claim
FALSE and filed `REPAIR_PENDING_defect28_cross_modal_api.md` as a design question. The ruling above answered it, so
the unit became eligible this tick. The row's other remainders are unchanged: leg **1b** (wordbook) is
BLOCKED-ON-DESIGN, **DEFECT-27** was ruled only this tick (see below), clusters (3)–(4) partially landed.

## RED first (orchestrator's own run, before any edit)

```
/usr/bin/python3 -m pytest tests/test_cross_modal.py -q --tb=line
-> 6 failed, 2 passed in 0.60s
   :60  AttributeError: module 'cross_modal' has no attribute 'text_to_tiles'
   :86 :103 :124 :138   AttributeError: module 'cross_modal' has no attribute 'extract_tiles'
   :165 AssertionError: CLI failed: usage: cross_modal.py [-h] {from-image,from-audio,from-text} ...
```
Saved: `output/cross_modal_orch_RED_prefix.txt` (rc=1).

## GREEN after (orchestrator's own re-run on the tree the delegate left)

```
/usr/bin/python3 -m pytest tests/test_cross_modal.py -q -rxX
-> 3 passed, 5 xfailed in 0.62s        rc=0
   XFAIL × 5, each reason naming the phantom callable + line and
   ".builder_queue/DEFECT-29_cross_modal_tile_abi_missing.json"
```

**Non-vacuity (the gate shown able to fail):** with the markers disabled,
`/usr/bin/python3 -m pytest tests/test_cross_modal.py -q --runxfail`
-> **5 failed, 3 passed**, every failure still the ORIGINAL `AttributeError` at `:60/:86/:103/:124/:138`.
The marker — not a weakened body — is what turns those five green. The fixed CLI leg asserts the two artifacts the
live `from_text_mode` (`tools/cross_modal.py:416-464`) actually writes, `round_trip.wav` + `round_trip_output.png`,
not merely `rc == 0`.

**Harness-level verdict token** (`tools/suite_iso_harness.py tests/test_cross_modal.py -t 150 -w 1 --json`):
`verdict: "PASS"`, `counts {collected: 8, passed: 3, failed: 0}`, 1.30 s
(`output/cross_modal_harness_post.json`) — this file was one of the 7 FAILs in the SUITE-BASE-2 re-measure, so the
sweep's FAIL budget should drop by one on the next full sweep.

## Scope

`git status --short` / `git diff --stat`: **only** `tests/test_cross_modal.py` was modified by the delegate
(force-added this commit past `.gitignore:101 test_*.py`, like `tests/test_instrument1_mark_registration.py`).
No file under `tools/`, `src/`, `glyph_dispatch/`, no WGSL shader, no `pytest.ini` — **no module API invented**
(the ruling's FORBIDDEN clause), no leg deleted, no assertion removed from the two passing CLI legs.
`tools/cross_modal.py` byte-identical.

## Delegation note (and why `agy_implement.sh` returned 3)

Delegated with `TIMEOUT=45m EFFORT=medium bash ~/.hermes/scripts/agy_implement.sh -f .builder_queue/brief_defect29_cross_modal_cli_xfail.md`
(108 s; brief `output/agy/agy_brief_20260913_204459.txt`, reply `output/agy/agy_impl_20260913_204459.log`).
The wrapper reported **`UNVERIFIED — reply carries no DIFF SUMMARY block`** and exited 3, but the reply **does**
carry the required evidence (RED tail, gate tail `3 passed, 5 xfailed`, the five reason strings, `git status`):
the detector keys on a literal block header and the reply used numbered sections. **The orchestrator re-ran every
leg above; nothing here rests on the delegate's claim.** Filed as `INSTRUMENT-2` (wrapper recall, not a correctness
gap in this change).

## What this PASS does NOT prove

- **The tile ABI is still absent and now unexercised.** Five legs are recorded as missing capability, not verified
  behaviour; nothing about `text_to_tiles` / `extract_tiles` / `tiles_to_audio_byteperfect` / `tiles_to_audio_semantic`
  is tested by anything. `xfail(strict=True)` makes a future accidental XPASS go RED, so the gap cannot become
  silently green — but the gap is real.
- **The re-point clause of the ruling was NOT executed, deliberately.** Every failing leg also depends on ≥1 phantom
  function, so no re-point could flip one to PASS; and the two live candidates measured are not equivalents —
  `pixel_dedup_optimized.extract_tiles_from_frame` needs a 4096×4096 RGBA frame, returns 32×32 `bytes` tiles and
  imports PIL, while the leg it would replace exists to assert 16×16×4 tiles and PPM loading with no PIL. Adapting the
  assertions to fit would replace the assertion set, which `DEFECT-28`'s ticket orders against. Recorded as the first
  option in the `DEFECT-29` ticket instead of guessed at.
- **No full sweep was re-run this tick** (contention rule; a parallel session was live). "No other file regressed" is
  inferred from the diff being test-file-only, not measured by a sweep. The next SUITE-BASE sweep must confirm the
  FAIL budget drop and the new xfailed count.
- **xfailed legs are counted nowhere** in the harness record: `collected 8, passed 3, failed 0`, so 5 records sit in
  neither bucket. Same accounting family as the `coll=0` artifact corrected by SUITE-COLLECT-1; noted, not filed.
- `sys.executable`-dependent CLI legs were run under `/usr/bin/python3` only; the hermes venv was not exercised.
