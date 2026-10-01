# REPAIR_PENDING — TEST-COL-1: how to make the repo-wide collection sweep clean and bounded

> **RESOLVED 2026-09-13** (builder cron `af3e62239ce2`) — moved to `.builder_queue/resolved/`.
> Ruling `RULING_testcol1_sweep_scope.md` chose **option 3**; measurement then **refuted its premise**
> (dropping `test_bk8`'s `sys.path` insert left all 18 errors). The binding is created *inside*
> `glyph_dispatch/src/dispatch/dispatcher.py` (which inserted `glyph_dispatch/` at `sys.path[0]`,
> hijacking the top-level name `src` process-wide), so the fix landed at that source: package-relative
> imports inside `glyph_dispatch/src` + `test_dispatch.py` on the same `src.` prefix.
> Result: `pytest --collect-only -q` **rc=0, 0 errors, 1604 collected** (was 1444 collected then
> aborted). Full chain, gates, boundary and residual hazards: `systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_GREEN.md`.
> The two options this ticket listed as needing Jericho's ruling (hybrid `src.__path__`) were **not**
> needed and were not taken.

Filed by builder cron `af3e62239ce2`, 2026-09-13. Full evidence:
`systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_RED.md`, raw artifacts in `output/TESTCOL1_*`.
Held config: `.builder_queue/held_patches/testcol1_pytest.ini.held` (a root `pytest.ini`).

## Design question (needs Jericho's ruling — option 2 only)

The sweep cannot be made clean without resolving **two mutually exclusive `src` packages** inside one
interpreter session:

- `tests/test_bk8_fs_pix_sha256.py:56-62` needs `src.glyph.*`, which lives in `glyph_dispatch/src/`
  (it puts `<repo>/glyph_dispatch` on `sys.path` and imports `from src.glyph.glyph_isa_v2 import ...`).
- 18 other `tests/` modules need `src.utils`, `src.spatial`, `src.codec`, `src.pixel_tokenizer`,
  `src.nlp`, which live in `<repo>/src/`.

Whichever import runs first binds `sys.modules['src']` and its `__path__` is fixed, so the other side
fails to collect. Measured both ways in `output/TESTCOL1_src_package_conflict_demo.txt`: each module
collects alone; together, exactly one of the pair errors.

### Options

1. **Per-module path extension inside `test_bk8` (cheapest, 3 lines, no assertion change).**
   Make `<repo>` the first entry so `src` binds to the repo package, then
   `import src; src.__path__.append(str(_REPO / "glyph_dispatch" / "src"))` so `src.glyph` still
   resolves for the glyph lane. Cost: edits a load-bearing gate file (test_bk8, 15 legs) —
   must re-run its gate + the arc. Risk: a future importer of `src.db` semantics could be surprised.
2. **Session isolation for `test_bk8` (no shared-path coupling).** Run the glyph-lane import inside a
   subprocess (`pytest` already proves subprocess isolation for similar cases). Cost: restructures
   test_bk8's import convention; medium.
3. **Migrate `test_bk8`'s imports to the `glyph_dispatch.` prefix**
   (`from glyph_dispatch.src.glyph...`) and drop the `glyph_dispatch` sys.path insert. Cost: touches
   ~10 import lines + every `patch()`/fixture reference in that file; most invasive, but removes the
   second `src` entirely. Needs `glyph_dispatch/__init__.py` to exist (check first).
4. **Declare the 18 repo-`src` modules out of the sweep** (collect_ignore_glob). Rejected as a
   default: they are real tests of the `src/` codec stack and the row forbids hiding a cause; only
   acceptable if Jericho rules the `src/` stack itself deprecated.

Also mechanical and independent of the ruling:
- `tests/disabled/*` (3 errors: `tools.cognitive_boot_injector`, `tools.layoutgan_saccade_optimizer`,
  `tools.ollama_discriminator` do not exist) → `collect_ignore_glob` entry with the measured ImportError,
  or move the directory out of collection scope. The directory is already named "disabled".
- `tools/` and `systems/` collection does **not terminate** (>90 s each, no summary) — bisect by file,
  then fix or exclude each hanger with its measured reason. A `testpaths` that includes them makes the
  gate command hang (`output/TESTCOL1_testpaths_collect_hang.txt`), which is worse than the abort.
- Then land the held `pytest.ini` (`pythonpath = .` + a `testpaths` measured to terminate) and the
  poison rename (`pixel_interpreter/test_buffer.py` → `buffer_probe.py`; the file is untracked junk,
  `git check-ignore` → `.gitignore:101`), and run legs 2 and 4 of the row's gate.

## UPDATE 2026-09-13 (cron `af3e62239ce2`, head `893ded6`) — two of the mechanical items are done

**(a) `tests/disabled/*` — fixed and committed** (`893ded6`). `tests/conftest.py` now carries
`collect_ignore_glob = ["disabled/*"]` with the three measured import errors written next to it.
Measured on this tree: `pytest tests/ --collect-only -q` went from **rc=2 / 21 errors** to
**rc=2 / 18 errors**, with **0** of the remaining errors from `tests/disabled/`. The files are not
hidden — `pytest tests/disabled/test_ollama_discriminator.py --collect-only -q` still collects and
still errors (rc=2, 1 error). No collateral: `tests/test_bk8_fs_pix_sha256.py` 15 passed,
`tests/test_substor_boot_witness.py` 5 passed.

**(b) hanger bisect — measured** (`systems/RECEIPT_TESTCOL1_HANGER_BISECT.md`; raw
`output/TESTCOL1_hanger_bisect.txt`, `output/TESTCOL1_hanger_reprobe60.txt`). 113 candidate files
under `tools/` + `systems/`, per-file `--collect-only` under a 12 s timeout: 26 OK / 47 no-collect /
29 error / **11 exceeded 12 s**. Re-probed at 60 s, only **3 do not terminate**:
`systems/infinite_map_rs/test_daemon.py` (module-level `server.accept()` on
`/tmp/spatial_compositor.sock` — it is a scratch server, not a test module),
`tools/boot_alpine_opensbi_test.py` (top-level `@numba.njit` JIT at import),
`tools/test_setup_vm.py` (≥60 s, cause not diagnosed). The other 8 are slow, not hung — they
terminate in 12–46 s collecting zero tests.

**Consequence:** the held `pytest.ini` cannot name `tools/`/`systems/` wholesale; any sweep
declaration must exclude those 3 (or run them under a timeout harness) and state the boundary.
The sweep-boundary call and the `src`-conflict options remain **Jericho's** — unchanged by this
update.
