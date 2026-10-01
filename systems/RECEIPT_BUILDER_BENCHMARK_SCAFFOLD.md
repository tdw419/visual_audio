# RECEIPT — Builder benchmark: scaffold beats model (measured, 2026-09-12)

**Question driving this:** should we train/fine-tune an LLM to be the builder?
**Answer this produces:** no — the binding variable is the *loop*, not the weights,
and it is measurable in one afternoon with `tools/builder_eval/`.

## The benchmark

`tools/builder_eval/run_eval.py` takes a **closed** roadmap row, strips the
solution in a scratch tree with **no git history**, hands the row's intent to a
candidate, and lets the row's own gate decide. Task used: **SB-1**
(`systems/SPATIAL_BUILDER_ROADMAP.md:77`) — recreate
`tools/glyph_gpt/spatial_builder.py` (437 lines) so that
`python3 tools/glyph_gpt/test_spatial_builder.py` prints `11 passed, 0 failed`.

## Three runs, each fixing a defect in the instrument

| # | setup | result |
|---|---|---|
| 1 | `git worktree` scratch, one-shot brief | **INVALID** — candidate produced a file byte-identical to the original (sha `7e17851e…`); it recovered the solution with `git show HEAD:<path>` in 87 s. The benchmark leaked the answer. |
| 2 | `git archive` scratch, **no history**, same one-shot brief | **FAIL** — no file written (gate: `ModuleNotFoundError`). Raw agy run shows why: it launched an unrelated repo test (`test_generate.py`) and searched the filesystem for `wordbase.db`, then hit `--print-timeout`. Task never attempted. |
| 3 | same no-history scratch, brief rewritten to impose the **emit → gate → fix loop** | **PASS** — 321 s, gate `11 passed, 0 failed`. |

Verification of run 3 (not taken on trust):

- scratch repo has exactly **1 commit** and `git show HEAD:<stripped>` fails, so the
  solution was unrecoverable by construction;
- produced file sha `0038444ad79880…` ≠ original `7e17851eb07ad6…`;
- **768 of 832 possible lines differ**; **zero** shared comment lines; the module
  implements the required public surface but with its own internal design (no
  `_prefix_*` family, no `_entry`, no `main`) — a reconstruction, not a copy;
- candidate log contains no reads of any path outside the scratch;
- the harness's own plagiarism guard (identical-hash ⇒ INVALID) ran and did not fire.

## What changed between run 2 and run 3

Only the brief. Run 2's brief described the task and the context; run 3's adds a
**mandatory work plan**: read only `glyph_gpt/`, create the file *early* so the gate
can run, run the gate, fix the failures it names, iterate to a bound of 6 attempts,
do not explore unrelated tests or the wider filesystem, and (explicitly) there is
no history to recover from.

Knowledge, repo access, model, and hardware were identical. **The scaffold is the
variable.** 0 → pass, ~5 minutes, zero training cost.

## Conclusions

1. **The fine-tune case is dead for this class of work.** Retrieval + iteration
   discipline closes an oracle-gated row of this system; no checkpoint was needed
   and none was trained.
2. **This is the third independent sighting of the same law today** (gpt-oss
   confabulating a whole task; agy wandering into unrelated tests; both fine once
   constrained). Structure constrains agents; weights do not.
3. **Two instrument defects were found by testing the instrument**, and both are
   the same species as the failures this repo polices elsewhere:
   - a *gate command* that collected 0 tests (pytest form of a standalone harness)
     — an oracle that does not run still reports;
   - a *scratch tree with history* — a benchmark that hands the candidate the
     answer. Both are now guard-railed in the harness.
4. **Operational takeaway for every delegation** (`cli-agent-implementation-delegation`):
   put the emit → gate → fix loop in the brief, with an attempt bound and a
   no-exploration clause. It is the cheapest measured win available.

## Reproduce

```bash
python3 tools/builder_eval/run_eval.py --task sb1_pipeline --red-check     # expect RED
python3 tools/builder_eval/run_eval.py --task sb1_pipeline --label agy \
  --candidate-cmd 'REPO=$PWD bash ~/.hermes/scripts/agy_implement.sh -f {brief}'
cat tools/builder_eval/results.jsonl
```

Caveat on scope: n = 1 task, one candidate, one trial. It establishes that the
question is *measurable* and that scaffold-first is the right default; it does not
estimate pass rates. Adding SB-0/SB-2 and a second candidate is the cheap next step.


---

## Final trial matrix (scaffolded brief, candidate `agy`) — added 2026-09-12 12:50

Counted from `tools/builder_eval/results.jsonl` after five instrument defects were
found and fixed (see `RECEIPT_BENCHMARK_INSTRUMENT_DEFECTS.md`):

| task | PASS | FAIL | INVALID |
|---|---|---|---|
| `sb1_pipeline` (pure-Python module, self-contained 11-leg gate) | **2** | 2 | 2 |
| `bk14_demo` (subprocess demo + human-gate refusal semantics) | 1* | 3 | 1 |
| `bk12_wgsl_tier` (WGSL compute path + CPU reference + pixel bridge) | 0 | **4** | 1 |

\* The single `bk14_demo` pass happened while the harness's archive closure was missing
`tests/`, i.e. **the gate file was absent from the scratch** — the only way `4 passed`
could appear is if the candidate satisfied its own idea of the gate. It is not counted.

### What this establishes (n is still small, but the shape is consistent)

1. **Single trials are coin flips.** The same task, brief, candidate and machine went
   **pass, pass, fail** on `sb1_pipeline`. Any capability claim resting on one run —
   including the earlier "one row, one pass" phrasing of this receipt — is a coin flip
   being reported as a result.
2. **Scaffold is necessary, not sufficient.** The emit → gate → fix loop is what turned a
   one-shot wander (0 landed) into a ~50% pass rate on the simplest row. On the two
   harder rows it is 0-for-3 and 0-for-4 — and the last `bk12` attempt ran **2692 s
   (45 minutes)** of genuine iteration before failing, so this is not laziness; it is a
   capability boundary.
3. **The gradient is legible:** a pure-Python module against a self-contained gate is
   reachable roughly half the time; reproducing subprocess + human-gate refusal
   semantics, or a GPU/WGSL tier, is not reachable at all in three and four attempts.
4. **The second candidate remains unmeasured.** `hermes --in <scratch>` does not confine
   a Hermes session (it works in the configured project checkout), so the deepseek arm is
   void, not failed. Measuring it needs an isolated config/HOME.

### Practical conclusion

- For **SB-1-class work**, an off-the-shelf agent with the scaffold is adequate about half
  the time; a fine-tune buys little.
- For **BK-12/BK-14-class work**, scaffolded generalist agents have not closed a single
  row in seven attempts. That is the first place in this investigation where a fine-tune
  (or a fundamentally better scaffold — e.g. a domain-specific harness the agent must
  drive, not invent) has a non-zero case.
- Either way the benchmark now measures rather than argues, and every void row carries its
  reason in `results.jsonl`.
