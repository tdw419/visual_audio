# BRIEF — SUITE-BASE-2: commit-anchored sweep records + attributed re-measure

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360` (SUITE-BASE-2, ⏳ queued 2026-09-13).
**Read first (spec = source of truth, this brief is only a summary):**
1. That row's cell text — especially its GATE cell and its own measured explanation of the 254/1590 vs 256/1608 discrepancy.
2. `systems/RECEIPT_SUITE_BASE1_BASELINE_LOCK.md` (the baseline that must stay the denominator) and
   `systems/SUITE_BASELINE_2026-09-13.txt` + `systems/SUITE_BASELINE_2026-09-13_PINNED_RERUN.txt`.
3. `tools/suite_iso_harness.py` (landed SUITE-ISO-1/ISO-2 + SUITE-COLLECT-1: `--sink/--jsonl`, `--import-grace`,
   `--budget`, `COLLECT-HANG`) and `tests/test_suite_iso_harness.py` (legs L1–L13; read `_sweep()` at `:534` and
   `test_l13_timeout_reports_observed_collection` at `:706` for the house pattern).

## The defect (measured, not inferred)

A sweep result is **not commit-anchored**. The harness's records carry per-file verdicts but nothing about *which
revision* produced them, and no re-measure mechanism checks that a difference against an earlier record is explained
by commits that landed in between. That is exactly how the 254/1590 vs 256/1608 discrepancy arose: two runs of the
same nominal command on different revisions, with no field in either artifact naming the revision, so the +18/+2 had
to be reconstructed by hand — and the 18th test of that delta is still unattributed today.

## What to build

### 1. `tools/suite_iso_harness.py` — a sweep record that names its revision

Add one flag:

* `--manifest PATH` — write ONE JSON object when the sweep finishes:
  `{"head_sha": <git rev-parse HEAD in --repo-root, or null if git is unavailable>,
    "timestamp": <ISO-8601 WITH timezone offset>, "files": <int>, "collected": <int>,
    "verdicts": {"PASS": n, "FAIL": n, "TIMEOUT": n, "COLLECT-HANG": n, "OOM": n, "CRASH": n, "ERROR": n, "SKIPPED": n},
    "roots": [...], "workers": <int>, "timeout_s": <float>, "import_grace_s": <float>, "python_bin": "<path>"}`
  `files`, `collected` and every `verdicts` count MUST equal what the same run's `--sink` records say (one source of
  truth, computed from the same `records` list). A requested-but-unwritable manifest is a harness error → non-zero exit.

Add a second flag:

* `--since PATH` — the previous manifest. When given, the new manifest additionally carries
  `"since": {"head_sha": <prev>, "files_delta": <int>, "collected_delta": <int>, "attribution_required": <bool>,
   "attribution": [{"commit": "<short sha>", "subject": "<subject>"}, ...], "attribution_unexplained": <bool>}`.
  `attribution_required` is true iff `collected_delta != 0 or files_delta != 0`. `attribution` lists the commits that
  touched the swept roots between the two heads (`git log --format='%h %s' <prev>..<head> -- <roots>`);
  `attribution_unexplained` is true iff attribution is required and no such commit exists. A `--since` manifest that
  cannot be read or parsed is a harness error → non-zero exit (never a silent empty attribution).

**INTERFACES ARE LOCKED.** `run_single_file(...)`, `run_suite_iso(...)`, `compute_exit_code(...)`,
`DEFAULT_TIMEOUT_S`, `DEFAULT_WORKERS`, `DEFAULT_IMPORT_GRACE_S`, the `--json` stdout contract (still exactly one
JSON array), and `--sink` semantics. The new flags must be **inert when absent**: with no `--manifest`, no file is
written and stdout/exit code are byte-identical to today.

### 2. `tests/test_suite_iso_harness.py` — two new legs (L14, L15), L1–L13 untouched

* **L14 `test_l14_manifest_is_commit_anchored`** — run a tiny sweep (one temp-dir file, `-t 20 -w 1`) with
  `--sink` + `--manifest`. Assert: `head_sha` equals `git -C <repo> rev-parse HEAD`; `timestamp` parses via
  `datetime.fromisoformat` and has a non-null `utcoffset()`; `files`/`collected`/`verdicts` agree exactly with the
  sink records; the manifest is one JSON object. Then run the same sweep with NO `--manifest` and assert no manifest
  file appeared anywhere in the temp dir (inertness).
* **L15 `test_l15_remeasure_attribution`** — with the same tiny sweep: (a) `--since <manifest>` where the manifest's
  `head_sha` is `git rev-parse HEAD` → `attribution_required` false; (b) a hand-written previous manifest whose
  `head_sha` is `git rev-parse HEAD~1` and whose `collected` is `current - 1` → `attribution_required` true and
  `attribution` non-empty (there are real commits between `HEAD~1` and `HEAD`); (c) a previous manifest with
  `head_sha` set to a **non-existent** sha and a non-zero delta → `attribution_unexplained` true (the loud case),
  and the harness must still exit non-zero on the *verdict* path if a file failed — attribution never masks verdicts.

**Failure evidence (mandatory):**
* Paste the RED tail of `pytest tests/test_suite_iso_harness.py -q -k "l14 or l15"` **before** your implementation
  (module has no `--manifest`: argparse must error, so the legs cannot pass) — this proves the new legs are
  discriminating rather than tautological.
* Write `.builder_queue/probe_suite_base2_nonvacuity.py` that mutates a COPY of `tools/suite_iso_harness.py`
  (never the repo file) in a temp dir with the head-SHA resolution neutered to a constant → L14 must go RED, and
  print the tail. Restore/hash-verify the repo file is untouched (`sha256sum` before == after).

## Scope

**In scope (only these two files may change):** `tools/suite_iso_harness.py`, `tests/test_suite_iso_harness.py`,
plus the out-of-tree probe `.builder_queue/probe_suite_base2_nonvacuity.py`.
**Out of scope / must not touch:** `tools/suite_sweep.sh`, `tools/arc_lega.sh`, `pytest.ini`, the roadmap, any
receipt, `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL shader, and every
existing leg's body (L1–L13 must stay byte-identical except for imports if strictly needed).
**Do NOT** run the canonical suite sweep (`suite_sweep.sh ... suite_iso_harness.py tests`): the orchestrator runs that
itself, under the 12 GiB scope. Do not delete, skip, or loosen any test.
**Do NOT commit.** Leave the tree dirty; the orchestrator re-runs the gate and commits.

