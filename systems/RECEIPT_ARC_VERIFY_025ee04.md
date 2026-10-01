# RECEIPT — arc + gate re-verification at `025ee04` (hold, tick 2026-09-12 21:0x CDT)

**Run:** builder cron `af3e62239ce2` · **Tree:** `glyph-transpiler-autoloop` @ `025ee04`
**Trigger:** the monitor saw HEAD move (`db08a95` → `025ee04`) and `tracked_dirty` 2 → 1.
Both are this lane's own commits, but the census conclusion ("lane complete, nothing eligible")
rests on **gates**, and the committed arc receipt (`systems/RECEIPT_ARC_VERIFY_3e2bd8e.md`) is
**69 commits old**: everything from OS-SKEL R2/R3, SPINE R1, WF-1 and OBS-1 landed after it.
`git merge-base --is-ancestor 3e2bd8e HEAD` → true, so the range is linear, not a branch illusion.

Inherited green is not evidence at a new HEAD, so the corpus was re-measured rather than assumed.

## 1. Arc corpus (the committed selection, unchanged from the 3e2bd8e receipt)

```bash
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py \
        | grep -vE 'glass_box|gh24_s2_mcp')          # 52 files
/usr/bin/python3 -m pytest $FILES -q --tb=short --junitxml=output/arc_verify_025ee04.xml \
        > output/arc_verify_025ee04.txt 2>&1
```

| metric | value |
|---|---|
| tests | **325** |
| failures | **0** |
| errors | **0** |
| skipped | 1 |
| time | 151.0 s |
| exit | 0 |

Counts read from `output/arc_verify_025ee04.xml` (`testsuite/@tests,failures,errors,skipped`),
not from the console tail — `-q` here prints no summary line, so the XML is the authority.

## 2. The gate modules that landed *after* the last arc (never re-run as a group)

```bash
/usr/bin/python3 -m pytest tests/test_osskel_*.py tests/test_spine_r1_*.py \
        -q --tb=short --junitxml=output/osskel_spine_verify_025ee04.xml
```

| metric | value |
|---|---|
| tests | **100** (8 OS-SKEL modules + 7 SPINE R1 modules) |
| failures / errors / skipped | **0 / 0 / 0** |
| time | 0.57 s |
| exit | 0 |

## 3. The headline guards, at HEAD

```bash
/usr/bin/python3 -m pytest tests/test_osskel_engine_switch.py tests/test_obs1_mcp_transport_identity.py \
        tests/test_wf1_tick_claim_bound.py tests/test_bk14_demo.py tests/test_defect20_write_identity.py -q
```
→ **23 passed, exit 0.**

**Interpreter:** all runs use `/usr/bin/python3`. The repo `.venv/bin/python` cannot import
`mcp.server.fastmcp`; a green gate in that venv reads as a red gate (repeat of the standing trap).

## 4. Census re-run (not re-read from the note)

- `.builder_queue/probe_roadmap_state_audit.py` → self-hosting **55 id rows / 0 open**;
  OSS lane 13 id rows / 8 open (GL-2, GL-6, GL-7 🟡 = *no status token* in that parser's set ⇒
  conservatively open; GL-8 human; GL-9..GL-12 `after` chains).
- Backlog: 15/15 promoted & closed (`probe_backlog_promotion_state.py`, prior tick, not re-derived here).

## 5. Teleop freshness (glyph-teleoperation discipline: meta before surface)

`geos_surface_meta` (geo-obs MCP, 80×25 @ origin) → `tick: 0`,
`source.age_seconds: 184849.6` (51.35 h). Independent `stat /tmp/geos_observation/kernel_memory.npy`
→ mtime `2026-09-10 17:48:25 CDT`, i.e. **51.35 h** against wall clock `2026-09-12 21:09 CDT`
— agreement to 0.00 h. **The machine is not stepping**, so no canvas read was performed and no
conclusion is drawn from the canvas; the tick-0/51 h pair is reported as the freshness bound.

## 6. OSS lane (fence check only)

`/home/jericho/zion/worktrees/glyph-isa` → clean, HEAD `0aa14b1` (GL-7), preceded by `b5aa3f2` (GL-6).
Unchanged from the prior tick's reading; its gates were **not** re-run this tick (out of lane).

## Conclusion

Nothing regressed. The hold stands: no self-promotable item exists in this lane, so there is
nothing to delegate, and inventing one would be scope the rulings forbid
(`RULING_lane_supply_20260912.md` § Reserved, `RULING_next_lane_OSS_GL6_GL7.md` § Conditions).

## Provenance correction (added 21:1x CDT, same tick)

The header says the tree is at `025ee04`; that is the HEAD the run **started** at, and it stayed the
merge base of the measured tree — but the sibling `tools/builder_eval/` lane committed **twice while
these gates were running**: `252cdb1` (21:05:50) and `9e0aba9` (21:08:51), both `tools/builder_eval/`
only (7 files, +850/−5; `ollama_tile_draftsman.py` +27/−5). My own commit therefore sits on `9e0aba9`,
not on `025ee04`.

This does not weaken the result, and it is stated rather than glossed because it is the sort of
provenance detail the `db08a95` near-escalation was about:

- `grep -rln builder_eval tests/` → **0 files**: no test in the arc selection (or anywhere under
  `tests/`) imports or executes the sibling lane, so those commits cannot change the arc outcome.
- the two sibling **data** files were dirty (`results.jsonl`, `ollama_tile_results.json`) and one
  code file (`ollama_tile_draftsman.py`) changed mid-run — none of them is on the arc's import path.
- all three runs were re-observable: the XML artifacts on disk carry the counts quoted above.

Not re-run against `9e0aba9` explicitly — the argument above is a path-independence argument, not a
second measurement. If that distinction matters for a future claim, re-run the arc at the then-HEAD.

**NOT verified this tick:** the full `tests/` tree (264 `.py` files live under `tests/`; only the
52-file arc selection plus the 15 new OS-SKEL/SPINE modules were run); GPU tick parity (unmeasurable by
construction — the WF-1 bound); OSS-lane gates; the *content* of the sibling
`tools/builder_eval/` work (`results.jsonl`, `ollama_tile_results.json` are dirty with another
session's in-flight edits and were deliberately not staged or read).
