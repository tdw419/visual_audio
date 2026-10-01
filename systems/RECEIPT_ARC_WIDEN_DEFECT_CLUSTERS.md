# RECEIPT — arc selector widened to the full defect-cluster set (DEFECT-30 follow-up)

**Date:** 2026-09-16 ~12:4x CDT · **Builder:** orchestrator cron af3e62239ce2 · **HEAD at landing:** 1c7c50f
**Provenance:** `.builder_queue/DEFECT-30_stale_l4_pin_after_5site_naming.md` § Follow-up filed;
brief `.builder_queue/brief_arc_widen_defect_clusters.md` (check_brief PASS).

## Symptom → fix chain

DEFECT-30's stale L4 pin (`tests/test_defect23_pte_acceptance.py`) went RED at
`fd24c76` and **the arc stayed green** — because `tools/arc_lega.sh`'s selector
glob was `test_defect1*`, predating the defect20/defect23/defect-d clusters.
Any future red in those 8 files (32 tests) would be invisible to the arc again.
Fix: widen the glob to `test_defect*` in BOTH runners (arc_lega.sh +
arc_lega_capture.sh, byte-identical mirror) and in the determinism audit's
`_get_arc_files()`, and PIN the three-way parity with a new gate.

## Files

- `tools/arc_lega.sh` — FILES glob `test_defect1*` → `test_defect*` (selector line only)
- `tools/arc_lega_capture.sh` — mirrored byte-identical
- `tests/test_arc_determinism_audit.py` — `_get_arc_files()` pattern list only
- `tests/test_arc_selector_parity.py` — NEW gate (4 legs)
- `.builder_queue/probe_arc_widen_red.sh` — RED-first probe

## Gate

`/usr/bin/python3 -m pytest tests/test_arc_selector_parity.py tests/test_arc_determinism_audit.py tests/test_instrument1_mark_registration.py -q -m "not live_smoke" -p no:randomly`
→ **12 passed, rc=0** (`output/arc_widen_gate_orch.txt`).

Legs: L1 both runners' selector expansions name all 6 cluster files (extracted
from the REAL scripts, expanded via shell — not transcribed); L2 the two
expansions are byte-identical; L3 the audit's file set covers the same clusters
and audits nothing the arc doesn't run; L4 non-vacuity — the same detector
run against the OLD `test_defect1*` expansion flags all 6 as missing.

## RED first (`.builder_queue/probe_arc_widen_red.sh`, `output/arc_widen_probe_green.txt`)

- LEG-A1: gate run with `Path.glob` monkeypatched back to the old narrow glob
  → **1 failed** (`test_l3_audit_covers_same_cluster_files`: audit misses the
  cluster files) — the gate DETECTS the pre-widen shape. (First probe draft
  RED'd with ModuleNotFoundError — a probe bug, not evidence; fixed before
  trusting. The RED is now the detector failing, not an import.)
- LEG-A2: same gate, widened glob → 4 passed, rc=0.
- LEG-B: the widened runner selector names exactly the 6 cluster files,
  including `test_defect23_pte_acceptance.py` — the file whose red went unseen.

## Arc (the acceptance itself)

`SEED=202609165 VERBOSE=0 OUTDIR=output bash tools/arc_lega.sh` at 1c7c50f →
**353 passed, 1 skipped, 9 deselected, 2 xfailed, rc=0, 71.28s, crashes=0**
(`output/arc_lega_seed202609165_1c7c50f.{txt,json}`).
Baseline at the same content minus this change: 323 passed / 1 skipped
(`output/arc_lega_seed202609162_fd24c76.json`). Δ = **+30 passed +2 xfailed**,
which is exactly the defect-cluster suite measured standalone this tick
(30 passed, 2 xfailed, 2.92s) — arithmetic confirmation the new files are
collected and green inside the arc.

## What this PASS does NOT prove

- Wall-clock budget at the wider denominator: one run measured (71s vs ~75s
  before — within noise), not a distribution; the +32 tests cost ~3s standalone.
- Coverage beyond the four glob families: a future test file named outside
  `test_{gh,bk,eng,defect}*.py` is still invisible to the arc (unchanged gap,
  now pinned in L3's shape so adding a family means touching the parity gate).
- The defect-cluster tests are NOT in the pre-commit hook (that hook gates only
  ISA/transpiler paths) — the arc remains the only standing execution of them.
- No repo-wide sweep ran; sibling lane is live in this tree ((d) handler
  migration, commits fd24c76/1c7c50f) — this change touches no engine file.

## Honest boundaries

The exclusion list (`glass_box|gh24_s2_mcp`), the live_smoke deselector, seed
pinning, artifact naming, and OOM-survival records are untouched. A future
defect-cluster file is covered by construction (glob), not by list edit; only
`CLUSTER_FILES` in the parity gate needs the new name for the non-vacuity pin.
