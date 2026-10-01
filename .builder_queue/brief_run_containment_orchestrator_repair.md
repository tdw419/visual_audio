# BRIEF — repair the RUN-containment regression in `tests/test_glyph_orchestrator_speak_to_driver.py`

**Roadmap row:** `SUITE-FIX-1` (line 355), the file is one of cluster (2)'s consumers; the regression is from `4863635`.
**Spec pointer (read first):** `.builder_queue/RULING_run_syscall_containment.md` — decisions 2 (default deny via env
`GLYPH_RUN_ALLOW`, colon-separated absolute paths, unset/empty = deny all), 3 (exact match on `realpath`), 4 (drop
`os.chmod`), 6 (refusal is a return, not an exception).
**Measured regression (mine, this tick — do not re-litigate):** sweeping `tests/` at HEAD `4863635` shows
`tests/test_glyph_orchestrator_speak_to_driver.py` **PASS → FAIL**, 1 collected / 0 passed / 1 failed:
```
[SYSCALL] AUDIO_IN: 143 bytes ... [SYSCALL] FILE_WRITE: 143 bytes ...
[SYSCALL] RUN denied: /tmp/.../spoken_driver.py not in GLYPH_RUN_ALLOW
tests/test_glyph_orchestrator_speak_to_driver.py:83: AssertionError: assert '0o664' == '0o755'
```
Two independent causes, both from that commit: (a) RUN is now default-deny and this consumer never grants itself, so
the driver is never executed; (b) `:83` asserts the `0o755` chmod side effect that ruling decision 4 **deliberately
removed**. The ruling's "enabling finding" (`:29-35`) claimed a default-deny allowlist "breaks **zero existing tests**"
— it inspected only `tests/test_glyph_run_program.py`; this file was missed. That premise is now **falsified**; record it
in your report, do NOT edit the ruling file.

## Files in scope

**Positive — the ONLY file you may modify:**
1. `tests/test_glyph_orchestrator_speak_to_driver.py`

**Negative — do NOT touch:** `tools/glyph_isa_v2.py` (the containment handler is LOCKED and landed),
`glyph_dispatch/**`, `tests/test_run_containment.py` (the ruling's own gate), `tests/test_glyph_run_program.py` (pinned
encoding test — must stay byte-identical and pass with no opt-in line added), `.builder_queue/RULING_run_syscall_containment.md`.

If a leg is red for a reason **outside the one in-scope file**, STOP and report the literal output.

## Required behaviour (keep the end-to-end coverage; weaken nothing)

1. **Keep the chain**: AUDIO_IN → FILE_WRITE → RUN → marker file, all inside `GlyphCPUv2`, host Python only for inputs.
2. **Grant explicitly** (the ruling's mechanism, and the "operator grant" this test is): set `GLYPH_RUN_ALLOW` to the
   driver script's `os.path.realpath` for the duration of the leg (monkeypatch the env or save/restore it in a
   `try/finally`). Do **not** weaken or delete the RUN coverage: `marker_path.exists()` and its content assertion must
   remain, i.e. the driver really executes.
3. **Delete `:83`'s `0o755` assertion** (it asserts the side effect the ruling removed) and replace it with an assertion
   of the ruling's actual guarantee — the guest did **not** set the mode to `0o755`. Keep the byte-equality assertion at `:84`.
4. **NEW second leg (the discriminating one — a repair that cannot fail is not a repair):**
   `test_speak_a_driver_run_is_default_denied` — the same program **with `GLYPH_RUN_ALLOW` unset/empty**: the script is
   still written and byte-exact, but `marker_path` **must NOT exist**, and the handler's denial must be observable
   (e.g. the `RUN denied` line on stdout, captured with `capsys`). This leg proves the ported leg's success depends on
   the grant rather than on a vacuous RUN.
5. No `pytest.skip`/`xfail`, no assertion deleted except the one named in (3), no `shell=True`, no network.

## Gate — run these exact commands; each must exit 0

```
/usr/bin/python3 -m pytest tests/test_glyph_orchestrator_speak_to_driver.py -q
/usr/bin/python3 -m pytest tests/test_glyph_orchestrator_speak_to_driver.py tests/test_run_containment.py tests/test_glyph_run_program.py -q
```

Gate clause (falsifiable):
- **PASS** ⇔ the file reports **2 passed** (the granted end-to-end leg + the default-deny leg) and the three-file run is
  green with `tests/test_run_containment.py` and `tests/test_glyph_run_program.py` unmodified.
- **REFUSE**: fewer than 2 legs; a deleted `marker_path` assertion; a `skip`/`xfail`; any edit outside the one in-scope file.
- **Non-vacuity**: the new default-deny leg must be RED if the grant it removes is instead left in place (i.e. show that
  your leg fails when the env is still set), and the granted leg must be RED with the env unset. Record both.

Failure evidence (RED-first, already measured by the orchestrator at HEAD `4863635`, quote it verbatim):
`1 failed in 0.21s` — `assert '0o664' == '0o755'` with `[SYSCALL] RUN denied: … not in GLYPH_RUN_ALLOW`.

## Interfaces are LOCKED + definition of done

**Interfaces LOCKED:** the 0x07 syscall's ABI (r1 = path_addr, r7 = 7, return = exit code or -1) and the
`GLYPH_RUN_ALLOW` policy are fixed by the ruling; this brief changes a test, not the handler.
**Definition of done:** both gate commands exit 0 with the counts above; the ruling's own gate and the pinned encoding
test unmodified and green; RED-first + both non-vacuity results pasted into your report.

## Do NOT commit

Do **NOT** `git commit`, `git add`, `git checkout`, `git stash` or `git reset`. Leave the tree dirty.

## Report back (literal)

1. Both gate commands with their literal tails.
2. The two non-vacuity results (granted leg with env unset → RED; default-deny leg with env set → RED).
3. DIFF SUMMARY: files changed, line counts.
4. The falsified-premise sentence for the receipt, in your own words, and anything you did NOT verify.
