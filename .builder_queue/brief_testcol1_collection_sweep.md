# Brief — TEST-COL-1: restore a clean, bounded repo-wide pytest collection sweep

Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:352` (TEST-COL-1; the row's state cell now reads closed).
Repo: `/home/jericho/projects/zion/projects/visual_audio`, branch `glyph-transpiler-autoloop`.
You implement; the orchestrator re-runs every gate itself afterwards. **Do NOT commit.**

**Status: LANDED — do not run this file as live work.** The row closed 2026-09-13 (`039ce3b`): the sweep
landed as a root `pytest.ini` (`pythonpath = .`, `testpaths = tests`, the three measured hangers named in
comments) plus the poison-file rename `pixel_interpreter/test_buffer.py` → `buffer_probe.py`. The landed
shape is **narrower** than this brief's "chosen fix shape" — the sweep is bounded to `tests/` only, and
recovering `tools/` + `systems/` became the follow-on row `SUITE-ISO-1` (also closed). The file is kept as
the RED-first record and as the statement of the ruling's gate legs. If the row ever reopens, re-brief it;
do not re-run this one.

## Files in scope (positive half)

The only files this brief authorizes:

1. `pytest.ini` (repo root, **NEW**) — `pythonpath = .` plus a `testpaths` declaration naming real project
   dirs, with a comment block naming what is intentionally outside the sweep and pointing at the receipt.
2. `pixel_interpreter/test_buffer.py` → `pixel_interpreter/buffer_probe.py` — **rename only**, plus one
   header comment citing TEST-COL-1. No other line of that file changes.
3. `conftest.py` (repo root, **NEW, conditional**) — only if a module **inside the declared scope** still
   errors at import, each `collect_ignore_glob` entry carrying its measured error text as justification.
4. `output/TESTCOL1_*` — evidence records only; no test logic lives there.

Nothing else may change. The "## Fences (binding)" section below is the negative half of this scope and is
equally binding.

**Definition of done:** legs L1–L4 evidenced with literal command output; `pytest --collect-only -q`
rc=0 with zero errors and the collected count reported **with its delta** against today's 0; the poison
file renamed with a cited header comment; no test file deleted and no assertion weakened.
**Interfaces LOCKED:** this round adds configuration and one rename; it alters no Python signature.

## The gate command (exactly this invocation, run from the repo root)

```
/home/jericho/.local/bin/pytest --collect-only -q
```

Note: bare `pytest` is the console script `/home/jericho/.local/bin/pytest` with shebang
`#!/usr/bin/python3` → py3.12 + `/home/jericho/.local/lib/python3.12/site-packages`. It is NOT
the same as `python3 -m pytest` (that resolves to the Hermes venv py3.11), and it is NOT the same
as `/usr/bin/python3 -m pytest` (module invocation puts CWD on `sys.path`, the console script does not).

## Gate legs (each must be evidenced with raw output)

- **L1** `pytest --collect-only -q` exits **0** with **zero** collection errors, in bounded time
  (record wall-clock; target ≤ 5 min). Paste the exit code and the final summary line.
- **L2** Record the **total collected count** and the **pass/fail summary of a full run** of the
  declared scope (`pytest -q`, time-boxed by the harness). Report the delta versus today's count
  (**today = 0 collected**, the run aborts). If the full run exceeds ~15 min, report exactly how far
  it got, which node ids it reached, and that it was truncated — do not silently narrow it.
- **L3** State, with a measurement, what happened to the poison file
  `pixel_interpreter/test_buffer.py` (see "chosen fix shape" below).
