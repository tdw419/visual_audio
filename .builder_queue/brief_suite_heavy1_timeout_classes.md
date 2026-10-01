# BRIEF — SUITE-HEAVY-1: TIMEOUT classes carried as data + `counts.observed_collected` / `counts.skipped` as sink FIELDS

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:359` (SUITE-HEAVY-1, ⏳ queued 2026-09-13, orchestrator).
Read the row text first — its GATE clause is the spec. Also read `systems/SUITE_TIMEOUT_PROBE_2026-09-13.txt`
(the prior probe, including its own CORRECTION block) and the sinks named below.

**Why:** the row's gate clause says (a) every TIMEOUT file carries exactly one of
`{BUDGET-RAISE, CONTENTION-SENSITIVE, RESTRUCTURE, KNOWN-INPUT}` with a solo-measured number as evidence, and
(b) the sink records `counts.observed_collected` (today the observed value lives only in `last_line` prose and in
the TIMEOUT branch's `collected` fallback, so a downstream parser reading a killed/KILLED record sees 0/0) and
`counts.skipped` (parsed in `_parse_counts_and_verdict` but never emitted).

## Scope — files you MAY change (exactly these six)

1. `tools/suite_iso_harness.py` — additive only:
   - `counts` gains `observed_collected` and `skipped` (ints, never None) on **every** branch
     (`COLLECT-HANG`, `TIMEOUT`, `OOM`, `CRASH`, normal, and the collect-only path).
   - semantics to implement, documented in a docstring:
     `observed_collected` = the collection count pytest printed to **stdout** (i.e. observed by execution;
     `collect_count_from(stdout)`, 0 when nothing was observed). `collected` keeps its current meaning
     (authoritative junitxml count, falling back to the observed value on the observed-TIMEOUT branch — the
     existing leg `tests/test_suite_iso_harness.py::test_l13` asserts `collected == 2` there and MUST stay green).
   - `skipped` = the skipped count already parsed from junitxml/summary; 0 when unknown.
   - module-level `CLASS_VOCABULARY = ("BUDGET-RAISE", "CONTENTION-SENSITIVE", "RESTRUCTURE", "KNOWN-INPUT")`,
     `load_timeout_classes(path=DEFAULT_CLASS_ARTIFACT)` and
     `unclassified_timeouts(records, artifact) -> list[str]` (returns the sorted TIMEOUT-record paths that have no
     artifact entry; `[]` when all are classified). Unknown class tokens must be reported, not ignored.
2. `tests/test_suite_heavy1_timeout_classes.py` — **NEW** gate, legs L1–L5 (see Gate clause).
3. `tests/test_suite_iso_harness.py` — **only** the three whole-dict `counts` assertions (around lines 380, 493,
   567) updated to the new key set, asserting the NEW keys' values explicitly (`observed_collected`, `skipped`).
   No leg may be deleted, skipped, xfailed, or loosened to a subset/`>=` check.
   **Never weaken a live guard to make a step pass** — if a live guard blocks this step, the step is wrong: file a
   `REPAIR_PENDING_suite_heavy1_*.md` and stop rather than editing the guard. (Note `.gitignore:101` hides
   `test_*.py` at the repo root only, so `tests/…` is not ignored; force-add if git still refuses.)
4. `systems/SUITE_TIMEOUT_CLASSES.json` — **NEW** machine-readable artifact. Content is given verbatim in
   § Artifact content below; do not invent or re-measure numbers, do not reword the classes.
5. `systems/RECEIPT_SUITE_HEAVY1_TIMEOUT_CLASSES.md` — **NEW** receipt: the classification table, which numbers are
   the orchestrator's own re-runs this tick vs. prior committed measurements, the RED-first tail, the non-vacuity
   probe outputs, and an explicit HONEST BOUNDARY section.
6. `.builder_queue/brief_suite_heavy1_timeout_classes.md` — this brief (already written; do not edit).

## MUST NOT change

- Any other file. In particular `tests/test_suite_iso_harness.py` legs other than the three assertions above,
  `src/**`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL shaders,
  `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (the orchestrator owns the row update), and every other test file.
- No sweep, no GPU work, no heavy probe: SUITE-HEAVY-1's clause makes sweeps exclusive and a sibling lane is live
  on the GPU (44 % util / 20 GB). Your gate is bounded (< 120 s) and must stay bounded.
- Do not change the harness exit-code contract (non-zero iff any FAIL or CRASH), the JSON line-per-record format,
  the sink fsync/lock behaviour, or any existing verdict token.
- **Do NOT commit.** Leave the tree dirty for the orchestrator.

## Gate command (the orchestrator re-runs this; you must run it too)

```
cd /home/jericho/projects/zion/projects/visual_audio
/usr/bin/python3 -m pytest tests/test_suite_heavy1_timeout_classes.py tests/test_suite_iso_harness.py -q -p no:randomly
```
Expected: **rc=0**, `0 failed` (`test_suite_iso_harness.py` is 17 collected today; the new file adds ~5).

## Gate clause — what the gate asserts (falsifiable)

- **L1 artifact completeness + closed vocabulary.** `systems/SUITE_TIMEOUT_CLASSES.json` loads; every entry has
  `path`, `class`, `solo_seconds`, `solo_command`, `in_sink`, `evidence`, `measured_at`; `class` is one of the four
  tokens; `solo_seconds` is a number > 0; `evidence` and `measured_at` are non-empty; `path` exists on disk.
- **L2 coverage of the committed sinks.** For every record with `verdict == "TIMEOUT"` in
  `output/SUITE_BASE1_LOCK_SINK.jsonl` and `output/SUITE_DEFECT27_SINK.jsonl` (both tracked), the path has an entry.
  The leg must first assert the TIMEOUT set is non-empty (7 distinct paths) — a coverage check over zero records
  proves nothing.
- **L3 the coverage check DISCRIMINATES (negative/non-vacuity leg).** Feeding `unclassified_timeouts` a synthetic
  record list containing a TIMEOUT on an unclassified path returns that path; feeding it a classified path returns
  `[]`. Also: an artifact copy with an unknown class token is reported as a violation, not accepted.
- **L4 the sink really carries the fields.** Run the harness CLI as a subprocess over a `tmp_path` directory holding
  one passing file, one file with a `@pytest.mark.skip` and one sleeping file, at a small budget with `--sink`;
  assert **every** emitted record's `counts` has both new keys, that the TIMEOUT record's `observed_collected > 0`
  (it collected before the kill) and that the skipping file reports `skipped >= 1`.
- **L5 non-vacuity of L4.** Re-run the same sweep against a temp **copy** of the harness with the
  `observed_collected` key removed (follow the mutation style of the existing
  `test_l11_collect_evidence_is_load_bearing`), and assert L4's own assertion helper goes RED on those records.
  Restore/verify the real `tools/suite_iso_harness.py` is byte-identical afterwards (print its md5 before/after).
- Refusal criterion, stated in the receipt: a TIMEOUT record whose path is not in the artifact must make the gate
  FAIL; if it does not, the gate is decoration and the row is not met.

## Failure evidence required (RED first — paste the tail literally)

1. Run the gate command **before** your change (or on a stash-restored tree) and paste the RED tail — with the new
   gate file present but the artifact/harness change absent, the expected RED is the artifact-missing /
   field-missing assertion, not a collection error.
2. Paste the GREEN tail of the gate command after the change, with rc and wall time.
3. Paste the L3 and L5 non-vacuity probe outputs (RED then GREEN), and the before/after md5 pair for
   `tools/suite_iso_harness.py` from the L5 mutation probe.
4. Any number you did not personally execute must be labelled `prior measurement, not re-run` with its source path.

## Interfaces LOCKED

`TestRecord`'s field names, `write_record_to_sink`, the CLI flags, and the verdict tokens are locked. Adding `counts`
keys is in scope because the row's gate names that field explicitly. If a locked signature looks wrong, do not change
it: file `REPAIR_PENDING_suite_heavy1_<topic>.md` with 2–4 cheapest-first options, state it is a skeleton-sign-off
change, and stop.

## Definition of done

Gate green (rc=0) with the RED tail and the non-vacuity probes pasted; only the six in-scope paths touched
(`git status --short` proves it); no commit made.

---

## Artifact content (`systems/SUITE_TIMEOUT_CLASSES.json` — copy verbatim, then pretty-print)

Vocabulary is closed: `BUDGET-RAISE` (needs a larger per-file budget, solo number given) ·
`CONTENTION-SENSITIVE` (passes solo; wall time is a function of queue depth) · `RESTRUCTURE` (the file itself must be
restructured) · `KNOWN-INPUT` (the red was an input defect, now removed).

`measured_at` for entries re-measured this tick: `2026-09-13T21:49-05:00`, evidence
`/tmp/suite_heavy1_solo_20260913.txt` is **transient** — copy its content into the receipt and use
`systems/RECEIPT_SUITE_HEAVY1_TIMEOUT_CLASSES.md` (plus the named sink) as the durable `evidence` string.

```json
{
  "artifact": "SUITE-HEAVY-1 TIMEOUT classification",
  "vocabulary": ["BUDGET-RAISE", "CONTENTION-SENSITIVE", "RESTRUCTURE", "KNOWN-INPUT"],
  "sinks_covered": ["output/SUITE_BASE1_LOCK_SINK.jsonl", "output/SUITE_DEFECT27_SINK.jsonl"],
  "entries": [
    {"path": "tests/test_probe_stval.py", "class": "CONTENTION-SENSITIVE", "solo_seconds": 4.37,
     "solo_command": "timeout 240 /usr/bin/python3 -m pytest tests/test_probe_stval.py -q -p no:randomly",
     "in_sink": true, "measured_at": "2026-09-13T21:49-05:00",
     "note": "1 passed solo in 4.37s at load 2.87 (orchestrator re-run this tick); TIMEOUT at 150.4s in the -w 4 production sweep on the same tree (output/SUITE_DEFECT27_SINK.jsonl). Not a defect: per-file wall time scales with queue depth.",
     "budget_note": "no raise justified while it passes the production budget solo; the row's 3.02s -> 118.52s 39x scaling was measured under load"},
    {"path": "tests/test_gh20_fs_v2.py", "class": "CONTENTION-SENSITIVE", "solo_seconds": 43.01,
     "solo_command": "timeout 240 /usr/bin/python3 -m pytest tests/test_gh20_fs_v2.py -q -p no:randomly",
     "in_sink": false, "measured_at": "2026-09-13T21:49-05:00",
     "note": "10 passed solo in 43.01s at load 2.80 (orchestrator re-run this tick); TIMEOUT at 150s in the row's 4-file reproduction. NOT in the two committed sinks - the row text is its provenance, hence in_sink false.",
     "budget_note": "solo 43s is inside 150s, so the production budget is close to the knee; a raise to 300s is defensible but not yet justified by a measured solo number over budget"},
    {"path": "tests/test_spatial_rv32i_cpu.py", "class": "CONTENTION-SENSITIVE", "solo_seconds": 1.42,
     "solo_command": "timeout 240 /usr/bin/python3 -m pytest tests/test_spatial_rv32i_cpu.py -q -p no:randomly",
     "in_sink": true, "measured_at": "2026-09-13T21:49-05:00",
     "note": "19 passed solo in 1.42s at load 2.56 (orchestrator re-run this tick); 39.95s under the lane's loaded run and TIMEOUT at 150.6s in the production sweep. Pure queue-depth sensitivity.",
     "budget_note": "none: solo is 1.4s"},
    {"path": "tests/test_sbi_firmware.py", "class": "CONTENTION-SENSITIVE", "solo_seconds": 3.07,
     "solo_command": "timeout 240 /usr/bin/python3 -m pytest tests/test_sbi_firmware.py -q -p no:randomly",
     "in_sink": true, "measured_at": "2026-09-13T21:49-05:00",
     "note": "1 passed solo in 3.07s at load 2.56 (orchestrator re-run this tick); 13 passed 49.02s in the lane's loaded run; TIMEOUT at 150.8s in the production sweep.",
     "budget_note": "none: solo is 3.1s"},
    {"path": "tests/test_rv64i_to_glyph_xv6_nano.py", "class": "CONTENTION-SENSITIVE", "solo_seconds": 43.12,
     "solo_command": "timeout 240 /usr/bin/python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py -q -p no:randomly",
     "in_sink": true, "measured_at": "2026-09-13T21:49-05:00",
     "note": "12 passed solo in 43.12s at load 2.60 (orchestrator re-run this tick); TIMEOUT at 150.1s in the production sweep.",
     "budget_note": "solo 43s inside 150s; raise not justified by measurement"},
    {"path": "tests/test_pixel_lm_train.py", "class": "CONTENTION-SENSITIVE", "solo_seconds": 80.16,
     "solo_command": "suite_sweep.sh -b 12G -w 4 -- suite_iso_harness.py tests/test_pixel_lm_train.py -t 400 -w 1",
     "in_sink": true, "measured_at": "2026-09-13 (prior measurement, not re-run)",
     "note": "PASS 6/6 rc=0 coll=6 at -t 400 -w 1; 150.1s TIMEOUT at -w 4 in the production sweep; FAIL 5/6 was also observed at -w 4.",
     "budget_note": "solo 80s is inside the 150s production budget; the failure is concurrency, not budget"},
    {"path": "tests/test_ollama_security_analysis.py", "class": "BUDGET-RAISE", "solo_seconds": 387.46,
     "solo_command": "suite_sweep.sh -b 12G -w 4 -- suite_iso_harness.py tests/test_ollama_security_analysis.py -t 400 -w 1",
     "in_sink": true, "measured_at": "2026-09-13 (prior measurement, not re-run)",
     "note": "FAIL 36/37 rc=1 coll=37 in 387.46s at -t 400: a slow REAL failure, not a budget artefact. Live-service (Ollama) file.",
     "budget_note": "needs a budget above its solo cost (>= 400s) before its one failing leg is even readable; the failing leg itself is NOT fixed by this row"},
    {"path": "tests/test_xv6_boot_regression.py", "class": "KNOWN-INPUT", "solo_seconds": 51.22,
     "solo_command": "XV6_KERNEL_PATH=boot_images/xv6-riscv.img /usr/bin/python3 -m pytest tests/test_xv6_boot_regression.py -q -p no:randomly",
     "in_sink": true, "measured_at": "2026-09-13 (SUITE-XV6-2 landing; prior measurement, not re-run)",
     "note": "The red was a KNOWN-BROKEN input: the test fell back to the RVC xv6 image. With the vendored non-RVC kernel it is 7 passed / 51.22s rc=0 (SUITE-XV6-2). Pre-fix the same file burned 601.30s / 2 failed on the broken fallback; the production sweep recorded 150.1s TIMEOUT before that landing.",
     "budget_note": "none: 51s with the correct input"}
  ]
}
```
