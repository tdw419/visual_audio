# RECEIPT — DEFECT-25: five GH-20 fs_v2 legs no longer draft a live tile to gate arc leg A

**Row:** `DEFECT-25` — `systems/GLYPH_SELF_HOSTING_ROADMAP.md:359`
**Landed:** 2026-09-13, builder cron `af3e62239ce2`, branch `glyph-transpiler-autoloop`, base `e3a384b`
**Delegate:** `agy` from `.builder_queue/brief_defect25_gh20_live_draft_migration.md`
(exit 0, 443 s, log `output/agy/agy_impl_20260913_151320.log`). **Every number below is the orchestrator's
own re-run on the resulting tree**, not the delegate's claim.

Two changes in one gate-able step, because the sensor cannot go green without the migration:
**(1)** the arc-determinism audit learns to see a live draft that carries no `_ollama_available` reference;
**(2)** the five GH-20 fs_v2 legs stop drafting and gain deterministic siblings.

---

## 1. The gap, and the RED that proved the sensor needed extending

The shipped audit (`tests/test_arc_determinism_audit.py` as landed by DEFECT-24) detects only
decorator/`_ollama_available`/live-naming signals. The five GH-20 legs
(`tests/test_gh20_fs_v2.py:118,163,202,235,274`) draft a live tile through
`admit_syscall(..., contract=…)` with no draft seam and no `_ollama_available` reference, so they
were structurally invisible: **the wart could not see itself.**

Orchestrator replay at `e3a384b` with a clean tracked tree — `output/defect25_sensor_RED.txt`:

```
target            : tests/test_gh20_fs_v2.py (372 lines)
shipped sensor    : 0 violation(s) []
proposed signal   : 5 violation(s)
    tests/test_gh20_fs_v2.py::test_gh20_fs_append_grows_extents_clean
    tests/test_gh20_fs_v2.py::test_gh20_fs_rename_inplace_inode_preserved
    tests/test_gh20_fs_v2.py::test_gh20_fs_unlink_shared_refcount_fails_clean
    tests/test_gh20_fs_v2.py::test_gh20_canonical_replay_fixpoint_across_mutations
    tests/test_gh20_fs_v2.py::test_gh20_fs_ops_are_proven_table_tiles
GAP REPRODUCES: shipped_flags=0, proposed_flags=5, exact_five=True
```

**The naive version of that signal is unusable — measured, not assumed.**
`.builder_queue/probe_defect25_sensor_fp_v2.py` over the 52 arc-selector files, three candidate signals:

| signal | violations | verdict |
|---|---|---|
| substring match on `admit_syscall`/`ingest`/`escalate` | **14** | 9 false positives |
| last dotted component ∈ the three | 6 | 1 false positive |
| **+ the call carries a `contract=` keyword** | **5** | the five, exactly |

The 9 substring false positives are `tests/test_gh19_stdlib.py`'s eight `*_matrix` legs (the helper is
named `ingest_leg(...)`) — plus, at the exact-callee level,
`tests/test_gh12_autoatlas.py::test_family_whitelist_blocks_without_model_calls`, which passes its
contract **positionally** to a whitelist-rejected family and asserts `res.escalations == 0`, i.e. is
deterministic by construction. Measured before the brief was written, so the delegate implemented the
signal with the noise already characterised instead of discovering it as a red gate.

## 2. GREEN — every leg re-run by the orchestrator

| leg | command | result |
|---|---|---|
| G2 gate | `pytest tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q` | **14 passed** 43.34 s, exit 0 |
| G2b gating subset | `pytest tests/test_gh20_fs_v2.py -q -m "not live_smoke"` | **5 passed, 5 deselected** 0.84 s |
| G2c smoker set | `pytest tests/test_gh20_fs_v2.py --collect-only -q -m live_smoke` | exactly the **5** migrated legs |
| G3 sensor, live file | `find_unmarked_live_tests(test_gh20_fs_v2.py)` | `[]` |
| G3 sensor, pre-fix fixture | `find_unmarked_live_tests(arc_determinism_prefix_gh20.py)` | exactly the **5** |
| G4 class regression | `pytest tests/test_gh18_syscall_abi.py tests/test_gh12_escalation.py -q` | **17 passed** 7.47 s, exit 0 |
| G5 arc | `SEED=2026091321 suite_sweep.sh -b 12G -w 4 -- bash tools/arc_lega.sh` | **rc=0, crashes=0, 323 passed / 1 skipped / 9 deselected** in **64.83 s**, `oom_kill_delta=0`, `mem_peak=846,893,056 B` |

`-m "not live_smoke"` dropping **0.84 s** for the five gating fs legs — versus the ~10 s each they cost
when they drafted a live tile — is the whole point. The arc's deselected count moved 4 → 9 while
`passed` stayed at 323: that arithmetic is exactly the five drafting legs leaving the gating lane and
five deterministic siblings taking their place, so **no coverage was silently dropped**.
(`output/defect25_arc_sweep.txt`.)

## 3. Mechanised non-vacuity and discrimination (orchestrator probes)

`.builder_queue/probe_defect25_nonvacuity.py` → `output/defect25_nonvacuity_probe.txt`:

```
PART 1 — sensor non-vacuity
  real   sensor on pre-fix gh20 : 5 violations
  neutered (Signal 4 removed)   : 0 violations []
PART 2 — sibling discrimination (same seam, two tiles)
  A control (pinned tile)                    PASS
  B mutant (also writes slot-1 word 1032)    RED: slot 1 word 1032 clobbered
repo files byte-identical after probing: True
```

