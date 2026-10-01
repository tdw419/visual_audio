# RECEIPT — SUITE-FIX-1 cluster (2): real handlers for the GlyphCPUv2 file/audio/run syscalls

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` → SUITE-FIX-1, cluster **(2) “Syscall stubs”**.
**Branch:** `glyph-transpiler-autoloop`. **Pre-fix head:** `9f62ee7`. **Interpreter/PATH pinned:** `/usr/bin/python3`, `PATH=/usr/bin:$PATH`.
**Author of the numbers below:** the orchestrator (builder cron `af3e62239ce2`) — every verdict is my own re-run, never the delegate’s claim.
**Implementation:** delegated to `agy` (`.builder_queue/brief_suite_fix1_syscall_stubs.md`, exit 0 / 150 s,
log `output/agy/agy_impl_20260913_173301.log`). Gate, probes, sweep, arc and commit: orchestrator.

## What was wrong (measured at `9f62ee7`, before any edit)

`GlyphCPUv2._handle_syscall` (`tools/glyph_isa_v2.py:1034`) declared 0x03/0x04 in its own docstring while both
branches were **print-only stubs that returned 0 without touching the filesystem** (`:1072`, `:1080`), and
`0x07`/`0x08`/`0x09` fell through to `[SYSCALL] UNKNOWN` (`:1107`). Three baseline-FAIL files were red for exactly
this reason — `[SYSCALL] FILE_WRITE: … (stub)`, `UNKNOWN: syscall_num=0x08`, `UNKNOWN: syscall_num=0x09`,
`UNKNOWN: syscall_num=0x07`.

## RED before (my run, HEAD `9f62ee7`) — `output/suite_fix1_syscall_stubs_RED_prefix.txt`

```
$ /usr/bin/python3 -m pytest tests/test_glyph_file_io.py tests/test_glyph_audio_io.py tests/test_glyph_orchestrator_speak_to_driver.py -q
FAILED tests/test_glyph_file_io.py::test_syscall_file_write_read  — AssertionError: File not created: /tmp/tmp99ugp5q8/spatial_test.txt
FAILED tests/test_glyph_file_io.py::test_syscall_file_read_not_found — AssertionError: FILE_READ should return -1 for missing file (assert 0 == -1)
FAILED tests/test_glyph_audio_io.py::test_syscall_audio_io — AssertionError (test_out.wav never created)  [SYSCALL] UNKNOWN: syscall_num=0x08
FAILED tests/test_glyph_orchestrator_speak_to_driver.py::test_speak_a_driver_end_to_end — AssertionError
        [SYSCALL] UNKNOWN: 0x09 · [SYSCALL] FILE_WRITE: -1 bytes … (stub) · [SYSCALL] UNKNOWN: 0x07
