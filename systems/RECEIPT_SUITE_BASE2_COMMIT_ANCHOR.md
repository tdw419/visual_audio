# RECEIPT — SUITE-BASE-2: commit-anchored sweep records + attributed re-measure

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360` (SUITE-BASE-2, ⏳ → ✅ 2026-09-13).
**Ticks:** builder cron `af3e62239ce2`. Implementation delegated to `agy`
(exit 0, 382 s, `output/agy/agy_impl_20260913_201746.log`); one orchestrator correction
(see §2). Every number below is the orchestrator's own run.

## 1. What landed

| commit | what |
|---|---|
| `05b2860` | `tools/suite_iso_harness.py`: `--manifest PATH` (one JSON object per sweep: `head_sha`, `timestamp`, `files`, `collected`, `verdicts`, `roots`, `workers`, `timeout_s`, `import_grace_s`, `python_bin`) and `--since PATH` (previous record → `files_delta`, `collected_delta`, `attribution_required`, `attribution`, `attribution_unexplained`). `tests/test_suite_iso_harness.py`: legs **L14** (commit-anchored manifest, inertness when absent) and **L15** (attribution against an older / same head, loud `--since` refusal). |
| `e95a13d` | orchestrator correction: the record is anchored **before** the first file runs; `head_sha_end` + `head_moved_during_sweep` added; leg **L16**. |

Gate: `/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q` → **17 passed, 1 warning in 133.50 s**
(`16 passed` before the correction). Locked interfaces untouched: `run_single_file`, `run_suite_iso`,
`compute_exit_code`, the three defaults, the `--json` stdout contract, `--sink` semantics.

**Non-vacuity (own runs, not the delegate's claim):**
* L14 RED against a copy with the head-SHA resolution neutered — `FAILED …::test_l14_manifest_is_commit_anchored`,
  `PROBE_VERDICT: DISCRIMINATING`, repo file `sha256 aea8ac40…` unchanged (`.builder_queue/probe_suite_base2_nonvacuity.py`).
* L16 RED against the pre-fix harness (`git show HEAD:tools/suite_iso_harness.py` → `/tmp/harness_prefix_base2.py`):
  `1 failed, 16 deselected in 4.04s` → GREEN `1 passed … in 3.93s`.
* Pre-fix the legs do not exist: `-k "l14 or l15"` on the pre-fix blob → `14 deselected`.
* Functional probe `.builder_queue/probe_suite_base2_orchestrator.py` (`output/SUITE_BASE2_orchestrator_probe.txt`):
  P1 `head_sha_matches_git=True` / tz-aware timestamp / counts equal its own `--sink`; P2 non-zero delta vs `HEAD~1` →
  `attribution_required=True`, named commit; P3 same head → `False`; P4 inert when absent; P5 unreadable `--since` → `rc=2`.

## 2. The correction — the row's own claim was measured FALSE on its first real run

The row demands "every sweep record carries (head SHA, …)". The first canonical sweep that used the mechanism
launched at `af88284` / `05b2860`, ran **471.59 s**, and wrote `head_sha = b8859ae` — a *parallel session's* roadmap-doc
commit that landed at **20:27:32, mid-run**. The record therefore named a revision the sweep never executed a file
against: the anchoring the row asks for was not actually provided. Cause: `head_sha` was resolved at manifest-write
time. Fix (`e95a13d`): capture at sweep start, keep the end revision and a `head_moved_during_sweep` flag observable.
Test inputs were unaffected here (the interleaved commit touched only `systems/GLYPH_SELF_HOSTING_ROADMAP.md`), so the
numbers below stand; the defect was in the record's identity, which is exactly what this row exists to fix.

## 3. The re-measure (canonical pinned command, `--sink` + `--manifest`)

```
PATH=/usr/bin:$PATH tools/suite_sweep.sh -b 12G -w 4 -- \
  /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 \
  --sink output/SUITE_BASE2_SINK.jsonl --manifest output/SUITE_BASE2_MANIFEST.json \
  --since .builder_queue/SUITE_BASE2_prev_manifest_backfill.json
