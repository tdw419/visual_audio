# RECEIPT — TEST-COL-1 repo-wide pytest collection sweep: RED, no fix landed

> **SUPERSEDED 2026-09-13** by `systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_GREEN.md`
> (commit lands the fix: rc=0 / 0 errors / 1604 collected). Keep this file for the
> measured RED diagnosis; note that its attribution of the 18 errors to
> `tests/test_bk8`'s `sys.path` insert was refined — see the GREEN receipt § Root
> cause (the binding is created inside `glyph_dispatch/src/dispatch/dispatcher.py`).

- Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:351` (TEST-COL-1, status **OPEN** — unchanged by this run)
- Run: builder cron `af3e62239ce2`, 2026-09-13 ~03:05–03:40 CDT, branch `glyph-transpiler-autoloop`
- Delegation: one `agy` attempt (`.builder_queue/brief_testcol1_collection_sweep.md`),
  29 min, **killed with no DIFF SUMMARY** (its own baseline collect never terminated). Budget used: 1 of 2.
- Working tree at the end of this run: reverted to the pre-run state. Nothing committed except this
  receipt, the repair note, the roadmap status update and the evidence files.

## Verdict

**Gate leg 1 (`pytest --collect-only -q` → exit 0, zero errors) is NOT met. The row stays OPEN.**
The fix path is now fully diagnosed and is one `git apply` + two small edits away; it was not
attempted this tick because the delegation burned the run's budget on an unbounded collection command.

## The exact gate command, measured on the untouched tree

```
/home/jericho/.local/bin/pytest --collect-only -q            # from the repo root
→ rc=3, INTERNALERROR, 11.0 s
```
Raw: `output/TESTCOL1_collect_run1_red.txt`.
Cause: `pixel_interpreter/test_buffer.py` does GPU work **at import** (line 12
`wgpu.gpu.request_adapter(...)`) and calls `exit(1)` at line 66, so `SystemExit` escapes the collector
and aborts the whole run. **Note the file is NOT tracked** — `git check-ignore -v` →
`.gitignore:101:test_*.py  pixel_interpreter/test_buffer.py`. It is local junk; a fresh checkout
does not contain it. It cannot be committed away; it can only be renamed or ignored.

## The row's premise is WRONG — corrected, with evidence

The row says the "21 errors" from `pytest tests/` are a symptom of that one poison file. **They are not.**
Measured this run, `pytest tests/` (bare console script) → `1444 tests collected, 21 errors`, and every
one of the 21 imports a module the poison file does not touch:

**(a) 18 errors — two mutually exclusive `src` packages in one interpreter session.**
`tests/test_bk8_fs_pix_sha256.py:56` builds its search path as
`for _p in (str(_REPO), str(_REPO / "glyph_dispatch"), str(_REPO / "tools")): sys.path.insert(0, _p)`,
so `<repo>/glyph_dispatch` ends up **ahead of** `<repo>`. Line 62 then does
`from src.glyph.glyph_isa_v2 import ...` — `src/glyph/` lives in `glyph_dispatch/src/`, so this import
binds `sys.modules['src']` to `<repo>/glyph_dispatch/src/__init__.py`, whose `__path__` is that one
directory. Every later `from src.utils|src.spatial|src.codec|src.pixel_tokenizer|src.nlp import ...`
in `tests/` then fails with `No module named 'src.<x>'`, because a regular package found first on
`sys.path` wins and its `__path__` is fixed.
Probe (out-of-tree plugin `/tmp/tc1_probe.py`, `pytest_collectreport` printing the binding):
`output/TESTCOL1_sysmodules_src_shadow_probe.txt` — at the moment `tests/test_crc_patch.py` fails,
`sys.modules['src'] = <module 'src' from '.../glyph_dispatch/src/__init__.py'>`.
Causality demo, both orders, same two files, bare pytest, **each module collects fine alone**:
`output/TESTCOL1_src_package_conflict_demo.txt`
- order A `test_bk8_fs_pix_sha256.py` then `test_crc_patch.py` → `15 tests collected, 1 error` (crc_patch ERRORS)
- order B `test_crc_patch.py` then `test_bk8_fs_pix_sha256.py` → `1 test collected, 1 error` (bk8 ERRORS)

Alphabetically `test_bk8…` precedes `test_crc_patch.py`, so in a full `tests/` sweep the glyph lane
wins and the 18 repo-`src` modules lose. This is **not** a `sys.path`-insertion depth issue:
`pythonpath = .` in a root `pytest.ini` and even an absolute `PYTHONPATH=<repo>` both leave the 21
errors intact (measured) — the binding is decided by *which* entry carries a regular `src/__init__.py`
first, not by whether the repo root is present.

**(b) 3 errors — `tests/disabled/*` import tools that do not exist:**
`tools.cognitive_boot_injector`, `tools.layoutgan_saccade_optimizer`, `tools.ollama_discriminator`.
These are a separate, older breakage; the directory name says they are disabled, but pytest still collects them.

## Cause 3 — a repo-wide sweep is unbounded (measured)

`output/TESTCOL1_perdir_collect_timing.txt` (per-directory `--collect-only`, 90 s cap):

| dir | result |
|---|---|
| `tests/` | 3 s — 1444 nodes, 21 errors |
| `tools/` | **timeout at 90 s**, no summary |
| `systems/` | **timeout at 90 s**, no summary |

Plus non-project trees inside the sweep: `venv.broken` (3978 `test_*.py`), `venv` (1185), `lib` (1166
vendored numpy/scipy/sklearn), `initramfs-cognitive` (184), `test_env` (88), and 115 loose root-level
`test_*.py` scratch scripts. A root-wide collect with those trees *and* the poison file excluded did
**not** terminate in >6 min (killed). So the sweep must be **bounded by declaration** (`testpaths`) —
and the declaration must not include `tools/`/`systems/` until the two hangs are diagnosed
(`output/TESTCOL1_testpaths_collect_hang.txt`: testpaths including them → rc=124, no summary at 200 s).

## What the `agy` delegation did (reverted, held)

One attempt: it created root `pytest.ini` (`pythonpath = .`, `testpaths = tests tools systems output
glyph_dispatch pixel_interpreter route_b external deepseek-harness`) and renamed the poison file to
`pixel_interpreter/buffer_probe.py` with a one-line note — both correct per the brief — then launched
its own baseline `pytest --collect-only -q`, which never terminated (its `testpaths` include the two
hanging dirs). Killed at 29 min, reply carried no DIFF SUMMARY. Working-tree changes were reverted
byte-for-byte (`pixel_interpreter/test_buffer.py` restored, 2073 bytes); the `pytest.ini` is held
verbatim at `.builder_queue/held_patches/testcol1_pytest.ini.held` for the next attempt.

## NOT verified this run

- Nothing was changed in any test file; no fix was landed.
- The remaining declared-scope dirs were not measured for collection cleanliness:
  `output/`, `glyph_dispatch/`, `pixel_interpreter/`, `route_b/`, `external/`, `deepseek-harness/`.
- The identity of the import-time hangers inside `tools/` and `systems/` (per-file bisect not run).
- Gate legs 2 and 4 (full-run count/summary; substor + osskel + bk1/bk9/bk11 suites) were not run —
  they are downstream of a green leg 1.

## Next (in order) — see `.builder_queue/REPAIR_PENDING_testcol1_sweep_scope.md`

1. `tests/disabled/*` → `collect_ignore_glob` in a root `conftest.py` (or move the dir out of scope),
   with the measured `tools.*` ImportError per entry. Visible, documented, not a test weakening.
2. The `src` conflict (a) — **needs a design OK because it touches the load-bearing `test_bk8` gate
   file**; the three options and their costs are in the repair note.
3. Bisect the `tools/` and `systems/` collection hangs by file, then fix or exclude each with its
   measured reason. Until then `testpaths` must not include them.
4. Only then: root `pytest.ini` (`pythonpath = .` + a `testpaths` that is measured to terminate) plus
   the poison rename, then legs 2 and 4 of the row's gate.