- **L4** No regression — all of these must be green after your change:
  `pytest tests/test_substor_boot_witness.py -q` ; `pytest tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q` ;
  `pytest tests/test_gh9_loader.py tests/test_bk11_coreutils.py tests/test_bk1_argv.py -q`.
  Use `/usr/bin/python3 -m pytest` for these (the interpreter the loop's receipts already use).

## Measured facts from this run (do not re-derive; verify only if a gate leg points at them)

1. **RED, reproduced:** `pytest --collect-only -q` from the repo root → exit **3**, `INTERNALERROR`,
   ~11 s. Cause: `pixel_interpreter/test_buffer.py` does GPU work **at import** — line 12
   `wgpu.gpu.request_adapter(...)`, and line 66 `exit(1)` inside its `except` block. pytest imports
   the module during collection, the `SystemExit` escapes the collector and aborts the ENTIRE run.
   Raw red is saved at `output/TESTCOL1_collect_run1_red.txt`.
2. **The row's stated hypothesis is WRONG; record the correction.** The row says the "21 errors"
   from `pytest tests/` are a symptom of that one poison file. Measured this run: `pytest tests/`
   (bare console script) exits 2 with `Interrupted: 21 errors during collection`, and **all 21 are
   local-import failures, none of them the poison file**: 17 × `ModuleNotFoundError: No module named
   'src.<pkg>'` (`src/` DOES exist at the repo root — `codec/ nlp/ spatial/ geos/ ...`) plus
   `tests/disabled/` modules importing missing `tools.*` modules
   (`tools.cognitive_boot_injector`, `tools.layoutgan_saccade_optimizer`, `tools.ollama_discriminator`).
   Root cause: the console-script invocation does not put the repo root on `sys.path`; `python3 -m pytest`
   does — which is exactly why the loop's `/usr/bin/python3 -m pytest` arc runs were green.
3. **The root sweep is unbounded today** — it recurses non-project trees:
   `venv.broken` (3978 `test_*.py`), `venv` (1185), `lib` (1166 vendored numpy/scipy/sklearn),
   `initramfs-cognitive` (184, an initramfs image), `test_env` (88), `.venv_test` (88), plus
   **115 loose `test_*.py` scripts at the repo root** (one-off scratch probes; `find . -maxdepth 1
   -name 'test_*.py' | wc -l` = 115). Measured: a root-wide `--collect-only` with the junk trees and
   the poison file excluded **did not terminate in > 6 min** (killed after 6 min, no node ids emitted).
   So the sweep must be **bounded by declaration**, not blacklisted item by item.
4. `pixel_interpreter/test_buffer.py` is **not runnable standalone**:
   `/usr/bin/python3 pixel_interpreter/test_buffer.py` → exit **1** with
   `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'function'`
   in `read_buf.map_async(wgpu.MapMode.READ, map_callback)` (stale wgpu API). It has no test functions.

## Chosen fix shape (the orchestrator's decision — implement exactly this, do not improvise a different shape)

**One decision: declare the sweep scope explicitly and move the poison file out of collection scope.
No test file is deleted, and no test assertion is touched.**

1. **NEW** root `pytest.ini`:
   - `pythonpath = .`  → fixes cause 2 (the console-script `sys.path` gap) so the 17 `src.*` modules
     and the resolvable `tools.*` modules import; previously-hidden tests therefore collect (that is L2's delta).
   - `testpaths = tests tools systems output glyph_dispatch pixel_interpreter route_b external deepseek-harness`
     → bounds cause 3. Include every top-level project directory that actually contains tests; check the
     tree and adjust only by *adding* real project dirs. Add a short comment block naming what is
     intentionally outside the declared sweep (`venv.broken`, `venv`, `lib`, `initramfs-cognitive`,
     `test_env`, `.venv_test`, the loose root-level `test_*.py` scratch scripts) and pointing at the
     receipt.
   - Do NOT add `addopts`, `-p no:...`, `--ignore` chains, or anything else that hides a cause.
2. **Rename** `pixel_interpreter/test_buffer.py` → `pixel_interpreter/buffer_probe.py`
   (satisfies L3's "moved/renamed out of collection scope" branch: it is a broken scratch probe, not
   a test — measured, see fact 4). Add the renamed file a **one-line** header comment saying why it is
   no longer collected and citing TEST-COL-1. Change nothing else in that file.
3. If — and only if — a module **inside the declared scope** still errors at import, add a root
   `conftest.py` with a `collect_ignore_glob` list where **each entry carries the measured error text
   as its justification**. Never ignore a module that collects cleanly. (Fact 1's file is handled by
   the rename; a second conftest entry for it is not needed.)

## Fences (binding)

- Do **not** delete or rewrite any test file, weaken any assertion, or edit `tests/conftest.py` /
  `output/conftest.py` to make collection succeed.
- Do **not** touch `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL
  shaders, or any engine file — this row is test infrastructure only.
- Do **not** widen scope to the `tests/disabled/` modules' missing `tools.*` imports; if they remain
  collection errors after `pythonpath = .`, report them with the measured error and leave them alone
  (they are a separate defect, name it in your report so the orchestrator can file it).
- Do **not** `git commit`, `git add`, or push. Leave the tree dirty for the orchestrator.

## Report back

`state (green/red per leg)` / `evidence (raw command + tail of output for each leg)` / `files changed`
/ `what you did NOT verify`. Keep it terse — the orchestrator re-runs the gates itself.
