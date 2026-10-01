# TICKET — HARNESS-FAILNAME-1: a failing file's verdict does not name the failing test

Filed 2026-09-13 by the builder cron `af3e62239ce2`, out of SUITE-BASE-1
(`systems/RECEIPT_SUITE_BASE1_BASELINE_LOCK.md`, finding 2).

## Symptom (measured)

The per-file record keeps only the **last** output line:

- `tools/suite_iso_harness.py:345` — `last_line = lines[-1] if lines else ""`
- the `--sink` JSONL carries the same `last_line`
- the text artifact prints that line, and nothing else, per file

So for `tests/test_ollama_security_analysis.py` the artifact says
`1 failed, 36 passed in 391.25s` — and the identity of the failing leg is **nowhere** in the
artifact. The same is true of all 17 baseline FAILs in `systems/SUITE_BASELINE_2026-09-13.txt`:
the baseline is clustered by *file* only because *test* identity was never captured.

Evidence (SUITE-BASE-1 `-t 400` secondary pass):
`output/SUITE_BASE1_TIMEOUT_SINK.jsonl` — `test_pixel_lm_train.py` FAIL `1 failed, 5 passed`,
`test_ollama_security_analysis.py` FAIL `1 failed, 36 passed`; no node ids in either record.

## Why it matters

SUITE-FIX-1 has to burn down 17 (now 19) failing files. Without the failing node id in the
artifact, every fix starts with a direct re-run of the file to learn what broke — the expensive
part of a slow file (218 s, 392 s for the two newest) is paid twice.

## Smallest fix (not implemented here — new scope, and the roadmap is at its 3-row cap)

Capture the pytest short summary instead of the last line, in the same place:

1. Run pytest with `-q -rf --tb=no` (or parse `short test summary info`), and store up to the
   `FAILED`/`ERROR` node ids (cap ~20) as a new record field, e.g. `failed_nodeids: []`.
2. Keep `last_line` for back-compat; print `<n> failed: test_a, test_b, …` in the text artifact.
3. Gate: a file with exactly 2 failing legs must yield `failed_nodeids` of length 2 with those
   node ids, and a green file must yield `[]` — RED first by mutating a copy of the harness to
   return `[]` unconditionally.
4. Do NOT change verdict semantics (a file is FAIL iff pytest rc != 0) — SWEEP-OOM-ACCT-1's
   accounting is live and must stay green (`tests/test_sweep_preflight.py` 5/5).

## Related

- `REPAIR_PENDING_suite_iso2_memory_containment.md` (record survival) — orthogonal; this is record
  *content*, not survival.
- The sink is otherwise well-formed: `counts` (`collected`/`passed`/`failed`), `rc`, `duration_s`,
  `timeout_s`, `verdict` are all present (verified 2026-09-13 on
  `output/SUITE_BASE1_LOCK_SINK.jsonl`). Missing from the record: **which** legs failed.
