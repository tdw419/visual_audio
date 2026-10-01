# BRIEF — DEFECT-24: demote the live-Ollama draft leg out of the gating arc (roadmap row `DEFECT-24`)

**Roadmap row:** `DEFECT-24` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (added this tick by the orchestrator, `4441197`).
**Ticket:** `.builder_queue/DEFECT-24_arc_live_ollama_gate.json` · note `.builder_queue/REPAIR_PENDING_arc_live_ollama_gate.md`.

**Spec pointer — read these FIRST, they are the specification:**
- `.builder_queue/DEFECT-24_arc_live_ollama_gate.json` — the measurement and the ruled option 1.
- `.builder_queue/RULING_gh12_gate_determinism.md` (option 3) + `.builder_queue/RULING_arc_determinism_standing.md` —
  the mechanism: a deterministic claim gates; a claim that depends on live LLM sampling / GPU / network runs as a
  **non-blocking smoke** and never gates.
- `tests/test_gh12_autoatlas.py:236-320` — the LANDED `@pytest.mark.live_smoke` pattern (marker + an
  `output/<name>_live_smoke_<head>.txt` record + `_ollama_available()` + "skipped" path). Copy this shape.
- `tests/test_gh15_step3_autoatlas.py:118-136` — the LANDED deterministic escalate seam
  (`monkeypatch.setattr(aa, "escalate", _fake)` returning `EscalationResult(..., verified=True, glyph_text=TILE, oracle=None)`;
  gate 3 — the in-image re-dispatch — still runs, so the admitted tile is still verified on-die).
- `tests/test_gh26_emit_admit.py:54-96` — the pinned tiles to reuse verbatim: `GOOD_TILE` (3*r1: input `@750`, result `@754`)
  and `ORACLE_WRONG_TILE` (2*r1 — must be REFUSED).
- `tests/test_gh18_syscall_abi.py:60-125` (constants `N_NEW`, `GH18_EXIT_WORD`, `GH18_EXIT_OK`, `_run`, `_seed_admit_tile`)
  and `:363-384` — the leg to split.
- `tools/arc_lega.sh` — the arc's file selector and its `-m "not live_smoke"` deselection (do not edit it).

## Deliverables

**1. `tests/test_gh18_syscall_abi.py` — split the live leg (this is the row's substance).**
Split `test_gh18_admit_syscall_via_ingest_end_to_end` (`:364`) into two tests:

- `test_gh18_admit_syscall_deterministic_end_to_end` — **gating, NO marker, zero network.** Same pipeline as today
  (`_run(..., mode="admit")` → `admit_syscall(runner, N_NEW, contract=..., argv={0: 6}, expected=18)` → re-dispatch),
  but the draft comes from a PINNED tile through the `aa.escalate` seam (pattern 4 above); use `GOOD_TILE`
  (or the equivalent constructed locally) so the real oracle/IR gate and the in-image re-dispatch both still run.
  Assertions: `res.ok`, `res.table_word != 0`, then `runner.drive(seeds={}, max_instructions=60000)` →
  `mem[754] == 18`, `mem[GH18_EXIT_WORD] == GH18_EXIT_OK`, `mem[GH18_BADSYS_WORD] == 0`.
  **Network proof inside the leg:** install a connect-guard that raises on any connection attempt to
  `localhost:11434` (`monkeypatch.setattr(socket.socket, "connect", guard)` or an equivalent seam) and assert at the
  end of the test that the guard recorded **0** attempts.
- Add/keep a deterministic sibling proving the ORACLE still refuses: `ORACLE_WRONG_TILE` (2*r1 → 12 ≠ 18) through the
  same seam must come back `not res.ok` with `res.table_word == 0` and the table untouched. Reuse the existing
  `test_gh18_unproven_tile_rejected_table_untouched` if it already covers this — do not duplicate it.
- `test_gh18_admit_syscall_live_draft_smoke` — `@pytest.mark.live_smoke`, **never gates**: today's body verbatim
  (the single live `admit_syscall(...)` draft) plus a record file `output/gh18_live_smoke_<short-head>.txt`
  recording model, rc, seconds and outcome, with the documented "skipped (ollama not available)" path.

**2. `tests/test_gh12_escalation.py` — same class, same tick.** Both live legs (`:31`, `:44`) get
`@pytest.mark.live_smoke` (keep their existing `skipif`). Do NOT delete them or change their bodies.

**3. NEW `tests/test_arc_determinism_audit.py` — the class closure (this is what stops regression).**
AST-only, no network, fast:
- **L1** — parse the arc selector's files (same glob/union as `tools/arc_lega.sh`: `tests/test_gh*.py`,
  `tests/test_bk*.py`, `tests/test_eng*.py`, `tests/test_defect1*.py`, minus `glass_box|gh24_s2_mcp`) and assert that
  EVERY test function which either (a) calls a live-model entry point (`escalate(` without a monkeypatched seam is not
  detectable by AST — so use the two detectable signals below) or (b) carries a
  `skipif(... _ollama_available() ...)` decorator is marked `live_smoke`. The second signal is the reliable one; use it
  as the primary predicate and state in the docstring exactly what the audit cannot see.
