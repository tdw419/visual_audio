# BRIEF — INSTRUMENT-1: register the `live_smoke` pytest mark (roadmap row INSTRUMENT-1)

## Spec pointer (read first)

1. `.builder_queue/INSTRUMENT-1_live_smoke_mark_unregistered.json` — the ticket, with the measured
   evidence and the gate clause. That ticket's `gate_clause` field is the contract; this brief
   sharpens it into legs.
2. `systems/GLYPH_SELF_HOSTING_ROADMAP.md` line 363 — the promoted row INSTRUMENT-1 (⏳ queued).
3. `pytest.ini` (10 lines, repo root) — the project's ONLY pytest config. It has `pythonpath = .`
   and `testpaths = tests`, and **no `markers =` entry**.
4. `tools/arc_lega.sh:51,70-71` — the arc runner deselects via `-m "not live_smoke"`; that string is
   already pinned by `tests/test_arc_determinism_audit.py::test_l3_arc_runner_excludes_live_smoke`.

Measured state you are starting from (already reproduced by the orchestrator, do not re-derive):
`/usr/bin/python3 -m pytest tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q`
→ `14 passed, 5 warnings in 43.34s`, every warning
`PytestUnknownMarkWarning: Unknown pytest.mark.live_smoke - is this a typo?` at the decorator
(e.g. `tests/test_gh20_fs_v2.py:475`). 22 `pytest.mark.live_smoke` usages exist across 5 files.

## Interfaces are LOCKED

No function/class/CLI signature changes anywhere. This brief adds one config entry and one new test
module. If you believe a locked interface must change, STOP, write
`.builder_queue/REPAIR_PENDING_instrument1_<topic>.md` with 2-4 options cheapest-first and hold.

## Scope — exactly two files may change

**Files in scope (positive) — only these two may change:**
- `pytest.ini` — add exactly ONE `markers =` entry registering the mark name `live_smoke` (with a
  one-line description), keeping every existing line (`pythonpath`, `testpaths`, the existing
  comment block) byte-identical. Do **not** add `--strict-markers`, `addopts`, or any other key.
- `tests/test_instrument1_mark_registration.py` — NEW gate module (see Gate clause).
  NOTE: `.gitignore` hides `test_*.py`, so the orchestrator will `git add -f` it; create the file
  normally and do not touch `.gitignore`.

**MUST NOT change (negative scope):**
- `tools/arc_lega.sh`, `tests/test_arc_determinism_audit.py`, `tests/test_gh20_fs_v2.py`,
  `tests/test_gh18_syscall_abi.py`, `tests/test_gh12_escalation.py`, `tests/test_gh12_autoatlas.py`
  — these are the guard, the consumer and the migrated legs. Do NOT add the marker to them, do not
  edit their assertions, do not weaken any live guard to make this step pass.
- `tools/glyph_isa_v2.py`, `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`,
  `glyph_dispatch/**`, any WGSL shader, anything under `.builder_queue/`, any `systems/*.md`.
- No new dependency, no network call, no GPU call. The gate must run with zero live model access.

## Gate command

Both must be run from the repo root:

```
/usr/bin/python3 -m pytest tests/test_instrument1_mark_registration.py -q
/usr/bin/python3 -m pytest tests/test_instrument1_mark_registration.py tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q --strict-markers
```

Expected: first command **4 passed, exit 0**; second command green (no failures, no errors) and its
output contains **zero** `PytestUnknownMarkWarning`. Interpreter note, measured: the gates in this
repo need `/usr/bin/python3` (pytest 8.3.5); the PATH `python3` is the hermes venv.

## Gate clause — what is written, what is refused, what is returned

`tests/test_instrument1_mark_registration.py` must carry exactly these four legs, each failable
independently, all with subprocesses only (no in-process pytest config mutation):

- **L1 registered** — a `--strict-markers --collect-only -q` subprocess over the four
  `live_smoke`-carrying arc files (`tests/test_gh20_fs_v2.py`, `tests/test_gh18_syscall_abi.py`,
  `tests/test_gh12_escalation.py`, `tests/test_gh12_autoatlas.py`) returns **rc 0**, and
  `"not found in \`markers\` configuration option"` does not appear in its output.
- **L2 RED-first / discriminating** — the SAME subprocess with the registration synthetically
  removed, `-o markers=` (measured by the orchestrator to reproduce the pre-fix condition exactly:
  `ERROR tests/test_gh20_fs_v2.py - Failed: 'live_smoke' not found in \`markers\` configuration
  option`, `no tests collected, 1 error`) returns **rc != 0** and its output names the mark. This leg
  is what proves L1 can fail; it must not be skipped or softened.
- **L3 non-vacuity** — against a synthetic `tmp_path` test file carrying a MISSPELLED mark
  (`@pytest.mark.live_smok`), `--strict-markers --collect-only -q` must return **rc != 0**; against an
  otherwise identical twin using the correct name `live_smoke` it must return **rc 0**. A guard that
  cannot fail is decoration; this leg is the demonstration.
- **L4 name-match** — parse the registered marker name out of `pytest.ini`'s `markers` entry and the
  deselection token out of `tools/arc_lega.sh`'s `-m "not <NAME>"` line, and assert the two names are
  **equal** (`live_smoke`). A registration under a different spelling than the deselector would leave
  the arc silently re-gated on live models.

Explicitly REFUSED: registering additional marks, adding `--strict-markers` to `pytest.ini`'s
`addopts`, touching any file outside the two in scope, or weakening/removing any existing pytest test.

## Failure evidence (required before the fix is trusted)

1. Module-absent RED: `tests/test_instrument1_mark_registration.py` does not exist →
   `/usr/bin/python3 -m pytest tests/test_instrument1_mark_registration.py -q` prints
   `no tests ran` / rc 4. Paste the tail.
2. Pre-fix tree RED for L1's own subject: paste the `PytestUnknownMarkWarning` tail from
   `/usr/bin/python3 -m pytest tests/test_gh20_fs_v2.py -q` (or the two-file set) run against the
   pre-fix `pytest.ini` (`git show 34934c6:pytest.ini` is the promotion-time copy).
3. L2 and L3 must be shown RED in their failing direction with their tails pasted — not asserted from
   the code's intent.
4. State plainly in your report what the PASS does **not** prove.

## Definition of done

Both gate commands green from the repo root, L1–L4 each individually failable and each shown in its
failing direction at least once, the working tree carrying **only** the two in-scope files
(`pytest.ini` modified, `tests/test_instrument1_mark_registration.py` added, `git status --short`
shows nothing else), and no commit made by you.

## Deliverable and hard constraints

- Do **NOT commit**. Do NOT `git add`. The orchestrator re-runs the gate itself, checks `git status
  --short` for out-of-scope edits, and commits. Leave the working tree with exactly the two in-scope
  files changed/added.
- Do not run the arc suite, the sweep, any WGSL/GPU command, or any live-model/Ollama call.
- Report: the two gate commands with their literal tail output, the RED tails, the git status, and the
  not-proved list.
