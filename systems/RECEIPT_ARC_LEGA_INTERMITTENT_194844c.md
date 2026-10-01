# RECEIPT — arc leg A at HEAD `194844c`: green, but not reliably green (2026-09-13, cron `af3e62239ce2`)

**Trigger.** The monitor saw HEAD move `8943601` → `194844c` (TEST-COL-1 landed: `039ce3b` changed
`pytest.ini`, `tests/conftest.py`, `tests/test_bk8_fs_pix_sha256.py` and three `glyph_dispatch/src`
modules — all inside the arc's dependency closure). The standing rule from
`REPAIR_PENDING_lane_supply_exhausted.md` therefore required the arc to be **re-run, not assumed**.

**Interpreter:** `/usr/bin/python3` (py3.12, the one with `mcp`) for both legs.

## What was run

```bash
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
/usr/bin/python3 -m pytest $FILES -q --junitxml=output/arc_verify_194844c_run<N>.xml   # leg A, 52 files
/usr/bin/python3 -m pytest tests/test_osskel_*.py tests/test_substor_*.py tests/test_obs1_*.py \
        tests/test_wf1_*.py tests/test_spatial_rv32i_cpu.py -q --junitxml=output/arc_legB_194844c.xml   # leg B
```

Driver script: `.builder_queue/arc_legA_rerun.sh` (runs 4–5).

## Leg A: five runs, three green, two disturbed

| run | rc | result | evidence |
|---|---|---|---|
| 1 | 1 | **1 failed**, 323 passed, 1 skipped, 159.70 s — `tests/test_gh12_autoatlas.py::test_registered_tile_persists_and_replays_offline` | `output/arc_legA_194844c.txt` |
| 2 | **139** | **SEGFAULT** (`Fatal Python error: Segmentation fault`) at ~44 % + 23 dots, killed the process | `output/arc_legA_194844c_run2.txt` |
| 3 | 0 | 324 passed, 1 skipped, 141.47 s (run with `-p no:randomly`) | `output/arc_legA_194844c_run3.txt` |
| 4 | 0 | 324 passed, 1 skipped, 140.75 s | `output/arc_legA_194844c_run4.txt` |
| 5 | 0 | 324 passed, 1 skipped, 139.13 s | `output/arc_legA_194844c_run5.txt` |

Collected set is stable: 324 passed + 1 skipped = 325 (matches `RECEIPT_ARC_VERIFY_025ee04.md`'s 325).

### Anomaly 1 — gh12 admission gate red (run 1)

```
tests/test_gh12_autoatlas.py:141: AssertionError
E   AssertionError: no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT
E   assert 'E_ATLAS_UNVERIFIED' == 'OK'
```

The test is `@pytest.mark.skipif(not _ollama_available(), ...)`; `http://localhost:11434/api/tags`
**is** reachable on this host (`qwen3-coder:30b`, plus a resident runner started 04:00), so the leg
executed rather than skipping. Its verdict depends on what the local model drafts and whether the
drafted tile halts — i.e. **the gate contains an LLM sampling step**.

### Anomaly 2 — segfault inside the engine's step path (run 2)

```
Fatal Python error: Segmentation fault
Current thread ... (most recent call first):
  tools/glyph_isa_v2.py:561 in step
  tools/glyph_isa_v2.py:1114 in run
  tools/glyph_gpt/generate.py:370 in run_generated
  tools/glyph_gpt/atlas.py:49 in register
  tools/glyph_gpt/atlas.py:239 in build_default_atlas
  tests/test_gh22_device_driver_abi.py:155 in _bake
  tests/test_gh22_device_driver_abi.py:174 in test_gh22_driver_abi_image_bakes
```

Every frame is pure Python; there is no deeper Python caller and no C-extension frame named, so the
fault is in a C-level call made under `step` (native widening of the stack region) — **cause NOT
diagnosed**. Host memory is not the explanation: 62 GB RAM, 47 GB available, no OOM in the run.

## Isolation probes (the discriminator)

| probe | command | result |
|---|---|---|
| gh12 admission leg alone | `pytest tests/test_gh12_autoatlas.py::test_registered_tile_persists_and_replays_offline` ×3 | **3/3 rc=0** (`output/gh12_isolated_rep{1,2,3}.txt`) |
| gh22 bake leg alone | `pytest tests/test_gh22_device_driver_abi.py::test_gh22_driver_abi_image_bakes` ×3 | **3/3 rc=0**, 1 passed in ~0.9 s each (`output/gh22_isolated_rep{1,2,3}.txt`) |

So both anomalies are **context-dependent, not file-local**: neither reproduces in isolation at the
same head. **n = 2 disturbed runs out of 5 — reported as two one-off observations, not a rate**
(the loop's own rule: a single trial is a coin flip; no causality is claimed).

## Leg B — green

`83 passed in 8.51 s`, rc=0 (`output/arc_legB_194844c.txt`, junit `output/arc_legB_194844c.xml`).
This is the leg that covers the suites the old 52-file list omitted (`test_osskel_*`, `test_substor_*`,
`test_obs1_*`, `test_wf1_*`, `test_spatial_rv32i_cpu.py`).

## Supply census at `194844c` (re-measured, not inherited)

- `.builder_queue/probe_roadmap_state_audit.py` → self-hosting roadmap **57 id rows / 1 flagged open**:
  `TEST-COL-1` (line 351) as `NO STATUS TOKEN`. **Read and discharged:** that row's status cell is a
  long closure narrative ending `✅ done`, so the flag is a classifier artifact (the cell does not
  *open* with a state token), not open work. **0 genuinely open rows.**
- OSS lane: 13 rows / 8 open — all reserved (GL-2 needs a fresh-eyes reader; GL-6/GL-7 publication is
  Jericho's; GL-8 outside human; GL-9..GL-12 carry `after` chains). Not poachable.
- `.builder_queue/*.json` open tickets: **0** at start of tick.

## Honest boundaries of this receipt

- **Not diagnosed:** the segfault's mechanism. The only falsifiable statement made here is the stack
  and the fact that the standalone leg passes 3/3.
- **Not measured:** whether pytest-randomly was actually active in runs 1–5. It is **installed**
  (`~/.local/lib/python3.12/site-packages/pytest_randomly`), and `-q` suppresses the header that would
  print `Using --randomly-seed=…`, so run-to-run *order* variation is a **hypothesis for the
  intermittency, not evidence**. Run 3's `-p no:randomly` is therefore a confound, not a fix.
- **Not run:** the full `tests/` suite to completion (still unbounded — 4 % in ~4 min, per
  `NOTE_glyph_dispatch_lane_syspath_and_slow_suite.md` § 2); any WGSL/GPU parity leg; the OSS worktree.
- **Not verified:** that the disturbance is caused by the landed TEST-COL-1 change. Both disturbed
  runs are at the same head as the three green runs, so no causal claim is possible from this data.

## Files

- new: this receipt, `.builder_queue/arc_legA_rerun.sh`, `.builder_queue/DEFECT-22_arc_legA_instability.json`,
  `.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md`, six `output/*_isolated_rep*.txt`
- no source file was modified by this tick.