- **L2 (non-vacuity, this is also the RED evidence)** — the same checker run over a FIXTURE copy of the
  **pre-fix** gh18 leg source must report exactly `test_gh18_admit_syscall_via_ingest_end_to_end` as a violation, and
  over the post-fix source must report none. Keep the fixture source inline in the test or at
  `tests/fixtures/arc_determinism_prefix_gh18.py` (a `.py` file under `tests/fixtures/` is fine).
- **L3** — pin the mechanism by source scan: `tools/arc_lega.sh` still carries `-m "not live_smoke"`.

## Scope

**Files in scope — only these may change:**
- `tests/test_gh18_syscall_abi.py`
- `tests/test_gh12_escalation.py`
- `tests/test_arc_determinism_audit.py` (new)
- optionally `tests/fixtures/arc_determinism_prefix_gh18.py` (new fixture)

**MUST NOT change:** `tools/glyph_gpt/autoatlas.py`, `tools/glyph_gpt/escalate.py`, `tools/glyph_gpt/baker.py`,
`tools/glyph_gpt/oracle.py`, `tools/arc_lega.sh`, `tools/rv64i_to_glyph.py`, any WGSL shader, `tests/test_gh12_autoatlas.py`,
`tests/test_gh15_step3_autoatlas.py`, `tests/test_gh26_emit_admit.py`, any `systems/*.md` (the orchestrator owns the
roadmap row), and `-m "not live_smoke"` deselection semantics.
**Interfaces are LOCKED:** no production signature, syscall number, ABI word, or CLI contract changes. Tests only.

## Gate commands (run each yourself; paste the literal tail)

1. `python3 -m pytest tests/test_gh18_syscall_abi.py tests/test_gh12_escalation.py tests/test_arc_determinism_audit.py -q`
   → expected exit code **0**, all pass.
2. `python3 -m pytest tests/test_gh18_syscall_abi.py -q -m "not live_smoke" -v`
   → expected exit code **0**; the live smoke leg shows as **deselected** and no network call happens (the
   deterministic leg's connect-guard assertion is what proves it).
3. `python3 -m pytest tests/test_gh18_syscall_abi.py --collect-only -q -m live_smoke`
   → expected: exactly the live smoke leg listed (proves the split did not delete coverage).
4. `python3 -m pytest tests/test_gh12_autoatlas.py tests/test_gh15_step3_autoatlas.py tests/test_gh26_emit_admit.py -q -m "not live_smoke"`
   → expected exit code **0** (no regression in the modules whose patterns you reused).

## Gate clause (what must be true)

- The three named modules + the new audit module pass (commands 1-4 above).
- The deterministic leg covers the end-to-end admission claim with **zero network**: table word live,
  `mem[754] == 18`, exit word `0xFEED0006`, badsys 0; the connect-guard records 0 connection attempts.
- A WRONG tile is still REFUSED with the table word untouched (the guard was NOT weakened).
- The live draft leg exists, is marked `live_smoke`, is deselected by `-m "not live_smoke"`, and writes its record file.
- The audit's L1 reports EMPTY on the live tree, and the audit is DISCRIMINATING: it reports exactly one violation
  on the pre-fix fixture source.
- **Does NOT prove:** that the pre-existing gh12/gh15/gh26 live coverage is complete; that the live draft would have
  succeeded on the 19:4x red with a longer timeout; that an unmigrated live leg in a file name outside the arc
  selector (e.g. `tests/test_oracle.py`) is caught — say so in the module docstring.

## Failure evidence (RED before GREEN — required)

1. **RED (discriminating power, no git needed):** temporarily remove the `live_smoke` marker from the new live leg,
   run `python3 -m pytest tests/test_arc_determinism_audit.py -q` → it must FAIL naming
   `test_gh18_admit_syscall_live_draft_smoke`; restore the marker and record `md5sum` before/after to prove the
   restore is byte-identical. Paste both tails.
2. **RED (L2 fixture):** the pre-fix fixture source check must be shown to flag the unmigrated leg
   (paste the assertion output showing the violation name).
3. Paste the literal tail of every gate command, and say explicitly what you did NOT verify.

## Hard constraints

- **Do NOT commit, do not stage, do not run `git checkout`/`git stash`/`git reset`.** Leave everything in the working tree.
- Do not weaken any live guard to make a leg pass. If a guard blocks you, STOP and report it.

## Definition of done

Gates 1-4 green with their literal tails pasted, RED evidence 1 and 2 pasted, the four deliverables present in the
working tree, and a DIFF SUMMARY naming every file changed — with anything unverified stated as unverified.
