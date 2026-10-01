# BRIEF — INSTRUMENT-2: the agy wrapper's DIFF SUMMARY detector must recognise real gate evidence, not just a literal header

Row: `.builder_queue/INSTRUMENT-2_agy_wrapper_diff_summary_recall.json` (instrument hygiene — wrapper
recall; the work it mis-graded is already landed at `39ad5ce`).

## Spec pointer — read these first

1. `~/.hermes/scripts/agy_implement.sh:119-126` — the current detector: `grep -q "DIFF SUMMARY" "$LOG"`,
   rc=3 on absence. This file is OUTSIDE the repo — **the deliverable is a patch file inside the repo;
   do NOT edit the wrapper in place** (the orchestrator applies it after your gate is green).
2. The mis-graded real reply: `output/agy/agy_impl_20260913_204459.log` — carries full gate evidence
   (`### 1. RED-first pre-edit gate output`, `### 2. Raw gate tail post-edit` → `5 failed …` →
   `3 passed, 5 xfailed in 0.62s`, `### 5. git diff --stat & git status`) but ZERO occurrences of the
   literal string "DIFF SUMMARY". It was graded UNVERIFIED/exit 3. This is the calibration point.
3. The standing contract text the reply was written against: `agy_implement.sh:73` (the guardrail's
   "End your reply with a DIFF SUMMARY…" line) — the predicate must stay STRICTER than "any reply is fine";
   its job is to keep catching exit-0 replies with no evidence at all (the 09:09 2026-09-12 incident).

## Scope — positive

- `tests/test_agy_wrapper_evidence.py` — NEW gate file (hidden by `.gitignore:101` `test_*.py`; the
  orchestrator force-adds it — that is expected and fine).
- `tools/agy_evidence_check.sh` or `.builder_queue/patch_agy_wrapper_detector.patch` — the extracted
  detector, whichever shape your legs exercise; if both, say which is authoritative.
- `.builder_queue/patch_agy_wrapper_detector.patch` may alternatively carry the wrapper edit as a
  unified diff against `~/.hermes/scripts/agy_implement.sh` (135 lines at HEAD, md5
  5b868a9571f6f6b9b98dc92d80d82b31).

## Scope — negative (must NOT change)

- `~/.hermes/scripts/agy_implement.sh` itself (orchestrator applies the patch).
- Any file in `tools/glyph_gpt/`, `tests/` other than the new gate file, `tools/suite_*`, the engine,
  the transpiler, WGSL shaders. No drive-by fixes to the 9 tracked-dirty files.

## The detector contract (the predicate you implement)

VERIFIED iff the reply log contains the literal block header `DIFF SUMMARY`, **OR** ALL of:
(a) a gate-command line (matches the repo's pytest/`python3 -m pytest`/`-m pytest` usage),
(b) a pytest-summary tail line (`N passed` / `N failed` / `N xfailed` / `no tests ran`),
(c) a changed-files section (`git diff`/`git status`/`git diff --stat` invocation or output).
Otherwise UNVERIFIED. The three-part arm is what reclassifies the 20260913_204459 log; the literal
header stays the fast path so nothing regress.

## Gate command

```
/usr/bin/python3 -m pytest tests/test_agy_wrapper_evidence.py -q -p no:randomly
```
Expected: all legs pass, exit 0.

## Gate clause (legs — each is falsifiable)

- **L1 calibration-positive:** the real mis-graded reply `output/agy/agy_impl_20260913_204459.log`
  classifies VERIFIED under the new predicate (and, if you also diff the wrapper, UNVERIFIED under the
  old grep — the RED-first witness is the ticket's own recorded observation, so assert the OLD predicate
  fails this file too, against a copy of the log with `DIFF SUMMARY` absent).
- **L2 no-evidence-negative:** a reply with neither the header nor any gate tail (e.g. just prose
  "looks good", and the `no output produced` shape) classifies UNVERIFIED — the detector must still
  catch the 09:09 shape.
- **L3 partial-evidence-negative:** a reply with a pytest tail but NO gate command and NO changed-files
  section classifies UNVERIFIED (the three-part arm is a conjunction; each part is load-bearing —
  show a mutant with any part dropped disagrees).
- **L4 header fast-path:** a reply containing the literal `DIFF SUMMARY` block classifies VERIFIED even
  if its body is thin (the header remains sufficient).
- **L5 self-test / non-vacuity:** the OLD predicate (`grep -q "DIFF SUMMARY"`) is shown RED on the L1
  fixture and GREEN on an L4-style fixture, so the change is a recall fix, not a relaxation.

## RED first

Before writing the detector, run the gate — the file is absent, so pytest exits 4 (collection error).
Paste that in your reply.

## Non-negotiables

- No design guessing: if the three-part arm cannot be built mechanically from the log evidence above,
  STOP and report with evidence instead of inventing new matching rules.
- Interfaces are LOCKED: do not change the wrapper's exit-code semantics (0 verified / 1 run-failed /
  3 unverified) — only WHAT classifies as verified may widen to the contract above.
- Never weaken a live guard: the `no output produced` and empty-log guards are untouched by this row.

## Done

Gate green on your own run with the literal tail pasted in your reply, plus the DIFF SUMMARY block
(files changed, gate command, literal output tail). Do NOT commit; leave the tree dirty.
