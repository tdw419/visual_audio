# RECEIPT — SE021 interpreter-resolution guard (REPAIR_PENDING option 1 landed)

**Landed 2026-09-17 (builder cron `af3e62239ce2`, orchestrator-implemented).**
Ticket: `.builder_queue/REPAIR_PENDING_se021_spawn_interpreter_resolution.md`
(filed addendum 147, 2026-09-16 22:0x). Option **1 (test-side only)** —
the option the ticket itself lists cheapest-first, with "No engine lines".

## Hold condition re-measured before acting

The ticket held because "the engine file is the exec-shell lane's active WIP
surface". That condition is stale: the lane's work is committed and is an
ancestor of HEAD —

- `d009e0c` 09-16 07:47 feat(SE021): green gate — RUN2 (0x12), _read_path view-merge, layout v5.1
- `fd24c76`..`e898bc2` 09-16 (d) handler series 1..5 — SYSCALL 0x01/0x04/0x03/0x08/0x09 dests migrate to RAM (this IS the RCA's option (a′), landed)
- `cd119fd` 09-17 00:30 fix(engine): BUG A — FAULT_PC packed-PC units (last engine touch, 02:00 prior to this run)

The engine surface is no longer WIP; option 1 touches `tests/` only, so the
hold no longer applies.

## RED reproduced first (guard absent)

```
PATH=/home/jericho/br_scratch/buildroot/output/host/bin:$PATH \
  /usr/bin/python3 -m pytest tests/test_glyph_app_glyph_on_glyph.py -q
2 failed, 2 passed
FAILED ...::test_exec_leg_child_output_appears
FAILED ...::test_control_returns_to_shell_after_exec
E  AssertionError: ['ERR:RUN_DENIED', ' hello']
```
Buildroot host python3.14 (`.../br_scratch/buildroot/output/host/bin/python3`)
has no numpy (`ModuleNotFoundError: No module named 'numpy'` measured
directly) → runner shebang `#!/usr/bin/env python3` resolves to it → runner
rc=1 → `ERR:RUN_DENIED`, the containment-failure signature, for an
environment reason.

## The guard (tests/test_glyph_app_glyph_on_glyph.py, fixture `child_env`)

Before building the child, probe `shutil.which("python3")` with
`python3 -c "import numpy"`; on failure `pytest.skip("environment: python3
on PATH (<py>) lacks numpy; glyph_child_runner shebang would resolve to it
and die rc=1")`. Also skips when no python3 on PATH at all. No engine line,
no assertion changed, no leg deleted.

## GREEN pair

- Pinned PATH (`PATH=/usr/bin:$PATH`): **4 passed** (0.54 s) — gate unchanged on a sane host.
- Hostile PATH: **1 passed, 3 skipped** with the named environment reason
  (`:168/:182/:198`), exit 0 — legs refuse to masquerade an environment
  artifact as a containment failure (`output/se021_opt1_hostile_path.txt`).

## Non-vacuity (the guard must be able to fail)

Probe `output/probe_se021_opt1_nonvacuity.py`: neuters the skip branch
(`if _probe.returncode != 0 and False:`), re-runs under hostile PATH,
restores the file byte-identically (md5 `95ec76ab5ea7d8be2650fde6e1e84fd1`
before == after), ALWAYS-restores in `finally`.
Result `output/se021_opt1_nonvacuity_neutered_RED.txt`: neutered →
**2 failed / 2 passed** with `['ERR:RUN_DENIED', ' hello']`, RUN2 line
"exit code 1". The guard is discriminating: present = honest skip, absent =
the original red.
PROBE DEFECT LOGGED in the artifact: two probe iterations mis-captured the
verdict (stderr flush order; then the FAILURES banner regex) and printed
`red=False` while the run was genuinely red — probe-flag bug only, RED real
in every iteration.

## What this PASS does NOT prove

- The containment mechanism itself is NOT re-proven here — leg 3
  (allowlist-deny + non-vacuity) is the SE021 lane's own evidence
  (`d009e0c`); this run only re-measured it green at HEAD.
- No WGSL/GPU leg exists for the RUN path.
- Option 1 does not make the runner work under a numpy-less PATH — it makes
  the gate REFUSE TO LIE about it. Runner hardening (option 2) or
  engine-side interpreter pinning (option 3, needs ruling) remain open if
  the exec legs should PASS on any host.
- n=1 per leg, single host.
