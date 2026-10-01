# BRIEF — implement RULING_run_syscall_containment: 0x07 SYSCALL_RUN default-deny allowlist

## Spec pointer (READ THIS FIRST)

`.builder_queue/RULING_run_syscall_containment.md` — it is the spec, not this brief's summary.
The handler under change is `tools/glyph_isa_v2.py` lines ~1143-1157 (`_handle_syscall`, branch
`elif syscall_num == 0x07`). Current code: reads guest path, `os.path.isfile` check,
`os.chmod(path, 0o755)`, `subprocess.run([path], cwd=parent_dir, timeout=30, capture_output=True)`,
returns `res.returncode`.

## Scope

POSITIVE (may change — nothing else):
- `tools/glyph_isa_v2.py`: the 0x07 branch only, plus two small module-level helpers
  (allowlist parse + injectable runner indirection). No other syscall branch.
- `tests/test_run_containment.py`: NEW file (must be created).

NEGATIVE (must NOT change):
- `tests/test_glyph_run_program.py` — do not edit it, do not add an opt-in line to it.
- No ABI/encoding change: r1 = path_addr, r7 = 7, return = exit code or -1, unchanged.
- No `os.chmod` anywhere in the handler.
- No new dependencies, no sandbox/namespace/seccomp work, no network policy, no change to
  `tools/geos_caps.py` or any other file. Interfaces are LOCKED.

## Gate command

```
/usr/bin/python3 -m pytest tests/test_run_containment.py tests/test_glyph_run_program.py -q 2>&1 | tail -20
```
EXPECTED: exit 0, 9 passed, 0 failed (8 containment legs + 1 pinned test). Report the exit code.

## Gate clause (falsifiable)

`tests/test_run_containment.py` must contain distinct tests for each leg, by name:
- **L1 allowed path runs** — path is in the allowlist → the injected runner double is called
  exactly once with `argv == [path]`, and the returned rc is the double's rc.
- **L2 default deny** — `GLYPH_RUN_ALLOW` unset OR empty string → returns -1 AND the runner
  double is never called (call count == 0).
- **L3 not-allowlisted** — file exists and is executable (chmod by the TEST, not the handler)
  but is not in the allowlist → returns -1, runner never called. THIS LEG IS THE
  DISCRIMINATING CHECK: it must FAIL on the pre-fix code.
- **L4 no prefix smuggling** — allowlist `/tmp/x/ok.py`; requesting `/tmp/x/ok.py/../evil.py`
  or `/tmp/x/ok2.py` both deny (realpath equality, no prefix match, no glob).
- **L5 no chmod** — target mode 0o644: `stat().st_mode` identical before and after the call,
  with the runner double in use.
- **L6 pinned test unchanged** — `tests/test_glyph_run_program.py` passes unmodified.
- **L7 refusal is a return** — denial yields -1, exactly one reason line naming the cause,
  and NO exception propagates out of the handler.
- **L8 invariant** — the 0x07 handler source contains no `shell=True` and no `os.chmod`.

REQUIRED IMPLEMENTATION SHAPE (from the ruling):
1. Keep `shell=False`, list argv, `timeout=30`, `capture_output=True`,
   `cwd=os.path.dirname(os.path.abspath(path))`, return `res.returncode`.
2. Allowlist from env `GLYPH_RUN_ALLOW`, colon-separated ABSOLUTE paths. Unset/empty = deny all.
3. Exact match on `os.path.realpath(...)` of both sides. No prefixes, no globs.
4. Refusal = `return -1` + one print line; never raise.
5. Make the spawn injectable: module-level indirection over `subprocess.run` (e.g.
   `_RUNNER = subprocess.run` plus a `_spawn(argv, cwd, timeout)` helper that calls `_RUNNER`)
   so a test can monkeypatch it and count calls WITHOUT spawning a process. Keep the
   imports valid — the branch's `except (OSError, subprocess.SubprocessError, Exception)`
   must still resolve `subprocess` (import it at module level if it is not already).

## Failure evidence (mandatory, RED FIRST)

1. Write `tests/test_run_containment.py` FIRST against the CURRENT unfixed handler and run the
   gate command. Paste the literal failing tail. At minimum L3 (and L5, since `os.chmod` is live)
   must be RED here — if they are not, your doubles/tests are vacuous and the harness is wrong.
2. Only then implement the handler change, and paste the literal PASSING tail with the exit code.
3. State in your final message which legs you did NOT run and what the green does NOT prove.

## Rules

- **Do NOT commit.** The orchestrator verifies the gate itself and commits.
- Do not weaken or delete any existing test to make a leg pass.
- Work only inside this repo. If a locked interface looks wrong, do not change it: report a
  design conflict and stop.
