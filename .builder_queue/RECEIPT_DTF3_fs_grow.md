# RECEIPT — DTF-3 desktop-floor rung 3: FS grow measured at HEAD + WGSL twin-boundary truthed

**Date:** 2026-09-22 ~20:3x CDT
**Builder:** af3e62239ce2 (product lane)
**Base revision:** 2629d9a5 (item 10 / DTF-2 landing; tree CLEAN at tick start)
**Scope touched:** `.builder_queue/probe_dtf3_twin_boundary.py` (NEW, re-runnable),
this receipt, `PRODUCT_ROADMAP.md` (DTF-3 row annotation only),
`PRODUCT_LANE_STATE.md` (ledger). No engine, shader, codec, or protected-asset
changes.

## What the rung turned out to be (same shape as DTF-1)

The amendment's DTF-3 gate assumed the test file might not exist ("RED-first
(test file does not exist; row authorizes creating it)"). Measured this tick:
**BK-7 landed 2026-09--11** — commit 153b5edb ("feat(bk7): FS grow — SYS 9
append + len-driven whole-file read + hole reuse"), ancestor-of-HEAD verified
(`git merge-base --is-ancestor`), with its own receipt
(`systems/RECEIPT_BK7_FS_GROW.md`) and its own RED-first arc
(`output/bk7_gate_run1_red.txt` → `.../bk7_gate_run2_green.txt`, per that
commit message). So the claimable work this tick was: measure at HEAD, truth
the twin boundary, receipt, promote the roadmap row. No FS code changed.

## Gate at HEAD (the amendment's binding gate)

```
.venv/bin/python -m pytest tests/test_bk7_fs_grow.py -v
  test_bk7_two_appends_grow_file_and_read_back PASSED
  test_bk7_delete_creates_reusable_slot PASSED
  2 passed in 0.08s
```

Regression family (defect_d RAM-scoped handlers + gh20 FS-v2 + pillar21
ABI rot-guard + bk7): **67 passed, 0 failed** in 43.28s.

## New measurement this tick: WGSL twin boundary

The amendment said: "WGSL twin: FS handlers are host-side; record
twin-boundary note per SYSCALL_ABI_SPEC convention." **The premise is wrong —
measured, not assumed.** The GH-8b FS kernel (SYS 6 create / 7 read / 9
append) is IN-IMAGE guest code baked by `fs_kernel_image()`
(tools/glyph_gpt/baker.py:1481); no host handler exists for it. Therefore the
WGSL twin should EXECUTE it. Probe `.builder_queue/probe_dtf3_twin_boundary.py`
ran the append image on BOTH engines:

- CPU oracle (GlyphRunner.run): halted, not faulted, 273 steps, all 14 FS
  assertions PASS (slot0 name/len=16/in_use; data extent incl. both appended
  words 0x99AABBCC, 0xDDEEFF10; read-out window 4 words byte-exact; exits
  0xFEED0006/7; status 0xCAFE0008 @950).
- WGSL shader path (GlyphRunner.run_wgsl, this machine's GPU): halted, not
  faulted, **273 steps** (identical), all 14 FS assertions PASS from
  `receipt["ram"]`.
- Full-RAM diff CPU-vs-WGSL: 8 words, ALL inside the BOX_MMIO mirror block
  8192-8210 (KFAULT_PC@8193, KSYS_PC@8194, BOX0/1 regs@8195-8198,
  SYSCALL_PC@8201, SYS_A0/A1@8205-8206) — the twin holds MMIO in its own
  160-word binding while the CPU engine mirrors it into RAM. Known
  engine-storage boundary (SE022a binding layout), NOT FS drift.
  **Zero non-MMIO diffs across all 16,384 words.**

**Twin-boundary note (the rung deliverable, corrected premise):** SYS
6/7/9 append/read/create execute on BOTH engines with word-exact FS state.
There is no host-side FS handler to fence off; no SYSCALL_ABI_SPEC block is
needed (SYS 6/7/9 are in-image kernel conventions, not engine syscall arms —
the spec's 12 blocks 0x01..0x12 are unchanged). VERDICT: **MATCH, exit 0.**

## RED leg (rule 4, shown before trusting GREEN)

Corrupted-expectation run (BK7_PAYLOAD2 → 0xDEADBEEF) against the same live
engines:

```
[CPU] FAIL: data2==append1, readout2==append1
[WGSL] FAIL: data2==append1, readout2==append1
VERDICT: DIVERGENT
RED-LEG EXIT: 1
```

The probe discriminates: it fails on BOTH engines when an expectation is
false, and its pass cannot be produced by a vacuous all-true dict.

## Probe-defect record (landing-time, kept)

First draft read `runner.image` post-run for the WGSL leg — run_wgsl never
writes the read-back buffer into `.image`, so the pixel reads decoded
pre-execution zeros and the probe RED'd for the wrong reason. Fixed to read
`receipt["memory"]` (BK-2 view of the read-back buffer), then re-scoped the
assertions to `receipt["ram"]` — the FS state is RAM-homed by design
(RECEIPT_SE021 lineage: single-view over RAM), and pixel words hold only the
program region on the twin. The final probe asserts RAM parity on both
engines, which is the established round-2 item-5 convention.

## Honesty — what this PASS does NOT prove

- Single machine, single GPU (this host's wgpu device); no second-machine claim.
- Hole-reuse leg (L2) measured CPU-oracle only (existing gate); the WGSL leg
  here exercised the APPEND image. No WGSL hole-leg was run — a bounded gap,
  probe and image both support adding it later (fs_kernel_image(hole_leg=True)
  → run_wgsl), not load-bearing for the rung's gate text.
- The 8-word MMIO-block diff is classified, not eliminated — the twin's MMIO
  stays in its own binding; any future consumer reading guest MMIO via CPU RAM
  mirror must know this (already the SE022a contract).
- No rate claims → floors/check_regime N/A.
- NOT done: DTF-4 (coreutils vol. 1) untouched — next rung, depends on this
  one; no RECEIPT_DTF_floor.md yet (that is the floor-exit artifact after all
  four rows, plus the agent pre-verification receipt which is the seat lane's).

## Verdict

DTF-3 rung: **DONE** — gate green at HEAD (67 passed incl. the binding 2/2),
twin boundary measured and recorded (MATCH), roadmap row promoted, ledger
updated. Desktop-floor progress: DTF-1 ✅, DTF-2 ✅, DTF-3 ✅, DTF-4 open.
