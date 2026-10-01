# RECEIPT — TEST-COL-1 hanger bisect (why `tools/` and `systems/` cannot be swept whole)

**Date:** 2026-09-13 · **Builder cron:** `af3e62239ce2` · **Branch:** `glyph-transpiler-autoloop`
**Head at measurement:** `d4d359d` (bisect) / `893ded6` (re-probe) — the re-probe commit adds
`tests/conftest.py`'s `collect_ignore_glob` for `tests/disabled/` only; it does not touch
`tools/` or `systems/`.
**Status:** TEST-COL-1 stays **OPEN**. This receipt closes only the "measure the hangers"
sub-item that `REPAIR_PENDING_testcol1_sweep_scope.md` lists as *mechanical and independent of
the ruling*. The `src`-package conflict (18 errors) and the sweep-boundary declaration are
unchanged.

## Question

`REPAIR_PENDING_testcol1_sweep_scope.md` recorded that collecting `tools/` and `systems/` does
not terminate (>90 s each, no summary). A held root `pytest.ini` whose `testpaths` includes
those trees would turn an 11 s collection abort into an unbounded hang for every session on
this branch. Which files are responsible, and are they slow or non-terminating?

## Method

- Candidate set: every `test_*.py` / `*_test.py` under `tools/` and `systems/` —
  **113 files** (`.builder_queue/tcol_hanger_bisect.sh`, list saved to `/tmp/tcol_cands.txt`).
- Per file: `/usr/bin/python3 -m pytest --collect-only -q <file>` under `timeout 12`.
- Second pass on the 11 files that exceeded 12 s: same command under `timeout 60`
  (`.builder_queue/tcol_hanger_reprobe.sh`).
- Scripts write only `output/TESTCOL1_hanger_bisect.txt` and
  `output/TESTCOL1_hanger_reprobe60.txt`; no tracked file was modified by the measurement.

## Result — 113 files at a 12 s bound

| status | count |
|---|---|
| OK (collected ≥1 test) | 26 |
| NOCOLLECT (rc=5, 0 tests collected) | 47 |
| ERR (rc≠0/5/124) | 29 |
| exceeded 12 s | 11 |

Slow-but-not-flagged at 12 s (8–11 s, all NOCOLLECT or ERR): `systems/virtio_pixel_rs/test_varying_data.py` (9 s),
`tools/test_alpine_virtio_fix.py` (9 s, rc=2), `tools/test_boot_trace_kernel.py` (11 s),
`tools/test_kernel_exception_trace.py` (11 s).

## Result — the 11 flagged files at a 60 s bound

| status | elapsed | file |
|---|---|---|
| **NOTERM60** | 60 s | `systems/infinite_map_rs/test_daemon.py` |
| **NOTERM60** | 61 s | `tools/boot_alpine_opensbi_test.py` |
| **NOTERM60** | 60 s | `tools/test_setup_vm.py` |
| NOCOLLECT | 46 s | `tools/test_boot_probe.py` |
| NOCOLLECT | 46 s | `tools/test_dtb_isa.py` |
| NOCOLLECT | 34 s | `tools/test_kernel_exception.py` |
| NOCOLLECT | 30 s | `tools/test_a2.py` |
| NOCOLLECT | 16 s | `tools/test_ollama_analyzer.py` |
| NOCOLLECT | 13 s | `tools/test_setup_vm_pt.py` |
| NOCOLLECT | 13 s | `tools/test_setup_vm_pt2.py` |
| NOCOLLECT | 12 s | `tools/test_pg_dir.py` |

So 8 of the 11 are **slow, not hung** — they terminate in 12–46 s and collect zero tests.
Only 3 files fail to terminate within 60 s, and those 3 are what makes whole-tree collection
unbounded.

## Measured cause (2 of the 3, from source — not inferred)

- `systems/infinite_map_rs/test_daemon.py` — not a pytest module at all: top-level code binds an
  AF_UNIX socket at `/tmp/spatial_compositor.sock` and calls `server.accept()`
  (`systems/infinite_map_rs/test_daemon.py:12-15`) before any test object exists. Collection blocks
  on `accept()` forever.
- `tools/boot_alpine_opensbi_test.py` — module-level `import numba` plus a top-level `@numba.njit`
  on a function (`tools/boot_alpine_opensbi_test.py:1-12`); JIT compilation happens at import, so a
  bare `--collect-only` pays compile cost before collecting anything.
- `tools/test_setup_vm.py` — not diagnosed beyond the 60 s non-termination; its siblings
  `test_setup_vm_pt.py` / `test_setup_vm_pt2.py` terminate in 13 s with 0 collected, so the cost
  is likely the same heavy import path, but the non-termination itself is **not** explained here.

The 8 NOCOLLECT files share a shape: heavy imports (VM/DTB/spatial-CPU/ollama stack) executed at
import time, then no `test_` functions — they buy seconds of sweep time and contribute no tests.

## Consequence for the held `pytest.ini`

A `testpaths` that names `tools/` or `systems/` wholesale is **not** declarable as terminating.
Any sweep declaration that wants those trees must either list the 11 files above as excludes (or
run them under a per-file timeout harness), or drop the two trees from the sweep and say so in the
documented boundary. That decision is the sweep-scope question already parked in
`REPAIR_PENDING_testcol1_sweep_scope.md` — this receipt is the measurement it asked for, not the
ruling.

## What was NOT verified

- Whether `tools/test_setup_vm.py` terminates at a bound longer than 60 s (only "≥60 s" is measured).
- Why the 8 NOCOLLECT files collect zero tests (they import a heavy stack and define nothing
  collecting; not inspected line by line).
- Whether any flagged file *passes* when run normally — only collection was measured.
- The 18 residual `src`-package-conflict errors and the sweep-boundary/`pytest.ini` decision:
  untouched, still parked for Jericho.
