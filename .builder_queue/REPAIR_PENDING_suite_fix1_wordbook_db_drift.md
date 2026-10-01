# REPAIR_PENDING — SUITE-FIX-1 cluster (1), wordbook sub-part: the fixture is unreproducible and its pinned colours no longer match the tracked DB

**Filed** 2026-09-13 ~17:20 by builder cron `af3e62239ce2`, branch `glyph-transpiler-autoloop`, head `539d418`.
**Status: BLOCKED-ON-DESIGN** — needs a ruling before anyone touches it. Not a mechanical fix.
**Skeleton-sign-off change?** No — this is a fixture/decision question, not a locked-interface change.

## Measured facts (all re-run by the orchestrator, not quoted from prose)

| probe | result |
|---|---|
| `PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_glyph_wordbook_lookup.py -q` | **2 failed** (`FileNotFoundError: wordbook.png`) |
| `git ls-files tests/test_glyph_wordbook_lookup.py` | **empty** — the test file itself is untracked (`.gitignore`'s `test_*.py` rule); only `tests/test_spatial_ide.py` is tracked |
| `git check-ignore -v wordbook.png` | `.gitignore:84:wordbook.png` — and `wordbook.meta.json` is line 85; **neither is tracked**, so the fixture exists in no revision |
| `wordbook.meta.json` (untracked, pinned) | `sha256 50ea7dc4…`, `max_id 126129`, `colored_words 125262`, 4096×32 |
| `sqlite3 db/wordbase.db` (tracked, clean vs HEAD, last touched by `ba13857`) | `50448 → #9050FD`, `124061 → #FF0000`, 126154 rows, `max_id 135268` |
| spec expectations | `("hello", 50448, "#5D4140")`, `("world", 124061, "#7D7930")` |
| rebuild in `/tmp/wbtest` from the tracked DB via `tools/build_wordbook.py` | 408,630 B, `sha256 2214842bf6a61b28fb578b0f7ed7d80b17d96a81177d8968f226902ae0147125`, and `WARNING: ID 135268 exceeds texture capacity (131072)` |

**Consequences.** (i) Building the PNG does **not** make the legs pass — the two colour constants are stale, so the
bake cannot flip them FAIL→PASS. (ii) The tracked DB has outgrown the 4096×32 bake (`max_id 135268 > 131072`), so
`build_wordbook.py` now silently drops words and can never again reproduce the pinned meta sha — the "VCC hash"
pinning in `wordbook.meta.json` is currently decorative. (iii) The colour for a fixed id changed between the state
the test was written against and the tracked DB, which means the id→colour mapping churns under ordinary runtime
bookkeeping commits (cf. `ba13857`, "wordbase.db/upic state … from 09-10 evening sessions").

## The design question (one ruling closes it)

**Which artifact is canonical — the tracked `db/wordbase.db`, or the pinned colour expectations?**
The test's actual claim is "the spatial ISA (`GlyphCPUv2` via `LD`/`LDI`/`PRT`) can read a word's colour straight out
of the bitmap with no Python-side dict lookup". That claim is orthogonal to *which* colours the DB happens to hold.

## Options, cheapest first

- **(a) Re-point the expectations at the DB** — regenerate the two `expected_hex` values from the tracked DB and have
  the test build the bake from `db/wordbase.db` into a scratch dir as its own fixture step (no committed binary).
  Cheapest, keeps the real claim, drops stale pinning. Needs a companion decision on the `135268 > 131072` overflow.
- **(b) Make the DB the fixture's provenance** — restore `db/wordbase.db` to the revision that reproduces
  `50ea7dc4…` and force-add `wordbook.png` as a committed binary fixture (against `.gitignore:84-85`, and a
  data rollback whose blast radius is the audio/VCC lanes).
- **(c) Treat the DB churn + bake overflow as the defect** — open a wordbase-versioning ticket (capacity, id
  stability, hash pinning) and hold the 2 legs red until that is ruled; the colour pinning then becomes a VCC
  fingerprint rather than a fixture.
- **(d) skip-with-reason** for the 2 legs — arguably "environment class" (untracked, unreproducible fixture), but the
  SUITE-FIX-1 row only permits skip-to-green for the offline-endpoint class, so this needs an explicit call.

## What was done instead, this tick

The other half of cluster (1) — `tests/test_spatial_ide.py`, 0/8, missing `tools/spatial_examples/*.asm` +
`tools/spatial_ide.py` — was worked as its own gate-able step (brief
`.builder_queue/brief_suite_fix1_asm_examples.md`). It is mechanical and independent of this question.
