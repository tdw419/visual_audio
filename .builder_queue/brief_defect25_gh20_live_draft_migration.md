# BRIEF — DEFECT-25: close the five GH-20 live-draft arc gates (sensor extension + migration)

Roadmap row `DEFECT-25` — `systems/GLYPH_SELF_HOSTING_ROADMAP.md:359`. Promoted 2026-09-13 by
builder cron `af3e62239ce2`; base commit `e3a384b` (branch `glyph-transpiler-autoloop`).

## Spec pointer — READ FIRST (in this order)

1. `.builder_queue/DEFECT-25_gh20_live_draft_gates.json` — the ticket: the measured red, the five
   unmigrated legs, the three-step plan this brief implements.
2. `tests/test_arc_determinism_audit.py` — the sensor you are extending (109 lines, read all of it;
   its own docstring lists the blind spot you are closing).
3. The landed shape to COPY, verbatim in technique:
   `tests/test_gh18_syscall_abi.py` → `test_gh18_admit_syscall_deterministic_end_to_end(monkeypatch)`
   (gating, zero network, pinned tile through the `aa.escalate` seam, real oracle + IR gate still run,
   `socket.socket.connect` guard asserting 0 attempts) and its smoker
   `test_gh18_admit_syscall_live_draft_smoke` (`@pytest.mark.live_smoke`).
4. `.builder_queue/brief_defect24_live_draft_split.md` — the brief that landed that shape last tick
   (same class, one file over).
5. Rulings in force: `.builder_queue/RULING_gh12_gate_determinism.md` (option 3) and
   `.builder_queue/RULING_arc_determinism_standing.md`.
6. `tests/test_gh20_fs_v2.py` — the five legs (:118 append, :163 rename, :202 unlink, :235 and :274
   the two loop legs). Its module docstring is the FS-v2 ABI spec; do not re-derive it.

**Signatures are LOCKED.** `admit_syscall(...)` in `tools/glyph_gpt/autoatlas.py:450`,
`find_unmarked_live_tests(source, filename)` in the audit, `_get_arc_files()`, and every existing
test leg keep their signatures and semantics. If you believe one is wrong, STOP and file
`.builder_queue/REPAIR_PENDING_defect25_<topic>.md` (2-4 options, cheapest first) — do not change it.

## Scope

**MAY change — exactly these files:**

- `tests/test_arc_determinism_audit.py` — extend the sensor; add the new legs.
- `tests/test_gh20_fs_v2.py` — mark the five drafting legs; add deterministic siblings.
- NEW `tests/fixtures/arc_determinism_prefix_gh20.py` — the pre-fix replay fixture.
- NEW pinned-tile supply file (suggest `tests/fixtures/fs_v2_op_tiles.py`) if you pin tile texts
  as module constants rather than inline strings.

**MUST NOT change:** `tools/glyph_gpt/**` (in particular `autoatlas.py`, `baker.py`, `fs_v2.py`,
`escalate.py`), `tools/arc_lega.sh`, `tools/supply_census.py`, `tools/check_brief.py`,
`tests/test_gh18_syscall_abi.py`, `tests/test_gh12_escalation.py`, any other test file, and any
engine/transpiler/WGSL file. No ABI change of any kind. **Do NOT commit.**

## The two changes

### (1) Sensor: `find_unmarked_live_tests` must see a live draft that carries no `_ollama_available`
A test is a violation when **all** hold:
- its body calls a function whose **last dotted component** is exactly `admit_syscall`, `ingest`, or
  `escalate` — AND that call carries a `contract=` **keyword**; and
- the call does **not** appear in a helper-mediated wrapper name (i.e. do not substring-match:
  `ingest_leg(...)` and `x_ingest(...)` must NOT match); and
- the test's signature does **not** take a `monkeypatch` fixture; and
- the test carries no `live_smoke` marker and no `live_smoke`/`live_draft` name.

