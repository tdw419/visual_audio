# RECEIPT — DEFECT-24: the live-Ollama draft leg leaves the gating arc (option 1 applied)

**Row:** `DEFECT-24` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md`, promotion commit `4441197`) · **Ticket:**
`.builder_queue/DEFECT-24_arc_live_ollama_gate.json` · **Note:** `.builder_queue/REPAIR_PENDING_arc_live_ollama_gate.md`
**Mechanism ruled twice before this tick (not re-decided here):** `RULING_gh12_gate_determinism.md` option 3 (deterministic
claim in the arc, live draft as non-blocking smoke) + `RULING_arc_determinism_standing.md` (a green that depends on
uncontrolled inputs is not evidence).
**Author of the implementation:** `agy` (`.builder_queue/brief_defect24_live_draft_split.md`,
log `output/agy/agy_impl_20260913_145131.log`, exit 0, 422 s) — then corrected and verified by the orchestrator.
**Every number below is the orchestrator's own re-run** on the merged working tree.

## What changed

| file | change |
|---|---|
| `tests/test_gh18_syscall_abi.py` | the live leg split in two: `test_gh18_admit_syscall_deterministic_end_to_end` (GATING, zero network — pinned tile through the `aa.escalate` seam, the REAL oracle and IR gate still run, in-image re-dispatch verified word-exactly) + `test_gh18_admit_syscall_live_draft_smoke` (`@pytest.mark.live_smoke`, records `output/gh18_live_smoke_<head>.txt`, never gates). `test_gh18_unproven_tile_rejected_table_untouched` gained a second case: `ORACLE_WRONG_TILE` (2*r1 → 12 ≠ 18) must be refused with the table word untouched |
| `tests/test_gh12_escalation.py` | both live legs (`:31`, `:44`) carry `@pytest.mark.live_smoke` (bodies unchanged) |
| `tests/test_arc_determinism_audit.py` (NEW) | AST audit: **L1** no test in the arc selector whose decorator carries `skipif(... _ollama_available() ...)` / whose body calls `_ollama_available()` without `monkeypatch` / whose name denotes a live smoke may lack `live_smoke`; **L2** non-vacuity against a pre-fix fixture; **L3** `tools/arc_lega.sh` still carries `-m "not live_smoke"` |
| `tests/fixtures/arc_determinism_prefix_gh18.py` (NEW) | the pre-fix leg as a fixture source for L2 |
| `tests/test_gh26_emit_admit.py` (orchestrator, after the delegation) | leg 5's GH-18 invariant now runs the subprocess with `-m "not live_smoke"` and asserts the **gating** count (14). Before this edit the invariant asserted `"14 passed"` on an UNFILTERED run — a hardcoded count that would have gone live-model-dependent (or 15 after the split) |

**Correction the orchestrator made to the delegate's work, and why.** `agy` kept the gh26 count green by making the new
smoke leg self-skip unless `-m live_smoke` was passed (`request.config.option.markexpr` introspection in the test body).
That is a guard passing for the wrong reason: the arc's verdict would depend on pytest internals, unfiltered runs would
silently stop exercising the live lane, and the coupling was invisible in the diff. Replaced with the explicit filter in
the *consumer* (`test_gh26_emit_admit.py`), which is the same shape the arc itself uses.

## Gate evidence (orchestrator runs, `/usr/bin/python3 -m pytest`)

| # | command | result |
|---|---|---|
| G1 | `pytest tests/test_gh18_syscall_abi.py tests/test_gh12_escalation.py tests/test_arc_determinism_audit.py -q` (unfiltered — the smoke lane RUNS) | **20 passed**, 10.38 s |
| G2 | `pytest tests/test_gh18_syscall_abi.py -q -m "not live_smoke"` | **14 passed, 1 deselected**, 2.10 s |
| G3 | `pytest tests/test_gh18_syscall_abi.py --collect-only -q -m live_smoke` | **1/15 collected (14 deselected)** — the live lane was not deleted |
| G4 | `pytest tests/test_gh12_autoatlas.py tests/test_gh15_step3_autoatlas.py tests/test_gh26_emit_admit.py -q -m "not live_smoke"` | **17 passed, 1 deselected**, 5.01 s |

**The live lane is genuinely live, not silently skipped:** `output/gh18_live_smoke_4441197.txt` →
`model: qwen2.5-coder:14b / rc: 0 / seconds: 2.77 / outcome: ok`.

## Failure evidence (RED first)

| probe | command | result |
|---|---|---|
| audit vs the REAL pre-fix source (`git show HEAD:tests/test_gh18_syscall_abi.py`, not the delegate's fixture) | `.builder_queue/probe_defect24_orchestrator.py` P1 | flags exactly `REAL_PREFIX_gh18::test_gh18_admit_syscall_via_ingest_end_to_end` |
| audit vs current source with ONLY the marker stripped | same probe P2 | flags exactly the live smoke leg; unmutated control → `[]` |
| connect-guard liveness (the technique the deterministic leg's `connect_attempts == 0` rests on) | same probe P3 | guard fired for `('127.0.0.1', 11434)` — the guard intercepts a real attempt |
| deterministic leg is a real gate, not decoration | `expected=18` → `expected=12` in the leg, then `pytest ... -k deterministic -m "not live_smoke"` | **`FAILED tests/test_gh18_syscall_abi.py::test_gh18_admit_syscall_deterministic_end_to_end`** — `1 failed`; mutation reverted, file md5 back to `9e8ffbb3b1de6a2a2349f16486594b96` (byte-identical), re-run **17 passed** |

## Arc regression (row-level check; test-only change)

`SEED=2026091316 bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- bash tools/arc_lega.sh` at head `4441197` →
**1 failed, 322 passed, 1 skipped, 4 deselected in 266.76 s** (`output/arc_lega_seed2026091316_4441197.txt`). The delta
versus the four preceding arc runs (325 passed / 1 skipped / 1 deselected) is **exactly the four migrated live legs**
moving from "ran" to "deselected".

**The single red is a NEW DEFECT-24-class finding, not a regression from this change — and the landing arc run is what
found it.** `tests/test_gh20_fs_v2.py::test_gh20_fs_rename_inplace_inode_preserved` fails with
`/usr/lib/python3.12/socket.py:707: TimeoutError: timed out` — the same live-draft socket timeout the DEFECT-24 ticket
measured. That leg (`:163`) calls `admit_syscall(runner, FSV2_N_RENAME, contract="fs_rename(old,new): ...")` with no
draft seam and no `_ollama_available` reference — one of **five** such GH-20 fs_v2 legs (`:118,163,202,235,274`), all
invisible to this tick's audit (whose three signals are declared in its docstring). It passes in isolation on the same
tree (`1 passed in 10.21 s`), and the arc's wall time (266 s vs 126 s) is the timeout itself. Filed as **DEFECT-25**
(`.builder_queue/DEFECT-25_gh20_live_draft_gates.json`).

**So the honest scope of this row:** the GH-18 leg named in the ticket is migrated, the mechanism is gated by a
discriminating audit, and the arc lost *four* live-model gates — but **the arc is NOT yet free of live-model gates**, and
this row does not claim it is. The re-run with a fresh seed (`SEED=2026091317`) is recorded in the landing commit.

## What this PASS does NOT prove

- That pre-existing live coverage elsewhere (gh12/gh15/gh26) is complete — the audit only sees the arc selector's files
  and only three signals (a `_ollama_available` decorator/call, or a live-denoting test name).
- That an unmigrated live leg outside the selector (`tests/test_oracle.py` and friends) is caught; that an unmocked
  `escalate(` nested in helper code with no marker and no `_ollama_available` reference is caught.
- That the 19:4x red (`TimeoutError`, 120.66 s) would have passed with a longer client timeout — not re-run, deliberately.
- Nothing about the WGSL twin, the engine, the transpiler, or any ABI: this row touches tests only.
- **Teleop: no substrate read this tick** (snapshot > 50 h stale, `tick=0` from the previous tick's meta — a read would
  return the same archaeology), and the marker `live_smoke` remains **unregistered** in pytest config, so runs print
  `PytestUnknownMarkWarning`. The mechanism works (`-m` deselection proven in G2/G3/G4); registration is a follow-up,
  not a claim.
