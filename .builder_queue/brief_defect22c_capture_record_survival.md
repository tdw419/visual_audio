# BRIEF — DEFECT-22c: the capture runner's verdict survives a scope OOM (record survival, follow-on)

## Spec pointer (READ FIRST, in this order)

1. `systems/RECEIPT_DEFECT22_PRESSURE_CLASS_AND_RECORD_SURVIVAL.md` — § "What this PASS does NOT prove", bullet 3
   names this exact follow-on: *"Only `tools/arc_lega.sh` is fixed. `tools/arc_lega_capture.sh` writes its own
   sidecar the same way and is **not** fixed."*
2. `.builder_queue/DEFECT-22_arc_legA_instability.json` — key `record_loss_fixed_2026_09_13_1310` (the whole
   finding, incl. the killing-scope measurement) and its trailing NOT-fixed clause.
3. **The landed fix, as the template**: `git show 9ef7b49 -- tools/arc_lega.sh` — the start record written with
   `printf` before pytest starts, overwritten by the full record with `"state": "DONE"` on normal exit.
4. **The landed gate, as the template**: `tools/gate_arc_lega_record_survival.sh` (129 lines) — reuse its L0/L1/L2
   shape verbatim (pinned pre-fix revision copy, `systemd-run --user --scope -q -p MemoryMax=$CAP -p OOMPolicy=kill`,
   the JSON key assertions).
5. `tools/arc_lega_capture.sh` (398 lines) — the file you change. Anchor points: sidecar path computed at
   `:51` (`JSON="${TAG}.json"`); the gdb invocation at `:194-196`; the dry-run parse writer at `:148-170`
   (writes `"dry_run": True`, **no** `"state"` key); the main parse writer at `:332-354`; the
   instrument-failure guard at `:370-375` (`if [ ! -s "$JSON" ]` → `FATAL` + `exit 2`).

## Scope

**May change (positive):**
- `tools/arc_lega_capture.sh` — the fix (start record + `state` on both terminal writers + the guard tightening).
- `tools/gate_arc_lega_capture_record_survival.sh` — **NEW** gate (the six legs below).
- `systems/RECEIPT_DEFECT22C_CAPTURE_RECORD_SURVIVAL.md` — **NEW** receipt.
- `output/d22c_*` — gate/probe evidence artifacts.

**Must NOT change:**
- `tools/arc_lega.sh` and `tools/gate_arc_lega_record_survival.sh` (landed at `9ef7b49`; treat as frozen — read-only
  reference).
- `tools/gate_arc_lega_naming.sh`, `tools/gate_arc_lega_telemetry.sh`, `tools/gate_arc_lega_capture.sh`,
  `tools/arc_env_telemetry.sh`, `tools/gdb_segv_capture.gdb` (regression witnesses, not targets).
- `tests/**`, `tools/process_registry.py`, anything under `tools/glyph_gpt/`, `tools/rv64i_to_glyph.py`,
  `glyph_dispatch/**`, WGSL shaders — no engine, transpiler or test file is in scope.
- Do **NOT commit.** Leave the tree dirty; the orchestrator verifies and commits.

## Gate command

```
bash tools/gate_arc_lega_capture_record_survival.sh      # exit 0 = all legs pass
```

Every leg's raw stdout goes to `output/d22c_capture_record_survival_gate.txt`.

## Gate clause (falsifiable — what is written, refused, returned)

- **L0 premise** — `git show <PRE_FIX_REV>:tools/arc_lega_capture.sh` (default `PRE_FIX_REV=9ef7b49`) contains
  **no** `"state": "RUNNING"`; the working-tree copy does. If the pinned copy already has it, exit 2 (stale RED).
- **L1 RED (falsifier)** — the pinned pre-fix capture runner, run inside
  `systemd-run --user --scope -q -p MemoryMax=1200M -p OOMPolicy=kill` with a stub `PY` whose first invocation
  (`-m pytest`) allocates past the cap (e.g. `bytearray` loop) and never returns: `rc=137` and
  **zero** `*arc_lega_capture_seed*.json` files in the OUTDIR. RED observed, not asserted.
- **L2 GREEN** — identical command, working-tree runner: `rc=137`, **exactly one** sidecar, it parses as JSON and
  carries `state=="RUNNING"`, an `int` seed, a non-empty `head`, a non-empty `started_utc`. Print those four values.
