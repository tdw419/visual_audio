# RECEIPT — SUITE-ISO-2: per-file verdicts survive an abnormal kill

**Row:** `SUITE-ISO-2` (roadmap ⏳ → ✅). **Tick:** 2026-09-13 11:2x–11:5x CDT, builder cron `af3e62239ce2`.
**Head when the defect was found:** `e2a4dbd` (promotion commit). **Delegate:** `agy` was launched from
`.builder_queue/brief_suite_iso2_sink.md` and was **SIGKILLed at startup** (`output/agy/agy_impl_suite_iso2_20260913_113553.log`,
log stops after the pre-state; 26 further OOM kills in the same window) — so the implementation below is the
orchestrator's own, under the loop's fallback rule, and every number is the orchestrator's run.

## What was wrong (measured, not inferred)

Running SUITE-ISO-1's own declared follow-on (per-file coverage over `tools/` + `systems/`) for the first time:

| attempt | command | outcome |
|---|---|---|
| 1 | `… tools systems --json -t 20 -w 12` | OOM-killed 11:28:13; `journalctl -k`: 20 × `Killed process … (python3)`, worst child `anon-rss:3,470,616 kB`, every victim `oom_score_adj:200`, `ollama` killed as collateral; `output/suite_iso2_tools_systems_20260913_1128.json` **0 bytes** |
| 2 | `… tools systems --json -t 20 -w 3` | killed again; `output/suite_iso2_w3_20260913_1128.json` **0 bytes** |

Cause: in `--json` mode records were buffered and printed only at exit (`:467`, `:473`). A ~2-minute sweep
therefore produced **no evidence at all** — the exact failure the row exists to prevent. Raw kill lines:
`output/suite_iso2_oom_journal_20260913.txt` (30 kills).

## The fix (additive, two files)

- `tools/suite_iso_harness.py` — new `--sink PATH` (alias `--jsonl`), **independent of `--json`**:
  each record is written as ONE compact JSON line in a single `os.write` under a lock, then `os.fsync`ed
  (`write_record_to_sink`, `_SINK_LOCK`). The fd is opened at start (`O_TRUNC|O_APPEND`) and closed in a
  `finally`. `DEFAULT_TIMEOUT_S` / `DEFAULT_WORKERS` untouched; `--json` stdout contract untouched;
  `run_suite_iso` / `run_single_file` signatures untouched (`on_record` still the only hook).
- `tests/test_suite_iso_harness.py` — **L5** kill-survival (sink must grow *mid-run*, be newline-terminated,
  and keep ≥1 complete parseable record after `SIGKILL` of the process group) and **L6** (`--json` still emits
  exactly one JSON array; **no** sink file when the flag is absent).

## Gate — RED first, then GREEN, then the leg shown to be able to fail

Probe: `.builder_queue/probe_suite_iso2_kill_survival.sh` (out-of-tree instrument; 2 synthetic files sleeping
25 s, `-t 60 -w 1`, `SIGKILL` at 30 s — after the first record completes at ~25 s).

1. **RED (pre-fix, `--json`, no sink):** `stdout_bytes=0`, `output/suite_iso2_RED_json_buffered_0bytes.json`
   (a record had completed internally; none reached disk).
2. **GREEN (same experiment, `--sink`):** `sink_bytes=206`, `sink_lines=1`, `sink_ends_with_newline=yes`,
   `sink_parse_complete=1`, `torn_tail_bytes=0`,
   `rec0: test_slow_a.py verdict=PASS rc=0 dur=25.1` → `output/suite_iso2_GREEN_sink_after_kill.jsonl`.
3. **Non-vacuity (fixed harness with the write neutered, repo file restored byte-identical md5 `8a84a3c4…`):**
   `sink_parse_complete=0` → `output/suite_iso2_NONVACUITY_neutered_sink.jsonl`. The leg is discriminating.
4. **Gate:** `/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q` → **7 passed, 1 warning in 63.85 s**
   (L1–L4 unchanged + L5 + L6). `/usr/bin/python3 -m pytest --collect-only -q` still clean.

## Coverage measurement (the follow-on this row was found by — recorded, not acted on)

First-ever bounded per-file verdicts for the two roots that a plain `pytest` cannot sweep, all at `-w 1`:

| root | files | PASS | ERROR | TIMEOUT | FAIL | harness exit | artifact |
|---|---|---|---|---|---|---|---|
| `tools/` | 102 | 58 | 25 | 10 | 9 | 1 | `output/suite_iso2_tools_w1_stream.txt` |
| `systems/` | 11 | 4 | 5 | 1 | 1 | 1 | `output/suite_iso2_systems_w1_stream.txt` |

Totals 113 files, matching the TEST-COL-1 hanger bisect. `systems/` finished in 32 s with the known
`test_daemon.py` hanger reported as `TIMEOUT` — the bounded-verdict promise holds there.
**Do NOT read the 44 non-PASS records as 44 broken tests.** Most `tools/*.py` are standalone probe scripts, not
pytest suites: many PASS records are `rc=5 coll=0` ("no tests ran") and most ERRORs are 0.2 s collection
failures. What is measured is that a pytest-shaped sweep **cannot interpret** these files; classifying
`tools/` into suites vs scripts is a design question, not a defect claim.

## Honest boundary — what this PASS does NOT prove

- **No memory containment.** The 3.3 GB child that caused the OOM is still uncontained; only the *loss* was
  fixed. Per-child caps / worker defaults are held in `.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md`
  (4 options, cheapest first). A second OOM kill will now cost a *partial* record set, not all of it.
- **Process kill ≠ power loss.** `os.fsync` per record; a machine crash or filesystem failure is untested.
- L5 asserts sink growth with `-w 1` and 2 files; concurrent multi-worker interleaving is exercised only by
  construction (single `os.write` + lock), not by a stress leg.
- The `--json`-mode stdout is unchanged, but `--json` **still** buffers: a user who needs kill-survival must
  pass `--sink`. That is deliberate (no locked-contract change) and is a usability boundary, not an oversight.
- Running sweeps has side effects on tracked files: `db/wordbase.db` and `test_queue/*.wav` were rewritten by
  the tools/ sweep and were reverted (not committed) — cf. AGENTS.md evidence discipline; the harness itself
  was not the writer, the probe scripts it ran were.
