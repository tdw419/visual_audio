# RECEIPT — SUITE-HEAVY-1: TIMEOUT classes as data + `counts.observed_collected` / `counts.skipped` as sink FIELDS

Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:359` · branch `glyph-transpiler-autoloop` · 2026-09-13 (builder cron `af3e62239ce2`)
Every number below is the orchestrator's own run unless the line says otherwise.

## 1. What the row asked for

(a) every TIMEOUT file carries exactly one of `{BUDGET-RAISE, CONTENTION-SENSITIVE, RESTRUCTURE, KNOWN-INPUT}`
with a **solo-measured number** as evidence; (b) the sink records `counts.observed_collected` as a **field**
(it lived only in `last_line` prose, so a parser saw 0/0 on a killed record) — and the row additionally noted
`counts` has no `skipped` field.

## 2. Solo re-measurements (orchestrator, sequential, one file at a time)

`timeout 240 /usr/bin/python3 -m pytest <file> -q -p no:randomly`, 2026-09-13 21:49–21:50 CDT, load avg 2.56–2.87
(1-min) — **not an idle box**: a sibling lane held the GPU at 44 % util / 20 GB throughout, so these are
"solo-sequential" numbers, not exclusive-box numbers. Every one of the five PASSED:

| file | solo | verdict | production sweep |
|---|---|---|---|
| `tests/test_probe_stval.py` | **4.37 s** (1 passed) | CONTENTION-SENSITIVE | TIMEOUT @150.4 s (`output/SUITE_DEFECT27_SINK.jsonl`) |
| `tests/test_gh20_fs_v2.py` | **43.01 s** (10 passed) | CONTENTION-SENSITIVE | TIMEOUT @150 s in the row's 4-file reproduction |
| `tests/test_spatial_rv32i_cpu.py` | **1.42 s** (19 passed) | CONTENTION-SENSITIVE | TIMEOUT @150.6 s |
| `tests/test_sbi_firmware.py` | **3.07 s** (1 passed) | CONTENTION-SENSITIVE | TIMEOUT @150.8 s |
| `tests/test_rv64i_to_glyph_xv6_nano.py` | **43.12 s** (12 passed) | CONTENTION-SENSITIVE | TIMEOUT @150.1 s |

Three classes rest on **prior** measurements, labelled `prior measurement, not re-run` in the artifact:
`test_pixel_lm_train.py` CONTENTION-SENSITIVE (PASS 6/6 @80.16 s, `-w 1`), `test_ollama_security_analysis.py`
BUDGET-RAISE (FAIL 36/37 @387.46 s — a slow real failure, ≥400 s needed before its failing leg is even readable),
`test_xv6_boot_regression.py` KNOWN-INPUT (7 passed @51.22 s with `XV6_KERNEL_PATH=boot_images/xv6-riscv.img`,
SUITE-XV6-2; 601.30 s / 2 failed pre-fix on the known-broken fallback).
`RESTRUCTURE` is assigned to no file: the row's own characterization of `test_probe_stval` as ">3000 s unfinished,
needs restructuring" is **refuted by re-measurement** (4.37 s solo) — the vocabulary is closed, and a class with no
member is not an error. The five TIMEOUT files that pass solo are queue-depth effects, not defects.

## 3. What was changed

* `tools/suite_iso_harness.py` (+150/−8, additive): `counts` gains `observed_collected` and `skipped` (ints) on
  **every** branch — `COLLECT-HANG`, `TIMEOUT`, `OOM`, `CRASH`, the SKIPPED-after-OOM record, the collect-only path
  and the normal path. Semantics: `observed_collected` = the collection count pytest printed to stdout (0 when
  nothing was observed); `collected` keeps its old meaning (authoritative junitxml, falling back to the observed
  value on the observed-TIMEOUT branch, which `test_l13` pins at 2). `skipped` = the count already parsed from
  junitxml/summary, now emitted. Module-level `CLASS_VOCABULARY`, `DEFAULT_CLASS_ARTIFACT`,
  `load_timeout_classes()` and `unclassified_timeouts(records, artifact)` (unknown class tokens are reported, not
  ignored). Exit-code contract, verdict tokens, JSON one-line-per-record and the sink lock/fsync path untouched.
* `systems/SUITE_TIMEOUT_CLASSES.json` (new): 8 entries; 7 cover every TIMEOUT in the two committed sinks,
  `test_gh20_fs_v2.py` is included with `in_sink: false` because only the row text is its provenance.
* `tests/test_suite_heavy1_timeout_classes.py` (new, 5 legs): L1 artifact completeness + closed vocabulary
  (+ path exists on disk), L2 coverage of the committed sinks with a non-empty-TIMEOUT precondition, L3 the
  coverage check discriminates (unclassified path returned; unknown token rejected), L4 a real subprocess sweep
  emits both fields on all three record shapes (`observed_collected > 0` on the TIMEOUT, `skipped >= 1` on the
  skipping file), L5 in-gate non-vacuity against a mutated **copy** (md5 of the real harness before == after).
* `tests/test_suite_iso_harness.py`: the three whole-dict `counts` assertions (L7/L9/L10) re-pinned to the new key
  set with explicit values. **L7's `observed_collected` is 1, not 0** — the child collected one test before
  SIGKILL, and the two counts are exactly what this row separates (`collected`=0: no junitxml exists after a kill;
  `observed_collected`=1: the collection was observed). The guard those legs have always made — a kill is neither
  pass nor fail (`passed`=0, `failed`=0) — is unchanged and still asserted. Nothing was deleted, skipped, xfailed
  or loosened to a subset check.

## 4. Gate — RED first, then GREEN

**RED (pre-change surface, committed probe `.builder_queue/probe_suite_heavy1_red_first.py`, output
`output/SUITE_HEAVY1_RED_probe_orch.txt`):** the harness blob from `git show HEAD:tools/suite_iso_harness.py`, loaded as its own
module: `CLASS_VOCABULARY = <ABSENT>`, `load_timeout_classes = <ABSENT>`, `unclassified_timeouts = <ABSENT>`;
a SIGKILLed child's record `counts = {'collected': 0, 'passed': 0, 'failed': 0}` → `missing_fields =
['observed_collected', 'skipped']` → **`PROBE_VERDICT = RED`**.

**GREEN (orchestrator's own run, `output/SUITE_HEAVY1_gate_GREEN.txt`):**

```
/usr/bin/python3 -m pytest tests/test_suite_heavy1_timeout_classes.py tests/test_suite_iso_harness.py -q -p no:randomly
22 passed, 1 warning in 138.59s (0:02:18)   rc=0
```

**Non-vacuity (orchestrator's own run, `output/SUITE_HEAVY1_nonvacuity_orch.txt`):** neutering every
`observed_collected` emission in the real harness (`mutated_occurrences = 7`) turns L4 RED —
`assert 'observed_collected' in {'collected': 1, 'failed': 0, 'passed': 1, 'skipped': 0}`,
`1 failed in 3.16s` — and the file is restored byte-identically (`md5 95765cabb58fa00e6a355321dead9a71` before
== after). **Probe defect worth recording:** the first version of this probe removed only one branch line
(the 12-space `"observed_collected": observed_collected,`, the collect-only path) and L4 stayed GREEN; that was a
probe targeting error, not a vacuous gate — a collect-only sweep never exercises L4's normal-path records.

## 5. Delegation and its failure

`agy` (delegate) was given `.builder_queue/brief_suite_heavy1_timeout_classes.md` (validated by
`tools/check_brief.py`, PASS) and ran `TIMEOUT=45m`; it wrote the artifact, the gate file, the harness change and
the three assertion re-pins, then was **SIGKILLed (exit −9)** at ~21:59 with a 1096-byte log
(`output/agy/agy_impl_20260913_215119.log`), producing no receipt and no verification. Per the loop's fallback
rule the orchestrator finished (receipt, the L7 expectation correction, RED/GREEN/non-vacuity runs, commit).

## 6. What the PASS does NOT prove

* **No repo-wide sweep ran this tick.** SUITE-HEAVY-1's own clause makes sweeps exclusive, and a sibling lane was
  live (GPU 44 %, 20 GB; per-file writes inside this tick's window). Regression status therefore rests on this
  22-leg gate plus the unchanged-arc argument, **not** on a full-width sweep.
* The coverage leg (L2) binds to the two sinks named in `sinks_covered`. A **future** sweep with a new TIMEOUT file
  will not be caught until that file (or that sink) is added — the gate is not a standing monitor.
* Three of the eight classes are prior measurements (see § 2); `test_gh20_fs_v2.py` has no committed sink record.
* Sealed references: b"..." never executed; nothing in this change touches the engine, the transpiler,
  `glyph_dispatch/**` or any WGSL shader — no pixel/word-level claim is made.
* **One transient red was not caused by this change, and is recorded rather than hidden:** the first full gate run
  failed `test_l2_bounded_coverage_tests_root` (`harness sum=1670 vs live=1682`). Measured attribution: fresh
  per-file collect-only dumps with the current harness and the HEAD harness are **identical** (258 files, total
  1682 = the live count, diff 0), and the leg passed in the confirm run 4 minutes later — a probe-window artefact
  consistent with a sibling write, not a defect in this change. No cause is attributed beyond that.
