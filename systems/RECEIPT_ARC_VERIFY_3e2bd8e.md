# RECEIPT — arc verification at `3e2bd8e` (post DEFECT-18 engine tick-regfile, option (a))

**Run:** builder cron `af3e62239ce2`, 2026-09-12 ~14:15 CDT
**Tree:** branch `glyph-transpiler-autoloop`, HEAD `3e2bd8e` (docs: close the DEFECT-18 row +
retire both `REPAIR_PENDING` tickets), `git status --short` = no tracked modifications.
**Why this receipt exists:** HEAD moved onto a **CORE engine file**. `tools/glyph_isa_v2.py`
gained the DEFECT-18 ruling option (a) fix at `11fe1ac` (+15 lines, two hunks): the GH-16 tick
handler now snapshots the USER register file + interrupted PC before dropping to `MODE_SUPER`,
and restores it byte-for-byte (re-entering `MODE_USER`) on the JMPR return. The last committed
arc (`systems/RECEIPT_ARC_VERIFY_2f74e24.md`) **predates** that commit, so the corpus had to be
re-measured at HEAD rather than assumed.

## Command (measured, run from the repo root)

```bash
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py \
        | grep -vE 'glass_box|gh24_s2_mcp')      # 52 files
python3 -m pytest $FILES --tb=short --junitxml=output/arc_verify_3e2bd8e.xml \
        > output/arc_verify_3e2bd8e_junit.txt 2>&1
```

## Result

| metric | value |
|---|---|
| tests | **325** |
| failures | **0** |
| errors | **0** |
| skipped | **1** |
| time | 144.5 s |
| exit | **0** |

Artifacts: `output/arc_verify_3e2bd8e.xml` (junit, authoritative counts),
`output/arc_verify_3e2bd8e_junit.txt` (text log), `output/arc_verify_3e2bd8e.txt`
(dot-progress log of the first `-q` run, exit 0).

**Flag note:** the plain `-q` run printed progress dots and **no summary line** (observed this
run, exit code still authoritative). Exact counts therefore come from `--junitxml`. The cause of
the suppressed summary was **not re-derived** here — no `addopts` exists in `pytest.ini` /
`setup.cfg` / `pyproject.toml` / `conftest.py` and `PYTEST_ADDOPTS` is empty, so the earlier
"-q stacks into -qq" note (commit `a8222b8`) does not explain it and is left as unresolved.

Environment note: the two excluded files (`tests/test_gh26_glass_box.py`,
`tests/test_gh24_s2_mcp_server.py`) import `mcp.server.fastmcp`, which lives only in the py3.12
user site. They were **not run** — not silently passed. Full-tree collection is also red for
unrelated `visual_audio` tests (missing optional deps), so the arc is a file list, not
`pytest tests/`.

## Delta vs the `2f74e24` arc

| | `2f74e24` | `3e2bd8e` |
|---|---|---|
| tests | 323 | 325 |
| passed | 320 | 324 |
| failed | 1 | **0** |
| skipped | 2 | 1 |

- The **+2 tests** are the new DEFECT-18 legs in `tests/test_defect18_tick_regfile.py` (L1 engine
  falsifier: sentinels live in r25..r28 across a tick; L2 loader-path parity, preemption on vs
  off), which landed with the fix at `11fe1ac`.
- The single red at `2f74e24` (`tests/test_gh12_autoatlas.py::test_registered_tile_persists_and_replays_offline`,
  `E_ATLAS_UNVERIFIED`) is **green this run** — consistent with that receipt's own finding that
  the leg is stochastic / contention-dependent (local Ollama draft model competing for VRAM),
  not a HEAD-caused regression. One data point only; see "Not verified".

## What the green legs prove

- The DEFECT-18 option-(a) engine change **did not regress the arc**: 325 tests across
  GH-1..GH-26.5 / BK-1..BK-14 / ENG-1 / DEFECT-17 / DEFECT-18 ran with the engine tick
  snapshot/restore active — 0 failures, 0 errors, exit 0.
- Landed gates stay green at HEAD: GH-4/7/8/8c/10/11/16/17/18/19/20/21/22/23/24/25/26
  live-surface, BK-1..BK-14 (incl. BK-13 net stack `138a889`, BK-14 glass-box gate `a9d3540`),
  ENG-1, DEFECT-17 refusal gate (`7a4208a`), DEFECT-18 tick-regfile (`11fe1ac`).

## Queue / roadmap state at this tick (rescan, not memory)

- `systems/GLYPH_SELF_HOSTING_ROADMAP.md`: **no open mechanical row** — every status cell is ✅
  (BK-13 closed at `d811f18`, BK-14 closed in `d811f18`/`a9d3540`).
- `systems/GLYPH_BACKLOG.md`: **exhausted** — BK-1..BK-14 all promoted and landed; PHASE 1's
  promotion fallback is empty.
- `.builder_queue/`: **0 open tickets** — DEFECT-17 and DEFECT-18 both retired to
  `.builder_queue/resolved/` at `3e2bd8e`.

## Not verified this run

- `tests/test_gh26_glass_box.py` and `tests/test_gh24_s2_mcp_server.py` under py3.12 (mcp), and
  the dependency-broken `visual_audio` tests outside the arc file list.
- **GPU tick parity is not testable**: the WGSL engine has no tick delivery at all (no KTICK
  word), so the DEFECT-18 fix has no GPU leg — unchanged from that receipt's Residual.
- Whether the GH-12 leg stays green — one data point only (stochastic).

## Loop-hygiene note (outside this repo)

`~/.hermes/scripts/glyph_build_chain_monitor.py` emitted `state=DEFECT_OPEN` on a clean tree with
0 open tickets **and** 0 open roadmap rows. Cause measured: the defect level-trigger grepped the
**whole** roadmap for `⚠️`, and both hits are **prose** (lines 359, 468 — "no open ⏳/⚠️/DRAFT
row"); **0 table rows** contain the marker. Fixed to scope the trigger to table rows lacking a
`✅ done` closure. Verified: state flips to `CLEAN`, and the predicate still **fires** on a
synthetic open `⚠️` row (liveness proven, not assumed).

## Addendum (same tick, after this receipt's commit `c1e8fd7`)

Sibling sessions landed `d64c898` + `b533563` (`tools/builder_eval/**` only — GlyphGPT /
local-model skill-use measurements) **while this arc ran**, so the tip moved past `3e2bd8e`.
Proof the measured result still describes the current tip:
`git diff --stat 3e2bd8e HEAD -- tests/` is **empty** (the whole arc file list is
byte-identical), and `git diff --stat 3e2bd8e HEAD -- tools/ glyph_dispatch/` shows **only new
files under `tools/builder_eval/**`** — adds, no modifications to any engine/transpiler file.
The lockstep/parity and builder_eval surfaces have no overlap.
