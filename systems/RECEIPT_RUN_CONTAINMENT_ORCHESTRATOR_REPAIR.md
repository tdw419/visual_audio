# RECEIPT — repair of the RUN-containment regression in `test_glyph_orchestrator_speak_to_driver.py`

**Date:** 2026-09-13 · **Builder cron:** `af3e62239ce2` · **Branch:** `glyph-transpiler-autoloop`
**Regression source:** `4863635` (`fix(syscall): 0x07 SYSCALL_RUN is default-deny`) — found by this tick's row-gate sweep, not by that landing.
**Sibling receipt:** `systems/RECEIPT_SUITE_FIX1_OLLAMA_MEMORY_DRIFT.md` (§5 names the discovery).
**In-scope file (one):** `tests/test_glyph_orchestrator_speak_to_driver.py` · **Brief:** `.builder_queue/brief_run_containment_orchestrator_repair.md`

## 1. The regression, measured

Per-file sweep attribution (`output/SUITE_FIX1_C3B_SINK.jsonl` → `output/SUITE_FIX1_C34_SINK.jsonl`, both at 256/257 files):

| file | before `4863635` | at `4863635` |
|---|---|---|
| `tests/test_glyph_orchestrator_speak_to_driver.py` | PASS (1/1/0) | **FAIL** (1/0/1) |

```
[SYSCALL] RUN denied: /tmp/.../spoken_driver.py not in GLYPH_RUN_ALLOW
tests/test_glyph_orchestrator_speak_to_driver.py:83: AssertionError: assert '0o664' == '0o755'
```

## 2. Two causes, and the premise the ruling got wrong

1. **Default deny with no opt-in.** The consumer never granted itself a `GLYPH_RUN_ALLOW` entry, so RUN was denied.
2. **`:83` asserted the removed side effect.** It required `0o755` — precisely the `os.chmod` that
   `RULING_run_syscall_containment.md` decision 4 deleted.

The ruling's enabling finding (`:29-35`) states a default-deny allowlist *"breaks **zero existing tests**"*. **That is
falsified**: it inspected only `tests/test_glyph_run_program.py`, and the arc selector does not collect this file, which
is why the landing's arc run was green while the tree was red. The ruling file was **not** edited.

## 3. My own brief was wrong too (recorded, not hidden)

The brief told the delegate to replace the `0o755` assertion with "the mode is NOT `0o755`". The delegate implemented it
faithfully and reported success — **my re-run was RED**:

```
[SYSCALL] RUN failed: [Errno 13] Permission denied: '/tmp/.../spoken_driver.py'
tests/test_glyph_orchestrator_speak_to_driver.py:94: AssertionError: RUN did not actually execute the spatially-written driver
1 failed, 1 passed in 0.20s
```

Cause: with the chmod gone, the target has no **exec bit**, so `execve` refuses it. "Mode is not 0o755" is not the same
claim as "the flow still works" — the second cause was invisible until the allowlist was satisfied. **The delegate's
claim of a green gate was not evidence; the orchestrator's re-run was.**

## 4. The repair (operator grants, both asserted)

Implemented by the orchestrator under the loop's fallback rule (the delegate's one attempt for this defect was spent and
its result was red), following the pattern the ruling itself names at `:48-49` ("the test chmods its own temp script"):

1. **Operator grant #1 — the exec bit.** `_run_speak_to_driver_pipeline` touches the target path and sets `OPERATOR_MODE
   = 0o741` **before** `cpu.run()`. The guest still supplies every content byte (`FILE_WRITE` opens the existing path, so
   the operator's mode survives), and both legs assert `stat.S_IMODE(...) == OPERATOR_MODE` — **a resurrected guest
   chmod would rewrite that mode and be caught**. The mode is deliberately not `0o755` so the assertion discriminates.
2. **Operator grant #2 — the allowlist.** The end-to-end leg sets `GLYPH_RUN_ALLOW` to the target's resolved path.
3. **NEW leg `test_speak_a_driver_run_is_default_denied`:** the same program with `GLYPH_RUN_ALLOW` unset — script
   written and byte-exact, **marker must NOT exist**, and the `[SYSCALL] RUN denied` line must appear on stdout.
4. Module docstring updated to state what the host must now supply and why.

## 5. Gate (all runs the orchestrator's own)

| step | command | result |
|---|---|---|
| RED, pre-repair | `pytest tests/test_glyph_orchestrator_speak_to_driver.py -q` at `fd9b4e0` (delegate's port) | **1 failed, 1 passed** — `[Errno 13]` |
| GREEN | same, after grant #1 | **2 passed in 0.21 s** |
| leg 1 alone | `-k end_to_end` | 1 passed, 1 deselected |
| leg 2 alone | `-k default_denied` | 1 passed, 1 deselected |
| 3-file gate | `pytest tests/test_glyph_orchestrator_speak_to_driver.py tests/test_run_containment.py tests/test_glyph_run_program.py -q` | **11 passed in 0.27 s** (the ruling's own gate + the pinned encoding test unmodified) |

**Non-vacuity, two independent probes, both restored byte-identical (`md5sum -c` OK):**

| probe | mutation | result |
|---|---|---|
| P1 | remove the `touch()`+`chmod(OPERATOR_MODE)` pre-provision | **RED** — `RUN failed: [Errno 13] Permission denied` (the exec grant is load-bearing) |
| P2 | make the default-deny leg grant the path instead | **RED** — `assert not marker_path.exists()` → `assert not True` (the allowlist is load-bearing) |

## 6. HONEST BOUNDARY — what this PASS does not prove

- The flow's **reach is reduced by the ruling, by design**: the guest can no longer turn a path it invents into an
  executable. This test now proves the *content* is fully guest-derived while *existence + mode + permission to run* are
  operator grants. That is the blast-radius reduction, not a test artifact — but it does mean the original
  "speak a driver into existence, executable by the guest" claim is **no longer true and no longer tested**.
- No ruling covers **who** must set the exec bit; the answer here (the operator, mirroring the ruling's own note about
  the pinned test chmodding itself) is this ticket's reading. If the lane wants RUN to exec non-executable allowlisted
  paths through an interpreter, that is an ABI change and needs a ruling — filed as
  `.builder_queue/REPAIR_PENDING_run_exec_bit_ownership.md`.
- `OPERATOR_MODE = 0o741` is asserted on both legs, but only with the owner exec bit set; other-mode combinations,
  sticky bits and ACLs were not probed.
- The 4 TIMEOUT files and cluster (4)'s remaining files were not touched; the RUN handler itself was not modified.
- The sweep is the row gate; no arc leg (this file is not in the arc selector), no WGSL leg.