```

`Sweep finished in 471.59s. Files: 257, Total collected: 1671 · Verdicts: FAIL 7, PASS 246, TIMEOUT 4` (exit 1 — FAIL present,
as the baseline expects). Record: `output/SUITE_BASE2_MANIFEST.json`; per-file records: `output/SUITE_BASE2_SINK.jsonl`.

### Delta vs the SUITE-BASE-1 lock (256 files / 1608 collected / PASS 235 · FAIL 17 · TIMEOUT 4 @ `594f647`)

Now: **257 / 1671 / PASS 246 · FAIL 7 · TIMEOUT 4** → files **+1**, collected **+63**, PASS **+11**, FAIL **−10**, TIMEOUT **±0**.

Every record that moved, attributed to a commit in `594f647..e95a13d` touching `tests/`:

| file | change | attributed to |
|---|---|---|
| `test_run_containment.py` | new file, 9 collected, PASS | `1f49a92` (RUN-containment repair) |
| `test_spatial_ide.py` | FAIL 8 → PASS 8 | `3b71c46` (SUITE-FIX-1 leg 1a) |
| `test_glyph_file_io.py` / `test_glyph_audio_io.py` / `test_glyph_orchestrator_speak_to_driver.py` | FAIL → PASS | `4bcfe15` (cluster 2), `1f49a92` |
| `test_crc_patch.py`, `test_sbi_firmware.py` | FAIL → PASS | `2b5706a` (cluster 3) |
| `test_ollama_contextual_memory_simple.py` | FAIL 2 → PASS 2 | `fd9b4e0` |
| `test_griffin_lim.py` | FAIL 22 → PASS 22 | `e8e71f0` (DEFECT-28 file 3) |
| `test_vcc_validation.py` | FAIL 9 → PASS 9 | `6096519` (DEFECT-28 file 2) |
| `test_supply_census.py` | FAIL 5 → PASS 7 (+2 collected) | `539d418` (SUITE-CENSUS-1) |
| `test_suite_iso_harness.py` | PASS 10 → PASS 16 (+6 collected) | `6ede59a` (L10–L13) + `05b2860` (L14–L15) |
| `test_ollama_security_analysis.py` (+37), `test_pixel_lm_train.py` (+6), `test_probe_stval.py` (+1), `test_xv6_boot_regression.py` (+2) | TIMEOUT, collected `0 → n` | `6ede59a` — SUITE-COLLECT-1: these records used to hardcode `coll=0` on every kill; **+46 collected is an instrument correction, not new tests** |

Arithmetic check: 1608 + 46 (instrument) + 6 (harness legs) + 2 (census legs) + 9 (new file) = **1671** ✔
**The previously unattributed 18th test is now closed**: the delta is fully accounted for by named commits, with the
largest single term being the `coll=0` instrument correction rather than a test the earlier reconciliation could not find.

## 4. Honest boundaries — what this PASS does NOT prove

1. `head_sha` names the commit, never the working tree's dirty state; a sweep run on a dirty tree is anchored to the
   commit while its inputs differed from it. `head_moved_during_sweep` covers a *moving* HEAD, not a *dirty* one.
2. `--since` attribution sees only commits that touch the swept roots; a commit touching tests outside the declared roots
   would appear as `attribution_unexplained`.
3. The re-measure record in §3 was produced by the **pre-correction** harness, so it is anchored to `b8859ae` (see §2)
   while the tree under test was `af88284`/`05b2860`; the only difference between those revisions is
   `systems/GLYPH_SELF_HOSTING_ROADMAP.md`, which no test file in this sweep reads. The next sweep is the first that will
   be anchored at start.
4. The 7 remaining FAILs are `test_cross_modal.py` (DEFECT-28 file 1, RULING-PENDING) and `tests/test_syscall_handlers.py`
   (DEFECT-27, ABI-semantics ruling) — untouched here, and this row does not claim them.
5. `--since` compares counts, not identities: an equal-count swap (one test added, one removed in the same commit) yields
   `attribution_required: false`. The per-file diff has to be read for that case.
6. No memory containment and no multi-worker stress was added (`REPAIR_PENDING_suite_iso2_memory_containment.md` stands).

## Artifacts

* `.builder_queue/brief_suite_base2_commit_anchor.md` — the brief (validator: PASS, 0 warnings)
* `.builder_queue/probe_suite_base2_nonvacuity.py` / `probe_suite_base2_orchestrator.py` — RED + functional probes
* `.builder_queue/SUITE_BASE2_prev_manifest_backfill.json` — backfilled prior record (from the `ba54fb4` sink)
* `output/SUITE_BASE2_SWEEP.txt`, `output/SUITE_BASE2_SINK.jsonl`, `output/SUITE_BASE2_MANIFEST.json`,
  `output/SUITE_BASE2_orchestrator_probe.txt`