- **L3 instrument-failure is still a refusal** — the guard at `:370` must require the terminal record, not mere
  file existence. A run whose parse step fails (stub `PY` that emits unusable output on the parse call, so the
  parse block cannot write `state="DONE"`) must: exit **2**, print the loud `FATAL` line to stderr, and print
  **no** `arc leg A (live capture) ::` verdict line on stdout — while the sidecar file survives in
  `state="RUNNING"` (proof that presence alone is no longer the pass criterion).
- **L4 no-regression** — `TELEMETRY_ONLY=1` dry run of the capture runner → `rc=0`, exactly one sidecar, it parses
  with `state=="DONE"`, `dry_run is True`, `rc is None`; **and** these four landed gates each exit 0, re-run:
  `tools/gate_arc_lega_naming.sh`, `tools/gate_arc_lega_telemetry.sh`, `tools/gate_arc_lega_record_survival.sh`,
  `tools/gate_arc_lega_capture.sh`.
- **L5 non-vacuity** — with the start-record write removed from a scratch copy of the working-tree runner (md5 the
  scratch copy before and after, restore byte-identical, print both md5s), L1's sidecar_count must still be 0 for
  that copy — i.e. the gate can distinguish "record survived" from "record lost". (Cheapest discriminating probe;
  a second acceptable probe is neutering the L3 state check and showing L3 FAIL.)

## Implementation constraints (the parts that bite)

1. **The start record must not cost an interpreter call.** Use `printf` (mirror `tools/arc_lega.sh:9ef7b49`), not
   `$PY` and not a heredoc-that-runs-python: the naming gate routes `PY` through a stub and a third call shape
   would need a new route.
2. **Write it after `:51` (the `JSON=` path exists and the no-clobber `_rerunN` suffix is decided) and before the
   gdb invocation at `:194`** — nothing heavy may precede it, or the kill window is not covered.
3. **Both terminal writers get `"state": "DONE"`** (dry-run writer at `:148-170` and parse writer at `:332-354`);
   keep every existing key and the printed line formats byte-identical otherwise.
4. **The `:370` guard must change meaning**: today it passes on file existence; after this change a file that is
   still `state="RUNNING"` is by definition a lost run, not a verdict. Keep `exit 2` and keep the message
   unmistakable (adjust the wording to name both cases: not written **or** not completed).
5. Keep the file's existing comment discipline: every non-obvious line carries its measured rationale.

## Standing constraints (soft fields)

- **Interfaces are LOCKED.** `tools/arc_lega_capture.sh`'s CLI surface (env vars `OUTDIR`/`SEED`/`PY`/`VERBOSE`/
  `TELEMETRY_ONLY`, its exit codes 0/2/139, and the `<OUTDIR>/arc_lega_capture_seed<SEED>_<HEAD>(_rerunN)`
  artifact name + printed summary-line formats) must not change. Sidecar keys may only be **added**.
- **Must-not-touch list** is the negative half of "Scope" above; if you believe one of those files must change,
  STOP and write `REPAIR_PENDING_defect22c_<topic>.md` instead of editing it.
- **Definition of done:** `bash tools/gate_arc_lega_capture_record_survival.sh` exits 0 on the working tree,
  every leg tail pasted into `systems/RECEIPT_DEFECT22C_CAPTURE_RECORD_SURVIVAL.md`, and the tree left uncommitted
  with `git status --short` showing only in-scope paths.
- **Never weaken a live guard to make a step pass.** The `:370` guard is being *tightened*, not relaxed; if a leg
  only goes green by deleting or loosening an existing check, the step is wrong — report it, do not do it.
- **If a locked interface looks wrong**, do not change it: file the `REPAIR_PENDING_*` note, then stop and report.

## Failure evidence (required before the gate is trusted)

- Paste, literally, in the receipt and the commit body the orchestrator-facing tails:
  - **L1 RED** (pinned pre-fix runner, killing scope) — `systemd-run rc=137 sidecar_count=0`.
  - **L5 falsification** — the same command against the start-record-stripped copy, md5s printed.
  - **L2 GREEN / L3 / L4 GREEN** tails.
- The receipt must end with a **"What this PASS does NOT prove"** section: it does not make the arc fit its cap, it
  was measured through a transient user scope with the same properties (not through the Hermes
  `tools/process_registry.py` wrapper), the caps are below production's 4 GiB and force the OOM deliberately, and
  n is one run per arm.

## Determinism clause

No live LLM sampling, no network, no GPU leg. The stub `PY` and the pinned revision are the only pinned inputs;
record `PRE_FIX_REV`, `CAP` and the stub body in the receipt. The deliberately-killed runs write to `mktemp -d`
directories under `/tmp` **only** — never into `output/`, so a deliberate kill can never enter the arc ledger.