## Gate command and gate clause

```
/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q          # expect: 16 passed, exit 0
/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q -k "l14 or l15"   # expect: 2 passed
```
PASS criteria: L1–L13 unchanged and green; L14/L15 green; with `--manifest` absent nothing extra is written and the
`--json` contract is byte-identical; the manifest's counts equal its own sink's counts; a non-zero delta against a
prior manifest is either attributed to named commits or flagged `attribution_unexplained`.
REFUSED: any change that weakens an existing assertion, any silently-empty attribution, any manifest that reports
counts from a second source instead of the records list.

**Determinism clause:** every leg uses small synthetic temp dirs, `/usr/bin/python3`, pinned budgets, no network, no
GPU, no live model, no randomized order. Do not add a leg that depends on live sampling.

**State in your final message:** files changed, the exact gate output you observed, the non-vacuity result, and what
your PASS does **not** prove (name the stubbed/reasoned parts explicitly).

## Definition of done

1. `tools/suite_iso_harness.py` gains `--manifest PATH` and `--since PATH` exactly as specified, inert when absent,
   with every locked interface untouched.
2. `tests/test_suite_iso_harness.py` gains L14 + L15 only; L1–L13 bodies unchanged.
3. `.builder_queue/probe_suite_base2_nonvacuity.py` exists, was run, went RED where it must, and printed its tail —
   with `sha256sum` of the repo harness proven unchanged before/after.
4. The two gate commands above were run and their literal output is pasted, RED (pre-implementation) before GREEN.
5. Nothing was committed, nothing outside the scope list was modified, and the final message names what the PASS
   does not prove.
