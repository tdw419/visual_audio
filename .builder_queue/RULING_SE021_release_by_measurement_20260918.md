# RULING — SE021 blocker RELEASED by measurement (premise false at HEAD)

**Status:** EFFECTIVE 2026-09-18 (policy D-1 of POLICY_decision_delegation_20260918.md: blocker premise measured false → close the blocker).
**Ruled by:** host session under Jericho's delegation directive of 2026-09-18. This is a release-by-measurement, not an option pick: the gate clause's own condition is satisfied.
**Supersedes:** the holding state enforced since the maildrop was posted 2026-09-16 03:00 CDT.

## The measurement

`/usr/bin/python3 -m pytest tests/test_glyph_app_glyph_on_glyph.py -v -p no:randomly` at HEAD `4fb0ff9b`, 2026-09-18 14:3x CDT:

```
test_exec_leg_child_output_appears            PASSED
test_control_returns_to_shell_after_exec      PASSED
test_allowlist_deny_loud_and_no_child_output  PASSED
test_dispatch_regression_green_with_exec_neutral PASSED
4 passed in 0.57s
```

`test_control_returns_to_shell_after_exec` — the exact leg the maildrop cites as "RED 38 consecutive" — passes. The BRIEF's definition of done required "the gate conjunction is green at a committed HEAD"; it is green at a committed HEAD (and has been reported green in builder addenda 182–306's BROADER conjunctions: "17 passed", which includes this file, every tick since 09-17). The blocker held anyway because no one re-measured the premise against the maildrop's claim. Premise false → blocker void.

## What released it (honest attribution)

Not a single fix: the roadmap's own SE021 notes record the view-merge work ("syscall space inventory, some already fixed via _read_path view-merge, in flight") landing between 09-16 and 09-17, after which the builder's addenda quietly reported the conjunction green while the maildrop hold counter kept incrementing (~68 holds). The hold outlived its own trigger. Recorded as a policy lesson: every hold re-measures its trigger before counting a new tick.

## Consequences (bound and scoped)

- SE021 glyph-on-glyph exec (RUN 0x07) is UNBLOCKED as roadmap supply: the builder may claim TASK_SE021 under the standard gates.
- **Scope limit:** this releases the EXEC feature to proceed, and releases the hold. It does NOT pick design option (a)-variant/(b)+/(c)/GH-25 where those remain genuinely discretionary — the roadmap's scoping pass (63c1cbd, memory-view unification) already recorded the structural recommendation (A)-scoped-to-handlers; the builder proceeds under THAT recorded recommendation unless measurement at implementation time forces otherwise, and files a DEFECT if it does.
- The oracle tests (4 legs) are the regression gate; any landing that turns one RED re-blocks the row immediately.
- Option (b)'s layout-assert caution from the RCA stands as implementation guidance (runner-path overlap), not a gate.

## What this PASS does not prove

It does not prove GPU/WGSL parity for RUN (no GPU leg ran); it does not prove the JZ-style 51-file blast radius is safe — that remains the implementation row's obligation under its own gates; it does not retroactively adjudicate the 38-tick RED history (the RCA file stands as the record of that investigation).
