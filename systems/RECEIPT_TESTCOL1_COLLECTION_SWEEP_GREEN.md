# RECEIPT — TEST-COL-1 GREEN: repo-wide pytest collection restored (clean, declared, bounded)

**Date:** 2026-09-13 · **Seat:** builder orchestrator (cron `af3e62239ce2`) · **Base HEAD:** `8943601`
**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:351` (TEST-COL-1) · **Ruling implemented:** `.builder_queue/RULING_testcol1_sweep_scope.md` (option 3)
**Predecessor (RED):** `systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_RED.md`, `systems/RECEIPT_TESTCOL1_HANGER_BISECT.md`

## Gate result (row gate, `systems/GLYPH_SELF_HOSTING_ROADMAP.md:351`)

| Leg | Requirement | Measured (after) | Measured (before) |
|---|---|---|---|
| 1 | `pytest --collect-only -q` exits **0**, **zero** errors | **rc=0, 0 errors, 1604 tests collected in 2.05 s** (wall 3 s) | rc=2, **18 errors**, run `Interrupted` (console script: rc=3 `INTERNALERROR`) |
| 2 | full-run collected count + pass/fail summary, materially higher | **1604 collected** (delta **+160** vs the 1444 that collected before aborting); full run **did not complete** in the 1500 s box — measured **4% (≈70/1604) after 4 min 20 s**, 9 failures in that prefix, log `/tmp/tc1_full.txt` (see § Full run — reported as truncated, NOT as a pass) | 1444 collected **then aborted** (never a full run) |
| 3 | poison file moved out of collection scope, one-line note | `pixel_interpreter/buffer_probe.py` (renamed from `test_buffer.py`, header note, untracked+gitignored `.gitignore:101`) | `pixel_interpreter/test_buffer.py` executed GPU work at import; aborted the run |
| 4 | no regression: substor / osskel / gh / bk suites | `test_substor_boot_witness.py` **5 passed**; `test_osskel_engine_switch.py`+`test_osskel_aspace_switch.py` **10 passed**; `test_gh9_loader.py`+`test_bk11_coreutils.py`+`test_bk1_argv.py` **16 passed** | same suites green |

Ruling's own legs: **(a)** `test_bk8` collected test-id set **identical** before/after (15 ids, md5 `027a2a5ab732a779030ba83077923086` both sides); **(b)** `test_bk8` **15 passed**; **(c)** whole-sweep collect rc 0 / 0 errors, count reported; **(d)** regression suites green; **(e)** `test_substor_boot_witness.py` 5 passed.

## Root cause (the ruling's premise was refuted by measurement — this is the correction)

The ruling attributed the 18 collection errors to `tests/test_bk8_fs_pix_sha256.py:56` inserting `<repo>/glyph_dispatch` on `sys.path`, and predicted option 3 "removes the second `src` binding outright." **Measured: it does not.** After the spelling-only migration the sweep was still rc=2 with the same 18 errors and 1444 collected.

The real chain:

1. `glyph_dispatch/src/__init__.py:1` imports `.dispatch.dispatcher` (eagerly, by design).
2. `glyph_dispatch/src/dispatch/dispatcher.py:22-24` then did `sys.path.insert(0, glyph_dispatch/)` so that its own `from src.glyph...` imports (lines 26-27) resolved to **glyph_dispatch/src**.
3. That insert is a **process-wide side effect of importing `glyph_dispatch.src`**: the top-level name `src` now resolves to `glyph_dispatch/src` for the whole interpreter session. Any later `import src.codec|spatial|nlp|utils|pixel_tokenizer` fails, because those live in the repo's own `<repo>/src/`. → exactly the 17 `ModuleNotFoundError: No module named 'src.<pkg>'` errors, plus `test_bk8`'s insert as a second, *redundant* source of the same binding.
4. Probe (before fix): `import glyph_dispatch.src.glyph.glyph_isa_v2` → `'src' in sys.modules == True`, bound to `.../glyph_dispatch/src`. After fix: `'src' in sys.modules == False`, and `glyph_dispatch` is **not** on `sys.path`.

## The fix (as landed)

1. **`tests/test_bk8_fs_pix_sha256.py`** — ruling option 3: dropped the `glyph_dispatch` `sys.path` entry; imports now carry the package prefix (`from glyph_dispatch.src.glyph.glyph_isa_v2 import ...`). No `glyph_dispatch/__init__.py` created (namespace package works).
2. **`glyph_dispatch/src/dispatch/dispatcher.py`, `glyph_dispatch/src/offload/glyph_dispatch_host.py`, `glyph_dispatch/src/offload/run_with_glyph_dispatch.py`** — 5 absolute `from src.*` imports become package-relative (`from ..glyph...`, `from ..dispatch...`, `from .glyph_dispatch_host...`) and the `glyph_dispatch/` `sys.path[0]` inserts are removed. Same isolation intent the original comment stated (never the repo-level `tools/` copy), now with **no `sys.path` side effect**. `run_with_glyph_dispatch.py` keeps its `tools/` insert (needed for `qemu_gpu_offload`).
3. **`glyph_dispatch/tests/test_dispatch.py`** — this lane test loaded the dispatcher as a *top-level* `dispatch.dispatcher` module (its `sys.path[0]` = `glyph_dispatch/src`), which a relative-import module cannot be. It now inserts `glyph_dispatch/` and uses the `src.dispatch.*` prefix its sibling tests already use. Same 5 tests, same pre-existing failures (below) — no behaviour change.
4. **NEW root `pytest.ini`** — `pythonpath = .` (bare pytest is the console script and does not put CWD on `sys.path`) and `testpaths = tests`, with the boundary and the three non-terminating files named in comments.
5. **`pixel_interpreter/test_buffer.py` → `pixel_interpreter/buffer_probe.py`** (+ one-line note). It is a broken GPU scratch probe (no test functions; `read_buf.map_async` → `TypeError`), untracked and gitignored.

## No-collateral evidence (measured, same tree)

- `glyph_dispatch/tests/test_dispatch.py`: **5 failed before, 5 failed after** — identical test ids, identical error (`sqlite3.OperationalError: unable to open database file`, `tools/wordbase.py:44`: `glyph_dispatch/src/db/wordbase.db` does not exist). Pre-existing, untouched by this change.
- `glyph_dispatch/tests/test_item2_dispatch_sha256.py`, `.../test_item3_mmio_bridge.py`: **2 collection errors before and after** (`ModuleNotFoundError: No module named 'tests.mock_ram'` — pytest binds `tests` to the repo's `tests/`). Pre-existing.
- `tools/verify_glyph_dispatch_mmio.py`: **4 passed, rc=0** (the library I edited, through its own verifier).
- `glyph_dispatch/src/db/` contains **no** Python modules, so the removed `_GD_ROOT` insert was not load-bearing for `db/` imports.

## Declared sweep boundary (not a hidden exclusion)

- `testpaths = tests` only. `tools/` + `systems/` are **out** and remain **collectable individually**: a `testpaths` that names them hangs the gate command (`output/TESTCOL1_testpaths_collect_hang.txt`).
- Three measured non-terminating files, named in `pytest.ini` comments: `systems/infinite_map_rs/test_daemon.py` (module-level `server.accept()`), `tools/boot_alpine_opensbi_test.py` (top-level `@numba.njit`), `tools/test_setup_vm.py` (≥60 s, undiagnosed).
- **Follow-on leg (not this row):** a per-file timeout harness over `tools/`+`systems/` so coverage is recovered without one file hanging the sweep.

## Residual hazards (filed, not hidden)

1. `glyph_dispatch/tests/*` and `glyph_dispatch/bench/*` still insert `glyph_dispatch/` (or `glyph_dispatch/src`) on `sys.path` and import `src.*`. That is fine for **this** row (they are outside `testpaths`), but a session that collects `tests/` **and** `glyph_dispatch/tests/` in one interpreter can re-introduce the same `src` shadow. The follow-on harness must run them per-file/out-of-process or the lane's tests need the same `glyph_dispatch.` prefix.
2. `pytest.ini` `pythonpath = .` is what lets the **console script** (`/home/jericho/.local/bin/pytest`, py3.12) see `src.*`; `python3 -m pytest` (repo `.venv`, py3.11, no `mcp`) is a different interpreter and is not the row's gate invocation.

## Full run (leg 2) — truncated, reported as such

`/home/jericho/.local/bin/pytest -q` on the green tree (`testpaths = tests`):

- **1604 tests collected in 2.0 s** — collection itself is fixed and fast.
- Runtime: **4% (≈70 tests) after 4 min 20 s**, 9 failures in that prefix (`F..FF.FFF……`), no
  completion before the 1500 s time box. Extrapolated ~100 min for the suite. Log: `/tmp/tc1_full.txt`
  (the run was left to run to its own timeout; the next tick can read the tail).
- Therefore leg 2 is met as **count recorded + full run truncated with its measured reach**, not as a
  complete pass/fail summary. Reason it matters: the suite is now *clean to collect* but not yet
  *timed*, so a one-command "everything is green" claim is still not available — which is exactly
  what the declared follow-on leg (per-file timeout harness) must fix, and it must cover `tests/` too
  (`.builder_queue/NOTE_glyph_dispatch_lane_syspath_and_slow_suite.md` § 2).

## What this receipt does NOT claim

- Not a full-suite *pass* claim: leg 2 records the count and summary; failures inside the full run that are unrelated to collection are reported, not fixed, by this row.
- `tools/`+`systems/` coverage is not restored (declared follow-on leg).
