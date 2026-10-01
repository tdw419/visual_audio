# TICKET SUPPLY STATE — ADDENDUM 334 (2026-09-20, builder cron af3e62239ce2)

Status: **SUPPLY LANDED — RULING_ps008 effectuated.** Monitor wake
(ceaaba8a → f4f34fba) was the RULING landing; the fork that held the PS
lane since addendum 329 is RESOLVED and the un-HOLD was executed the
same tick.

## What landed (commit e649cddf, 6 files, exactly the ruling's steps 1-6)

1. `tools/pyshader_fde.py` `execute_one`: taken branch now `pc + imm//4`
   (SPEC, +1 dropped). Docstrings updated.
2. FIB word 6: `0xFE0296E3` → `0xFE0298E3` (BNE x5,x0,-16 — the
   ruling's corrected word; decode-verified fmt=B imm=-16 rs1=5).
3. `tests/test_pyshader_fde.py`: step-3 polarity/bounds re-pinned to
   SPEC arithmetic + an old-convention regression guard; FIB pins
   UNCHANGED (42 steps, x3 seq 2,3,5,8,13,21,34,55, final 34/55/55/0)
   — exactly as the ruling predicted.
4. `tests/test_pyshader_ctl.py::test_ps008_cross_executor_branch_agreement`
   — the PS009 composition pre-gate: per-step taken/not-taken identity
   plus full-FIB step-count/final-register/entire-regfile equality
   across both executors; discriminates vs pc+1+imm//4 (old convention
   lands pc=3, asserted !=).
5. `RULING_ps007_fib_branch_offset.md`: dated SUPERSEDED addendum
   (original text preserved — audit trail).
6. `GPU_CPU_EMULATOR_ROADMAP.md` PS008 row: "papered over" paragraph →
   RESOLVED pointer. `REPAIR_PENDING_ps008_branch_convention_vs_ps007.md`
   marked RULED (not deleted).

## Evidence (RED first, per ruling step 3)

- RED (old executor + new word): `IndexError: fetch: pc 7 out of bounds
  (imem len 7)` at the FIB gate — taken branch landed pc=7, SPEC target
  2. Tail pasted in commit e649cddf.
- GREEN: `tests/test_pyshader_fde.py + tests/test_pyshader_ctl.py` →
  **30 passed / 1.04s**; wider re-measure +compiler → **96 passed /
  2.49s**, rc=0, at e649cddf.
- Scope check: `git status` filtered — only the 6 in-scope files in the
  commit; the other ~18 tracked-dirty files are Qoder BM lane / guest
  churn, untouched.

## State after this tick

- PS008 fork: CLOSED. PS009 eligibility condition (both suites green on
  SPEC convention + cross-executor agreement test) is SATISFIED.
- **Next row: PS009 — still INELIGIBLE for execution** (J-DECISION,
  GPU_CPU_EMULATOR_ROADMAP.md:67 — Jericho's seat on the ≥5x-deficit
  continue/stop call). This loop does NOT self-promote past it.
- SE021: ~96th hold, BLOCKED-ON-JERICHO (maildrop md5 unchanged).
- Qoder BM lane: dirty set untouched, per lane split.

## What this addendum does NOT prove

- The pixel-CPU cross-validation leg was not re-run under the new word
  (wgpu smoke lane, unchanged code path — not exercised this tick).
- No end-to-end GPU execution of the full FIB program exists anywhere
  yet (GPU legs remain per-class samples; PS009's composition is the
  row that changes that, and it waits on Jericho).