4 failed in 0.24s
```

## GREEN after (my run)

| leg | command | result |
|---|---|---|
| conjunction (gate) | `/usr/bin/python3 -m pytest tests/test_glyph_file_io.py tests/test_glyph_audio_io.py tests/test_glyph_orchestrator_speak_to_driver.py -q` | **4 passed in 0.24s, exit 0** |
| file I/O alone | same file 1 only | 2 passed |
| audio I/O alone | same file 2 only | 1 passed |
| orchestrator chain alone | same file 3 only | 1 passed |
| engine consumers | `pytest tests/test_gh4_wgsl_parity.py tests/test_bk2_wgsl_syscall_parity.py tests/test_gh18_syscall_abi.py tests/test_gh21_posix_shim.py tests/test_bk1_argv.py tests/test_bk11_coreutils.py -q -m "not live_smoke"` | **37 passed, 1 deselected, 31.12 s** |
| arc leg A | `SEED=2026091318 PATH=/usr/bin:$PATH suite_sweep.sh -b 12G -w 4 -- bash tools/arc_lega.sh` | **rc=0, crashes=0, 323 passed / 1 skipped / 9 deselected, 67.02 s**, `oom_kill_delta=0`, peak 820 MB |

## Non-vacuity (my probe, not the delegate’s word)

`.builder_queue/probe_suite_fix1_syscall_nonvacuity.py` — neuters one behaviour at a time in the landed file, runs the
corresponding leg, restores the file, and requires the restore to be byte-identical:

```
repo file md5 before: 0fcb4aa90204b8ab04e20d3eef8cd20b
PROBE FILE_READ-missing-must-return--1: rc=1 RED (expected)          # `return -1` → `return 0` on not-found
PROBE AUDIO_IN-must-decode-and-write-back: rc=1 RED (expected)       # decode+writeback skipped
repo file md5 after:  0fcb4aa90204b8ab04e20d3eef8cd20b  identical=True
PROBE RESULT: PASS (both probes discriminate, file restored)
```

## Row gate: the pinned SUITE-BASE-1 command, before vs after

`PATH=/usr/bin:$PATH suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 --sink …`

| run | files | collected | PASS | FAIL | TIMEOUT | wall |
|---|---|---|---|---|---|---|
| pinned baseline (`output/SUITE_BASE1_LOCK_SINK.jsonl`, head `594f647`) | 256 | 1608 | 235 | 17 | 4 | 468.54 s |
| **this change** (`output/SUITE_FIX1_C2_SINK.jsonl`, head `9f62ee7`) | **256** | **1610** | **240** | **12** | **4** | **467.17 s** |

Per-file delta (`.builder_queue/probe_suite_fix1_c2_sinkdiff.py`, all 256 records compared key-by-key):

```
test_glyph_audio_io.py                     FAIL->PASS  {coll 1, 1 failed} -> {coll 1, 1 passed}   ← this change
test_glyph_file_io.py                      FAIL->PASS  {coll 2, 2 failed} -> {coll 2, 2 passed}   ← this change
test_glyph_orchestrator_speak_to_driver.py FAIL->PASS  {coll 1, 1 failed} -> {coll 1, 1 passed}   ← this change
test_spatial_ide.py                        FAIL->PASS  {coll 8, 8 failed} -> {coll 8, 8 passed}   ← SUITE-FIX-1 leg 1a (`3b71c46`)
test_supply_census.py                      FAIL->PASS  {coll 5, 1 failed} -> {coll 7, 7 passed}   ← SUITE-CENSUS-1 (`539d418`)
```

**No file regressed** (no PASS→FAIL, no file left or entered the denominator; the +2 collected is
`test_supply_census.py`’s two new legs from `539d418`).

## Mechanism (`tools/glyph_isa_v2.py`, +119/−8)

Function-local imports, no top-level dependency added, `_handle_syscall` signature and calling convention untouched:

- `0x03` FILE_WRITE — r1=path, r2=data, r3=len → host write of exactly `len` bytes; `0` / `-1`.
- `0x04` FILE_READ — r1=path, r2=dest, r3=max_len → writes back, returns the **actual count**; missing file **`-1`**.
- `0x07` RUN — r1=path → `os.chmod(path, 0o755)` then `subprocess.run([path], cwd=parent, timeout=30, capture_output=True)`; returns the child exit code; `-1` if not a regular file. No `shell=True`.
- `0x08` AUDIO_OUT — bytes → `Phy16Tone.encode` → int16 wav at `Phy16Tone.SAMPLE_RATE`; `0` / `-1`.
- `0x09` AUDIO_IN — wav → `Phy16Tone.decode`, truncated to max_len, written to memory; returns the decoded count.
- Paths are read as NUL-terminated strings from image memory (`_read_path`, 4096-byte cap); every handler is non-raising (`except` → `-1`).

## What the PASS does NOT prove

- **`0x07` RUN is a host-execution capability** (the emulated CPU asks the host hypervisor to execute a host path). It is
  what `tests/test_glyph_orchestrator_speak_to_driver.py` demands, so it is not new *trust* at the ABI level — but it is a
  real trust boundary and the loop has not been given a ruling on it; a login-shell-free, `shell=False`, 30 s-bounded
  `subprocess.run` is the implementer’s parameter, not a policy. Flagged to Jericho (near-escalation entry this tick).
- No sandboxing of any kind: paths are whatever the emulated program wrote into memory, including absolute host paths.
- The AUDIO format is whatever `Phy16Tone` round-trips at int16; no other sample rate, channel count, or wav variant was tried.
- The `except (OSError, Exception)` tuple is redundant (it swallows all exceptions); a genuine programming error inside a
  handler therefore surfaces as `-1` rather than a traceback. Deliberate (non-raising was required), but noted.
- No WGSL leg: these syscalls exist in the Python engine only; `GlyphCPUv2 ≡ WGSL` parity is not asserted for them.
- The three gate files are **untracked** in git (`.gitignore`’s `test_*.py` rule); this commit force-adds them so the gate
  artifact is versioned. Their content was not otherwise audited.
- The remaining SUITE-FIX-1 clusters are untouched: (1b) wordbook is BLOCKED-ON-DESIGN
  (`.builder_queue/REPAIR_PENDING_suite_fix1_wordbook_db_drift.md`); clusters (3) and (4) remain red (12 FAIL files in
  the sweep above).

## Pre-existing guard debt found while landing (must be reported, not bypassed)

The repo's pre-commit hook (`.git/hooks/pre-commit` → `glyph_dispatch/tools/run_precommit_check.sh:32`) requires
`coreutils`-style byte-identity between `tools/glyph_isa_v2.py` and its mirror
`glyph_dispatch/src/glyph/glyph_isa_v2.py` (`cmp -s`), and **that guard was already RED at HEAD `9f62ee7`**:
`git show HEAD:glyph_dispatch/src/glyph/glyph_isa_v2.py` is missing the DEFECT-18 tick-register snapshot hunk that
landed in `tools/glyph_isa_v2.py` at `11fe1ac` (`git show --stat 11fe1ac` → that commit touched only the
`tools/` copy; the mirror's last commit is `00391e2`, BK-6). The hook therefore refused this commit until the mirror
was brought back into sync — a guard correctly blocking a landing that would have widened the divergence.

The fix here is **satisfy the guard, never bypass it** (`--no-verify` was not used): the mirror was refreshed
verbatim with `cp`, which lands *both* this change and the outstanding DEFECT-18 hunk into the dispatch lane.
Evidence (`cmp` byte-identical, md5 `0fcb4aa9…` on both paths):

- dispatch lane's collectable tests before **and** after the sync: `6 failed, 5 passed` (the 6 are the pre-existing
  `sqlite3.OperationalError` failures — missing `glyph_dispatch/src/db/wordbase.db`; the 2 `tests.mock_ram`
  collection errors pre-date this change, cf. `systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_GREEN.md`) — **no delta**;
- the hook's own differential suite, run by me before committing: `pytest $(git ls-files 'tests/test_rv64i_to_glyph*.py' 'tests/test_glyph_isa_v2.py') -q` → **37 passed in 43.78 s**.

## Artifacts

- brief `.builder_queue/brief_suite_fix1_syscall_stubs.md` (validator: `PASS (1 checked, 0 invalid, 0 with warnings)`)
- RED prefix `output/suite_fix1_syscall_stubs_RED_prefix.txt`
- probe `.builder_queue/probe_suite_fix1_syscall_nonvacuity.py`; sink diff `.builder_queue/probe_suite_fix1_c2_sinkdiff.py`
- sweep sink `output/SUITE_FIX1_C2_SINK.jsonl` (256 records), arc `output/suite_fix1_c2_arc_lega.txt` + `output/arc_lega_seed2026091318_9f62ee7.{txt,json}`
- delegate log `output/agy/agy_impl_20260913_173301.log`
