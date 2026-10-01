# RECEIPT — arc verification at `2f74e24` (post DEFECT-17 refusal gate)

**Run:** builder cron `af3e62239ce2`, 2026-09-12 ~13:40 CDT
**Tree:** branch `glyph-transpiler-autoloop`, HEAD `2f74e24` (docs: retire the DEFECT-17 ticket),
`git status --short` = no tracked modifications (tracked_dirty=0).
**Why this receipt exists:** HEAD moved twice today on a CORE file (`tools/rv64i_to_glyph.py`
gained the named `REFUSAL: RV x31 (t6)` guard at `7a4208a`). A refusal gate is a
new hard-fail path, so the corpus had to be re-measured at HEAD, not assumed.

## Command (measured, run from the repo root)

```bash
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect17*.py \
        | grep -vE 'glass_box|gh24_s2_mcp')
python3 -m pytest $FILES -q --tb=no > output/arc_verify_2f74e24.txt 2>&1
```

## Result

| metric | value |
|---|---|
| collected | **323** |
| passed | **320** |
| failed | **1** |
| skipped | **2** |
| exit | 1 |

Environment note: the two excluded files (`tests/test_gh26_glass_box.py`,
`tests/test_gh24_s2_mcp_server.py`) cannot be collected under the cron's Python 3.11 —
both import `mcp.server.fastmcp`, which lives only in the py3.12 user site. They were
not silently passed; they were **not run**. Full-tree collection is also red for
22 unrelated visual_audio tests (missing optional deps), so the arc is a file list,
not `pytest tests/`.

## The single red is pre-existing and stochastic, not a regression

`tests/test_gh12_autoatlas.py::test_registered_tile_persists_and_replays_offline`
→ `E_ATLAS_UNVERIFIED: no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT`.

Evidence that HEAD did not cause it:
- The same test leg is already red in the pre-HEAD arc record `output/DEFECT19_arc_postfix.txt`
  (which additionally had `test_full_loop_miss_to_verified_kernel_dispatch` red — this run it passed),
  so the leg moves run-to-run on its own.
- Its producer is a **local LLM draft**: the test is `skipif(not _ollama_available())`, and Ollama
  IS up. Model routing is intact — `qwen2.5-coder:14b` (the `autoatlas.py:234/456` default) is
  installed. What changed is contention: `qwen3-coder:30b` was loaded on the same GPU
  (`/api/tags` modified_at 13:20 CDT, runner process live), so the local draft model is
  competing for VRAM while the gate asks it for a verifying tile.
- Nothing in the failing path touches the x31 scan.

## What the green legs prove

- **The x31 refusal gate did not regress the arc**: 323 tests across GH-1..GH-26.5 / BK-1..BK-14 /
  ENG-1 / DEFECT-17 ran with the guard active and **zero** `RVX31RefusalError` was raised —
  consistent with the scan receipt (`28 programs / 8,006 instructions / 0 x31 refs`).
- Landed gates stay green at HEAD: GH-4/7/8/8c/10/11/16/17/18/19/20/21/22/23/24/25/26 live-surface,
  BK-1..BK-14 (incl. BK-13 net stack, BK-14 glass-box gate), ENG-1, DEFECT-17 refusal 11/11.

## Queue / roadmap state at this tick (rescan, not memory)

- Roadmap `systems/GLYPH_SELF_HOSTING_ROADMAP.md`: **no open mechanical row.**
  GH-24 is ✅ S1+S2 with **S3 write path HUMAN-GATED**; GH-25 is a horizon stub (gate legs ✅);
  BK-13 closed at `d811f18` (implementation `138a889`).
- `systems/GLYPH_BACKLOG.md` candidate list is **exhausted**: BK-1..BK-14 all have roadmap rows
  and all are landed. There is no item left to promote under the standing promotion rule.
- `.builder_queue/`: one open design ticket — **DEFECT-18** (`REPAIR_PENDING_defect18_tick_identity_map.md`),
  exempt from auto-work (needs Jericho's ruling). DEFECT-17 was closed and its ticket retired to
  `.builder_queue/resolved/` at `2f74e24`.

## Not verified this run

- `tests/test_gh26_glass_box.py` and `tests/test_gh24_s2_mcp_server.py` under py3.12 (mcp),
  and the 22 dependency-broken visual_audio tests.
- Whether the GH-12 leg goes green again once the GPU is idle — one data point only.