Keep the three existing signals and the existing violation-string form `"<file>::<test>"` unchanged.
**MEASURED WARNING — do not implement the naive substring form.** Measured by the orchestrator at
`e3a384b` (`.builder_queue/probe_defect25_sensor_fp_v2.py`, saved verdict in
`output/defect25_sensor_RED.txt`): substring-matching `ingest`/`escalate` over the 52 arc-selector
files flags **14** tests — 9 false positives, all deterministic: `tests/test_gh19_stdlib.py`'s eight
`*_matrix` legs call the helper `ingest_leg(...)` (substring hit), and
`tests/test_gh12_autoatlas.py::test_family_whitelist_blocks_without_model_calls` calls `ingest(...)`
**positionally** with a whitelist-rejected family and asserts `res.escalations == 0` (deterministic by
construction). Exact-callee **plus** the `contract=` keyword clause is the signal that yields exactly
the five. The keyword clause is a real boundary: a live leg passing `contract` positionally is not
caught — record that in the audit docstring's Limitations list.

### (2) Migration: five legs stop drafting a live tile
- Pin one **supply-verified** tile text per FS op (`FSV2_N_APPEND`=10, `FSV2_N_RENAME`=11,
  `FSV2_N_UNLINK`=12) and serve it through the `aa.escalate` seam
  (`monkeypatch.setattr(aa, "escalate", ...)`) returning
  `EscalationResult(contract=..., verified=<real oracle verdict>, glyph_text=<pinned text>, oracle=ores)`.
  **Supply-verified means the real pipeline produced it** — obtain it from a real run or from the
  in-repo probe supply (`output/fs_semantics_probe2.py`, `output/debug_gh20_probe1*.py` hold candidate
  FS-op texts) and confirm `run_oracle(...)` passes on it. **NEVER hand-assert `verified=True`** on a
  tile the real oracle has not passed; the real oracle and the IR gate must still run inside
  `ingest()`.
- Per leg: the drafting leg keeps its assertions but gains `@pytest.mark.live_smoke`; a deterministic
  **sibling** runs the same end-to-end path through the seam and asserts the same post-conditions
  (admission `res.ok`, `res.table_word != 0`, then a live-image `runner.drive()` re-assertion of the
  leg's own observable — the FSTAB word / errno word it already checks).
- The two loop legs (:235, :274) iterate ops: dispatch the pinned tile **by contract text** so the seam
  serves the right op — make it a shared helper rather than per-leg copies.
- Install the `socket.socket.connect` guard in each deterministic sibling and assert **0** attempts to
  `localhost:11434`.
- **Fallback, only if a loop leg's pinned tile is genuinely not a mechanical port** (no per-contract
  dispatch is possible without changing a locked signature): migrate the three single-op legs, mark the
  two loop legs `@pytest.mark.live_smoke`, and file `.builder_queue/DEFECT-25b_fs_loop_determinism.json`
  describing exactly what stopped the port. Do not delete a leg and do not weaken its assertions to
  make this fallback easier — reduced coverage must be filed, never silent.

## Gate command and expected results

```bash
# G1  RED-first replay (must be pasted RED, before the fix, in the delegate log)
python3 .builder_queue/probe_defect25_red_gap.py            # expect rc=0, shipped=0 / proposed=exactly 5

# G2  the sensor + the migration together
python3 -m pytest tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q
#     expect: all green, exit 0, and the five drafting legs DESELECTED by the marker

python3 -m pytest tests/test_gh20_fs_v2.py -q -m "not live_smoke"
#     expect: green, exit 0, and >= 5 deterministic legs COLLECTED (the siblings gating)

python3 -m pytest tests/test_gh20_fs_v2.py --collect-only -q -m live_smoke
#     expect: exactly the 5 migrated leg names (or 3, with DEFECT-25b filed under the fallback)

# G3  the sensor is live at file level (not just via pytest)
python3 -c "import importlib.util,sys;s=importlib.util.spec_from_file_location('a','tests/test_arc_determinism_audit.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.find_unmarked_live_tests(open('tests/test_gh20_fs_v2.py').read(),'x'))"
#     expect: [] (empty list)

# G4  no regression in the class this one belongs to
python3 -m pytest tests/test_gh18_syscall_abi.py tests/test_gh12_escalation.py -q
#     expect: green, exit 0 (20 passed as landed by DEFECT-24)

# G5  the arc this row exists to protect
SEED=<pin an integer and record it> bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- bash tools/arc_lega.sh
#     expect: rc=0, crashes=0, 0 failed, oom_kill_delta=0
```

