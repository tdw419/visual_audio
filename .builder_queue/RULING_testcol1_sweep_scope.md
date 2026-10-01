# RULING — TEST-COL-1: take option 3, prerequisite refuted by measurement

**Date:** 2026-09-13 · **Seat:** orchestrator · reversible: Jericho may override any line.

## Decision: option 3 — migrate test_bk8 to the `glyph_dispat...[truncated]
## Decision: option 3 — migrate `test_bk8` to the `glyph_dispatch.` prefix

**Why option 3, and why the ticket's prerequisite is void:**

1. `python3 -c "import glyph_dispatch.src"` **works on this tree today** — namespace package,
   resolves to `glyph_dispatch/src/__init__.py`. **No new `__init__.py` is needed**; do NOT create one.
2. The prefix style is already this repo's convention: `tools/verify_glyph_dispatch_mmio.py` imports
   `glyph_dispatch.src...`. Option 3 aligns the gate with the existing convention.
3. Scale is smaller than estimated: `tests/test_bk8_fs_pix_sha256.py` has **2** glyph import
   statements (lines 65, 68) plus the `sys.path` insert at 56-62 — not ~10.
4. Options 1 and 2 both leave the ambiguity in place (hybrid `__path__`; subprocess-scoped binding)
   while editing a load-bearing 15-leg gate. Option 3 removes the second `src` binding outright.

## Verification protocol (all five, or the row stays RED)

- (a) `test_bk8`'s collected **test-id set is identical** before/after (proves spelling-only change).
- (b) `tests/test_bk8_fs_pix_sha256.py` — **15 legs pass**.
- (c) `pytest tests/ --collect-only -q` → **rc=0, zero errors**, and the **collected count reported**
      (today: rc 2, 18 errors). No leg may pass by narrowing scope.
- (d) The arc / regression suite green at the same HEAD, no new failures.
- (e) No collateral: `tests/test_substor_boot_witness.py` 5 passed unchanged.

**Fallback rule:** if (a)-(d) are not achievable after **2 attempts**, STOP and file with the measured
failure. Do **not** silently fall back to option 1's hybrid `__path__` — that needs a new ruling.

## Sweep boundary (leg 1's scope, declared not assumed)

- **testpaths = `tests/` only.** `tools/` and `systems/` are OUT: collection does not terminate there,
  a `testpaths` that names them **hangs the gate command**, which is worse than the abort.
- The 3 measured hangers are recorded as exclusions with reasons, never hidden:
  `systems/infinite_map_rs/test_daemon.py` (module-level `server.accept()` — scratch server),
  `tools/boot_alpine_opensbi_test.py` (top-level `@numba.njit` JIT),
  `tools/test_setup_vm.py` (≥60 s, cause undiagnosed).
- **Follow-on leg (not part of leg 1):** a per-file timeout harness over tools/ + systems/ so that
  coverage is recovered without letting one file hang the sweep.
- Poison-file rename approved: `pixel_interpreter/test_buffer.py` → `buffer_probe.py` (untracked,
  `.gitignore:101`; it is a GPU scratch probe, not a test).
- Already done and accepted: `tests/disabled/*` excluded via `collect_ignore_glob` (`893ded6`),
  files still collectable individually (not hidden).
