# RECEIPT — SPINE-R1: archive-retention + write-registry skeleton, populated and gated

**Round:** SPINE-R1 (Phase 3 population of `tools/geos_archive.py` and `tools/geos_registry.py`)
**Skeleton (locked, is the spec):** `systems/GLYPH_SPINE_SKELETON.md` @ `95ee58f`
**Authority:** `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item (3) — the lane reported supply
exhaustion, so the loop was authorized to author the two spine items named in the ruling; the architecture was
locked first (`95ee58f`), which turned those structural questions into mechanical work.
**Round plan:** `.builder_queue/brief_spine_r1_phase3.md` (six steps, one per run) + `.builder_queue/brief_spine_r1_step7_lookup.md` (seventh step, provenance below)
**Executed by:** builder cron `af3e62239ce2` — `agy` implemented each step from a per-step brief; the orchestrator
re-ran every gate on the resulting tree, ran out-of-tree falsification probes, ran the arc regression, and committed.
**Date:** 2026-09-12 · **Branch:** `glyph-transpiler-autoloop`

## 1. What landed

| Step | Body populated | Gate module | Gate | Commit |
|---|---|---|---|---|
| 1 | `ArchiveStore.plan()` (read-only scan) | `tests/test_spine_r1_plan.py` | 9/9 | `531bfaa` |
| 2 | `ArchiveStore.compact(plan)` | `tests/test_spine_r1_compact.py` | 7/7 | `2e10286` |
| 3 | `compact()` cross-reference refusal | `tests/test_spine_r1_refuse.py` | 7/7 | `0bc756a` |
| 4 | `WriteRegistry.register()` + persistence | `tests/test_spine_r1_register.py` | 9/9 | `8e7878d` |
| 5 | `WriteRegistry.scan(root)` | `tests/test_spine_r1_scan.py` | 8/8 | `b3090a4` |
| 6 | `WriteRegistry.conflicts()` | `tests/test_spine_r1_conflicts.py` | 5/5 | `6d07f7f` |
| 7 | `WriteRegistry.lookup()` | `tests/test_spine_r1_lookup.py` | 5/5 | `b6577a5` |

All seven gates together: **50 passed, exit 0** (`output/spine_r1_step7_all_gates_orch.txt`).
Structural harness `python3 tools/geos_spine_verify.py`: **PASS — structure locked, pure core discriminating,
stubs typed** (`output/spine_r1_step7_spine_verify_orch.txt`), exit 0.
Arc regression `/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_spine_r1_*.py -q`:
**exit 0** (`output/spine_r1_step7_arc.txt`; step 6's run `output/spine_r1_step6_arc.txt` likewise).
No tracked file outside `tools/geos_registry.py` / `tools/geos_archive.py` and `tests/test_spine_r1_*.py` was
modified by the round; no core file (`tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`,
WGSL) was touched, so AGENTS.md worktree isolation was not required. Test modules are hidden by the `.gitignore`
`test_*.py` rule and were force-added.

Every step has the loop's RED→GREEN discipline: RED at module-absent baseline (pytest exit 4), RED again with the
pre-step implementation restored where a body already existed, then GREEN with the orchestrator's own re-run; the
literal tails are in each commit body and in `output/spine_r1_step*_*.txt`.

## 2. The two judgment calls worth recording

1. **`conflicts()` must read the persisted index, not `self.entries`.** `register()` refuses duplicate keys
   (`tools/geos_registry.py:188-190` names the asymmetry with `conflicts()`'s `>1 distinct line_sha` rule), so an
   in-memory-only implementation is *vacuous by construction* — it could never observe the state it exists to
   detect. The step-6 gate therefore builds the conflicting history **on disk directly**, and the falsification
   probe `diskblind` (`for raw in []`) turns L1/L4/L5 red, proving the gate enforces the disk read rather than the
   shape of the implementation.
2. **A seventh step was added.** The round brief enumerated six and omitted `lookup()`, but
   `systems/GLYPH_SPINE_SKELETON.md:59` lists all four `WriteRegistry` bodies as Phase-3 stubs, and step 6's commit
   recorded the residual: `lookup()` still returned `[]` unconditionally with **no gate covering it** (the harness
   at `tools/geos_spine_verify.py:102` only asserts it returns a list) — a detectable failure that nothing could
   detect. Closure over that stub was rejected; step 7 populates and gates it in the same locked interface
   (no signature change, no design judgment). Provenance: `.builder_queue/brief_spine_r1_step7_lookup.md`.

## 3. Falsification (beyond the gates)

Named mutations were applied to `tools/geos_registry.py` out-of-tree, the gate re-run, and the file restored
byte-identically each time (`md5sum -c`; step 6 `6097aaa457b37b8b2d80eb755f9e8cfa`, step 7 `7029104cd0ec94f4b549f77b43d7539f`):

| Mutation | Reddened legs |
|---|---|
| step 6: discriminator inverted (`len(shas) > 0`) | L2, L3, L4, L5 |
| step 6: `return {}` at the body head | L1, L4, L5 |
| step 6: disk read blinded | L1, L4, L5 |
| step 7: `return []` at the body head | L1, L4, L5 |
| step 7: **`self.entries`-only search** | **L4 alone** (the disk-truth leg) |
| step 7: key filter disabled | L1, L2, L5 |
| step 7: fabricated entry on the absent-index path | L3 |

Every leg of both step gates is reddened by at least one mutation. Note the honest inverse: against a
`return {}` stub, step 6's L2/L3 pass by design (they are negative legs) — their discrimination is shown only by
the inversion probe above, which is why the inversion probe was run.

## 4. What this receipt does NOT claim

- **No wire-in.** `tools/geos_emit.publish()` does not write the registry, and there is no operator-invocable
  retention command. The round brief scoped that to a separate round with its own gate; nothing in the publish or
  teleop path changed in this round.
- **No concurrency or locking test.** The index is append-only with append+fsync, but two writers appending
  concurrently are untested; no lock is claimed.
- **Corrupt/foreign-schema lines are skipped, not refused, and are ungated.** Both `lookup()` and `conflicts()`
  skip lines they cannot parse; the gate deliberately does not assert either way (state that as a policy gap, not
  as verified behaviour).
- **Nothing was exercised against a live publish directory.** All gates run in `tmp_path`; the round's verdict is
  CPU-side (tool modules + tests), so per the roadmap's substrate-witness rule it needs **no** substrate witness —
  and none was taken. `geos_surface_meta` / `geos_read_surface` were not read this round.
- **The pure core was not re-derived.** `retention_plan`, `parse_record`, `canonical_record_line`, `entry_line`,
  `index_digest`, `line_sha_for` and `registry_key` were treated as dependencies; the harness's discriminating
  pure-core legs were re-run, not rewritten.
- **No roadmap done-state is claimed here.** SPINE-R1 is a lane-supply item from the ruling, not a roadmap row;
  `systems/GLYPH_SELF_HOSTING_ROADMAP.md` is unchanged by this round.

## 5. Next

- The `WriteRegistry`/`ArchiveStore` bodies are exhausted — the round's six enumerated steps plus the seventh are
  all landed, so **no further SPINE-R1 step is eligible**.
- The remaining authorized lane supply is the OSS lane (`GL6-BUILD`, `GL7-BUILD` loop-side done, publication
  fenced to Jericho) and **OS-SKEL-R2** (`.builder_queue/brief_osskel_r2_phase3.md`, seven steps, none started).
- The registry → `publish()` wire-in remains a named, unauthored follow-up (design question: who calls retention,
  and with which policy — Jericho's call, not the builder's).
