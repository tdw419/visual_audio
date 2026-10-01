# Brief — TEST-COL-1, RULING option 3: migrate `test_bk8` to the `glyph_dispatch.` prefix

Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:351` (TEST-COL-1, OPEN).
Ruling (already committed, `8943601`): `.builder_queue/RULING_testcol1_sweep_scope.md` — **read it first**.
Repo: `/home/jericho/projects/zion/projects/visual_audio`, branch `glyph-transpiler-autoloop`.
You implement; the orchestrator re-runs every gate itself afterwards. **Do NOT commit / `git add` / push.**

## Why this shape (do not re-open the decision)

18 `tests/` modules currently fail collection because two mutually exclusive `src` packages fight over
`sys.modules['src']`: `tests/test_bk8_fs_pix_sha256.py:56` inserts `<repo>/glyph_dispatch` at
`sys.path[0]`, so `from src.glyph...` binds `src` to `glyph_dispatch/src/`; the other 17 modules then
cannot import `src.codec` / `src.utils` / `src.spatial` / `src.nlp` / `src.pixel_tokenizer` from `<repo>/src/`.
`import glyph_dispatch.src` already works as a namespace package — **do NOT create
`glyph_dispatch/__init__.py`** (measured: resolves to `glyph_dispatch/src/__init__.py` today).

## Changes in scope (exactly three; nothing else)

1. **`tests/test_bk8_fs_pix_sha256.py` — imports only, spelling-only change.**
   - line 56: drop `str(_REPO / "glyph_dispatch")` from the `sys.path` tuple (keep `_REPO` and `_REPO/"tools"`).
   - line 65: `from src.glyph.glyph_isa_v2 import (...)` → `from glyph_dispatch.src.glyph.glyph_isa_v2 import (...)`
   - line 68: `from src.glyph.sha256_kernel import (...)` → `from glyph_dispatch.src.glyph.sha256_kernel import (...)`
   - Touch **no** assertion, no fixture, no other line. Its collected test-id set must be identical before/after.
2. **NEW root `pytest.ini`** — exactly this shape, with a comment block naming the declared boundary
   and the three measured non-terminating files:
   ```
   [pytest]
   pythonpath = .
   testpaths = tests
   ```
   - `pythonpath = .` closes the console-script `sys.path` gap (bare `pytest` is the py3.12 console
     script; it does not put CWD on `sys.path`).
   - `testpaths = tests` only. Do **NOT** name `tools/` or `systems/` — measured, a `testpaths` that
     includes them **hangs the gate command** (`output/TESTCOL1_testpaths_collect_hang.txt`), which is
     worse than today's abort. Record in comments (with their measured reasons) that
     `systems/infinite_map_rs/test_daemon.py` (module-level `server.accept()`),
     `tools/boot_alpine_opensbi_test.py` (top-level `@numba.njit`) and `tools/test_setup_vm.py` (≥60 s,
     undiagnosed) are outside the sweep, and that recovering `tools/`+`systems/` needs a per-file
     timeout harness (a declared follow-on leg, not part of this row).
   - No `addopts`, no `--ignore` chains, no `collect_ignore_glob`.
3. **Rename** `pixel_interpreter/test_buffer.py` → `pixel_interpreter/buffer_probe.py` (untracked,
   gitignored at `.gitignore:101`; broken GPU scratch probe — `TypeError` in `read_buf.map_async(...)`
   at line 58, no test functions). Add a **one-line** header comment saying why it is no longer in
   collection scope and citing TEST-COL-1. Change nothing else in it.

## Fences (binding)

- Do NOT delete or rewrite any test, weaken any assertion, or edit `tests/conftest.py` / any other
  `conftest.py`. `tests/conftest.py`'s existing `collect_ignore_glob = ["disabled/*"]` stays as-is.
- Do NOT touch `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL shaders,
  or any engine file.
- Do NOT `collect_ignore_glob` away any module that collects cleanly — no leg may pass by narrowing scope.
- If a `tests/` module still errors after the change, report the measured error **verbatim**; leave it alone.

## Gates YOU must run and paste raw (orchestrator re-runs them anyway)

- **G1** `/home/jericho/.local/bin/pytest --collect-only -q` → **rc 0, zero errors**, record wall-clock.
  (Today: rc 3 `INTERNALERROR` from the poison file; `python3 -m pytest tests/ --collect-only -q` → rc 2, 18 errors.)
- **G2** `/home/jericho/.local/bin/pytest -q` — full run of the declared scope: report **total collected
  count** + pass/fail summary, time-boxed. If it exceeds ~15 min, report how far it got and that it was
  truncated — never silently narrow it.
- **G3** test-id set of `tests/test_bk8_fs_pix_sha256.py` unchanged (run `--collect-only -q` before/after
  and diff), and `/usr/bin/python3 -m pytest tests/test_bk8_fs_pix_sha256.py -q` → **15 passed**.
- **G4** no collateral, all green: `/usr/bin/python3 -m pytest tests/test_substor_boot_witness.py -q` (5 passed) ;
  `/usr/bin/python3 -m pytest tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q` ;
  `/usr/bin/python3 -m pytest tests/test_gh9_loader.py tests/test_bk11_coreutils.py tests/test_bk1_argv.py -q`.

## Report back

`state (green/red per gate)` / `evidence (raw command + tail of output per gate)` / `files changed`
(in-scope only) / `what you did NOT verify`. Terse — the orchestrator re-runs everything itself.