Part 1 proves the new predicate is what the replay leg tests (remove only that clause → 5 becomes 0,
so L4 is not passing for some other reason). Part 2 is the falsifier the brief demanded: a tile that
**passes the real oracle** but corrupts a neighbour FSTAB word is caught by the sibling's own guard —
a sibling that passes with a corrupting tile would have been decoration.

`.builder_queue/probe_defect25_dispatch.py` → `output/defect25_dispatch_probe.txt` attacks the one
place the migration could have been theatre: the loop legs dispatch the pinned tile by **substring of
the task text**, so if all three ops' augmented tasks contained the same digits they would all get the
same tile. Measured: `calls=3 distinct_tiles=['APPEND','RENAME','UNLINK']`,
`every served tile passed the REAL oracle: True`, rc=0.

## 4. The pinned tiles are supply, not invention

`tests/fixtures/fs_v2_op_tiles.py` pins one tile per op. Verified against the repo's own supply rather
than trusted: each is a **verbatim entry in `tools/glyph_gpt/corpus.jsonl`** with a recorded passing
oracle run —

| fixture constant | corpus entry | sys | recorded `oracle_exec_result` |
|---|---|---|---|
| `FSV2_APPEND_TILE` | `fs_append` (`autoatlas.py:fs_append`) | 10 | `status: pass`, 15 steps, `r2=0x0` |
| `FSV2_RENAME_TILE` | `fs_rename` (`autoatlas.py:fs_rename`) | 11 | `status: pass`, 14 steps, `r2=0x0` |
| `FSV2_UNLINK_TILE` | `fs_unlink` (`autoatlas.py:fs_unlink`) | 12 | `status: pass`, 16 steps, `r2=0x45` |

`0x45` is the seeded refcount≠0 refuse path's verdict, which is why the unlink legs' `expected` is the
errno and not `0`. The seam derives `verified` from `run_oracle(...).passed` — **nothing hand-asserts
`verified=True`**, and the real oracle + IR gate still run inside `ingest()`.

## 5. Mechanism

- `tests/test_arc_determinism_audit.py` — Signal 4 added to `find_unmarked_live_tests`: exact last
  dotted component ∈ {`admit_syscall`, `ingest`, `escalate`} **and** a `contract=` keyword on that call
  **and** no `monkeypatch` fixture **and** no `live_smoke` marker. Existing signals, violation-string
  form and signatures untouched; the positional-`contract=` blind spot is recorded in the module's own
  Limitations list. New leg `test_l4_nonvacuity_prefix_gh20_detected` pins the five names literally.
- `tests/test_gh20_fs_v2.py` — the five drafting legs carry `@pytest.mark.live_smoke`; each gains a
  deterministic sibling taking `monkeypatch`, installing the seam, and asserting the **same** chain
  (`res.ok`, `table_word != 0`, the leg's own FSTAB/errno/pixel observables) plus
  `len(connect_attempts) == 0` against a `socket.socket.connect` guard.
- NEW `tests/fixtures/arc_determinism_prefix_gh20.py` — pre-fix source of the GH-20 gate, replay fixture.
- NEW `tests/fixtures/fs_v2_op_tiles.py` — the three pinned tiles, `dispatch_fs_tile_by_contract`, and
  `install_fs_seam`.

## HONEST BOUNDARY — what this PASS does not prove

1. **The migrated siblings prove the pipeline, not the drafter.** They pin a known-good candidate and
   exercise admission → dispatch → oracle → in-image re-dispatch deterministically. A regression in the
   *live drafter's* ability to produce a verified FS tile for these contracts would **no longer turn the
   arc red** — it would only show up in the non-gating `live_smoke` legs. That is the deliberate trade
   of `RULING_gh12_gate_determinism` option 3, and it is a real reduction in what the arc detects.
2. **Positional contracts are invisible to the sensor** (documented limitation, and the reason
   `test_gh12_autoatlas.py`'s whitelist leg is not flagged). The sensor is static: a live draft nested in
   a helper with none of the four signals is still not caught.
3. **The pins are not tied to corpus freshness.** If `tools/glyph_gpt/corpus.jsonl` is regenerated with
   different tiles, the fixtures keep the old text and nothing re-checks the hash. A drift check was not
   in scope.
4. **`live_smoke` is still an unregistered pytest mark** — the run emits 5 ×
   `PytestUnknownMarkWarning`. Deselection works, but a misspelled mark would not be deselected.
   Filed as `.builder_queue/INSTRUMENT-1_live_smoke_mark_unregistered.json`.
5. **One seed, one order, host-side only.** `SEED=2026091321` is a single arc order; no multi-worker
   interleaving stress, no WGSL leg, no power-loss or memory-containment claim (that last one stays
   where SUITE-ISO-2 left it).
6. The audit's L1 covers 52 arc-selector files by the three filename globs in `_get_arc_files()`; a live
   leg in a file outside those globs is untouched by this change, as before.

## Discipline

RED before GREEN, both pasted above. Gates re-executed by the orchestrator. Files changed are exactly
`tests/test_arc_determinism_audit.py` and `tests/test_gh20_fs_v2.py` plus two new fixtures; no
engine/transpiler/WGSL/`tools/glyph_gpt/**` file was touched, so the worktree-isolation rule was not
triggered. No live guard was weakened: L1's assertion, L2's fixture equality and L3's `-m "not
live_smoke"` check are byte-identical to what DEFECT-24 landed, and every sibling asserts its leg's
full original chain.
