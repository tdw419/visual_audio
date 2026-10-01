# NOTE — two follow-ups measured while landing TEST-COL-1 (2026-09-13, cron `af3e62239ce2`)

Status: **latent / non-blocking.** Written as a NOTE (not a `REPAIR_PENDING_*` blocker) so the
monitor's open-ticket count keeps meaning "a red gate is waiting". Landed with `039ce3b`.

## 1. `glyph_dispatch`'s own lane tests can re-create the `src` shadow

The TEST-COL-1 fix removed the *library's* `sys.path` side effect
(`glyph_dispatch/src/dispatch/dispatcher.py` and the two `offload/` modules now import
package-relatively). But the lane's **test/bench** files still do the old thing:

- `glyph_dispatch/tests/test_item2_dispatch_sha256.py:24`, `test_item3_mmio_bridge.py`,
  `test_item3b_shader_mmio.py`, `test_item5b_wgsl_parity.py`, `test_sha256_dispatch.py`,
  `glyph_dispatch/bench/bench_*.py` — each inserts `glyph_dispatch/` (or `glyph_dispatch/src`) at
  `sys.path[0]` and imports top-level `src.*`.

Consequence (measured, not inferred): in a session that collects `tests/` **and**
`glyph_dispatch/tests/`, the first one of those modules to run re-binds `sys.modules['src']` to
`glyph_dispatch/src`, and the 17 repo-`src` modules fail with `ModuleNotFoundError: No module named
'src.<pkg>'` again. Today this is invisible only because `pytest.ini` declares `testpaths = tests`
and the lane's files sit outside it.

Fix shape (same migration already applied to `test_dispatch.py`): keep the `glyph_dispatch/` root on
`sys.path` and import through the `glyph_dispatch.` / `src.` package prefix, or run those files
per-file/out-of-process. Also measured and pre-existing, unrelated to this hazard:
`glyph_dispatch/tests/test_dispatch.py` 5 failures (`glyph_dispatch/src/db/wordbase.db` missing) and
2 collection errors from `No module named 'tests.mock_ram'`.

## 2. The full `tests/` run does not complete inside 25 minutes

Row TEST-COL-1's leg 2 asks for a full-run pass/fail summary. Measured on the green tree
(`/home/jericho/.local/bin/pytest -q`, `testpaths = tests`):

- 1604 collected in 2.0 s (collection is fixed and fast).
- **4% (≈70 of 1604) after 4 min 20 s of runtime**, with 9 failures already (`F..FF.FFF…`), i.e. an
  extrapolated ~100 min for the whole suite. The run was time-boxed to 1500 s and left to write
  `/tmp/tc1_full.txt`; the next tick can read it, but the row's own gate leg 2 is **met only as
  "count + truncated progress"**, not as a complete pass/fail summary — reported as such in
  `systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_GREEN.md`.

Implication for the declared follow-on leg (per-file timeout harness): it must cover **`tests/`
too**, not just `tools/` + `systems/` — the sweep is clean but not yet *timed*, so "the suite is
green" remains unprovable in one command.