## Gate clause (concrete criteria — all must hold)

- The audit flags **exactly** the five GH-20 legs when run against the **pre-fix** source
  (`git show HEAD:tests/test_gh20_fs_v2.py`, committed as the replay fixture) — names listed literally
  in the assertion, so a widened or narrowed sensor fails the leg.
- The audit flags **zero** tests in the live arc-selector set after the migration (`_get_arc_files()`).
- Each of the five legs carries `@pytest.mark.live_smoke`; each has a deterministic sibling that
  installs the seam itself, passes with **0** connect attempts to `localhost:11434`, and leaves
  `res.table_word != 0` plus the leg's own in-image observable asserted.
- A **non-vacuity leg** proves the new predicate is load-bearing: neutering only it (monkeypatch or a
  mutated copy of the module) makes the replay leg RED with the five names present; the repo file is
  restored byte-identical (md5 recorded in the log).
- `find_unmarked_live_tests` over `tests/test_gh20_fs_v2.py` returns `[]` (G3).

## Failure evidence (the gate must be shown able to FAIL)

Paste, literally, in the delegate log:
1. **G1 RED** — shipped sensor flags **0** of the five while the proposed signal flags **exactly 5**
   (`output/defect25_sensor_RED.txt` is the orchestrator's copy; re-run it and paste your own).
2. **Non-vacuity RED** — the neutered-predicate run, showing the replay leg failing with the five names.
3. **A discriminating sibling probe** — mutate one pinned sibling's expected observable (e.g. the
   FSTAB word it asserts) and show that sibling going RED, then revert it byte-identical (md5 before
   and after) and show it green again. A sibling that passes with a wrong expected value is decoration.
4. **The pre-fix sensor's blindness, re-shown** — `git show HEAD:tests/test_arc_determinism_audit.py`
   run over the pre-fix GH-20 source flags **0**, i.e. the wart could not see itself.

## Determinism clause

Every new gating leg must be deterministic: pinned inputs only, **zero network**, no live model
sampling, no randomized order. Any leg that needs the live drafter is `live_smoke` and never gates.
Record the arc `SEED=<n>` you ran with. State in your log what the PASS does **not** prove.

## Pitfalls that bite here

- **Do not weaken a live guard.** L1's assertion, L2's fixture equality, L3's `-m "not live_smoke"`
  check, and the five legs' existing assertions stay exactly as strong as they are. If a guard blocks
  you, the step is wrong — file the REPAIR_PENDING and hold.
- **Do not add `-k`/`-m` filters to `tools/arc_lega.sh`** or otherwise route around the deselection.
- `.gitignore`'s `test_*.py` rule hides new test files from `git status` — if you create one, note it
  and force-add is the orchestrator's call, not yours.
- `tests/fixtures/` already holds `arc_determinism_prefix_gh18.py`; follow its shape for the GH-20
  replay fixture (a plain module of pre-fix source, loaded by path, never imported as a test).

## Definition of done

The five GH-20 legs no longer gate the arc on a live model; the audit sensor that missed them now
catches the class; every gate command above is green on your own run; and you have pasted the RED
evidence first. **Do not commit** — the orchestrator re-runs every gate on your tree and commits only
on its own green.
