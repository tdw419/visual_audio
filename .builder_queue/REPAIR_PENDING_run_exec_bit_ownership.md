# REPAIR_PENDING — who owns the exec bit for a RUN target? (ruling-level, seat the lane)

**Filed:** 2026-09-13 by builder cron `af3e62239ce2`, from the `4863635` regression repair
(`systems/RECEIPT_RUN_CONTAINMENT_ORCHESTRATOR_REPAIR.md`).
**Status:** OPEN — design question, **not** a mechanical patch. The regression itself is repaired; this asks what the
repaired shape should be as policy.

## The gap, measured

`RULING_run_syscall_containment.md` decision 4 removed the guest's `os.chmod(path, 0o755)`, and decision 2/3 made RUN
default-deny with a realpath allowlist. Both landed at `4863635`. Measured consequence (my own run, RED-first):

```
[SYSCALL] RUN failed: [Errno 13] Permission denied: '/tmp/.../spoken_driver.py'
tests/test_glyph_orchestrator_speak_to_driver.py:94: AssertionError: RUN did not actually execute the spatially-written driver
```

The handler still execs `[path]` directly (`shell=False`), so an allowlisted path **also** needs the exec bit — meaning
the operator must now grant two things (allowlist entry + mode) and the ruling names only one. The end-to-end flow
"speak a script into existence and run it" can only work if the operator pre-provisions the path's mode, because
`FILE_WRITE` and `RUN` happen inside a single `cpu.run()` and the guest may no longer chmod. The regression repair
adopts the operator-pre-provisioned reading (mirroring the ruling's own note at `:48-49` that the pinned test chmods its
own temp script), and its receipt §6 states the reduced reach explicitly. That reading is a **reading**, not a ruling.

## Options, cheapest first

**(a) Document the requirement only** — no code change; the operator-set exec bit is policy by consequence of decision
4. Cost: 0 lines. Risk: a denied RUN is indistinguishable from a missing file in the operator's experience, which is
what made this regression expensive to attribute (two causes, one message).

**(b) Make the requirement loud** — on `PermissionError` the handler's existing one-line refusal names the cause
(`RUN failed: <path> is not executable (mode 0644); GLYPH_RUN_ALLOW grants execution, not the exec bit`). ~5 lines in
`_handle_syscall`'s RUN branch, no ABI change, no new grant. Discriminating gate: a mode-0644 allowlisted target yields
the named reason, and the reason text changes if the mode assertion is neutered. **Recommended** — it turns the silent
half of a two-cause failure into a diagnosis.

**(c) RUN execs via an interpreter when the exec bit is absent** — `sys.executable <path>` for allowlisted `.py`
targets. Changes `argv[0]`/`argv` semantics that decision 5 pinned (`[path]`, `cwd=dirname`), and makes exec-ness
irrelevant for those targets, so the operator's grant weakens from "this file may run" to "this path may be
interpreted". Cost ~10 lines + ABI/lang questions (what is a `.py`? what about ELF?).

**(d) Narrow guest chmod inside the allowlist** — let the guest set the exec bit only for a path it just wrote and only
when already allowlisted. Reverses decision 4 in part. Highest blast radius; needs an explicit ruling because decision 4
was itself a defect fix ("an execute syscall has no business changing host permissions").

## What a ruling must settle

1. Is the operator's grant one fact (the path may run) or two (the path may run **and** the operator keeps the mode)?
2. If two, must the refusal name which one is missing (option b)?
3. Does any flow need the guest to produce a runnable artifact from nothing — and if so, is that capability worth
   reversing decision 4 for (option d)?

## Pointer

Repaired consumer: `tests/test_glyph_orchestrator_speak_to_driver.py` (2 legs: granted end-to-end + default-deny).
Ruling: `.builder_queue/RULING_run_syscall_containment.md` (whose `:29-35` "breaks zero existing tests" premise is
**falsified** — see receipt §2). Landed containment gate: `tests/test_run_containment.py`.
