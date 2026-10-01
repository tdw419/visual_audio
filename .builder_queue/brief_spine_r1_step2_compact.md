# BRIEF — SPINE-R1 Phase 3 · STEP 2 of 6: populate `ArchiveStore.compact(plan)`

**Row id:** SPINE-R1 step 2 of 6 (authority: `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item 3;
parent plan `.builder_queue/brief_spine_r1_phase3.md`; spec of record `systems/GLYPH_SPINE_SKELETON.md` §7 item 2 /
§4 interface contracts, **LOCKED**).

**Step 1 is landed** (commit `531bfaa`, `tests/test_spine_r1_plan.py` 9/9). You implement **step 2 only**.
Prior partial work is NOT a precedent to copy — read the current file state first.

**Files in scope (only these two):**
- EDIT `tools/geos_archive.py` — implement `ArchiveStore.compact()`'s body (and add stdlib imports at the top only if
  strictly needed). Do **not** touch `plan()`, `retention_plan()`, `parse_record()`, `canonical_record_line()`, any
  dataclass or any signature.
- NEW  `tests/test_spine_r1_compact.py` — the gate.

Nothing else. No signature change, no dataclass field change, no rename, no new module.

## Semantics — decided by the orchestrator, implement EXACTLY this

`compact(self, plan: Sequence[Eviction]) -> Dict[str, int]`

1. **Validate the WHOLE plan before deleting anything** (containment — nothing faults for us, so the tool must be
   its own fence). For every eviction, both `record.image_path` and `record.sidecar_path` must resolve **inside**
   `self.archive_dir`: compare `os.path.realpath(...)` against `os.path.realpath(self.archive_dir)` using
   `os.path.commonpath`. If any path escapes → raise `ValueError` whose message **names the offending path** and the
   archive dir (e.g. `refusing to compact outside archive_dir: <path> not under <archive_dir>`), and delete **nothing**
   (validation is a full pass over the plan *before* the first `os.remove`).
2. **Delete, in the order the plan gives them, both files of each eviction**: `record.image_path`, then
   `record.sidecar_path`. That is the complete delete set — the plan is the only authority.
   No `glob`, no `os.walk`, no directory removal, no deleting by pattern, no touching any other path.
3. **A path that does not exist is skipped, not fatal** (an already-applied plan, or a partially-present pair).
   This makes `compact` idempotent.
4. **Return `{"deleted": <n>, "bytes": <b>}` where:**
   - `deleted` = the number of **files actually unlinked** (an eviction with image+sidecar present contributes 2;
     a skipped missing file contributes 0);
   - `bytes` = the **measured on-disk size** (`os.path.getsize`, read *before* unlinking) summed over exactly those
     unlinked files. **Not** the sidecar-declared `bytes_len` — say why in a comment: `bytes_len` is a policy input,
     while this is the disk actually reclaimed, and a retention tool must not report a number it did not measure.
5. **`plan_cache` is left untouched** by `compact` (it records the decision that was applied, not the disk state).
6. **Stdlib only** (`geos_spine_verify.py` AST-scans for third-party imports).
7. **No registry cross-reference check in this step.** `self.registry` stays unused here — that refusal is step 3
   (`tests/test_spine_r1_refuse.py`) and adding a half version now would leave dead, ungated code. Do not touch
   `tools/geos_registry.py`.
8. Docstring: state the delete set, the accounting units, idempotence, the containment refusal, and the explicit
   "step 3 owns the registry refusal" boundary.

## Gate — `tests/test_spine_r1_compact.py`

Write it **before** implementing so the RED run lands on the stub (stub returns `{"deleted": 0, "bytes": 0}`).
All fixtures in `tmp_path` — never touch the real archive dir, `/tmp/geos_observation`, or any repo file.
Imports from `tools.geos_archive`: `ArchiveRecord`, `Eviction`, `RetentionPolicy`, `ArchiveStore`, `REASON_*`.
Helper needed: a tree snapshot (relative path → (sha256, size)) used before/after.

- **L1 — exact deletion + exact accounting.** 3 dirs (`w1/`, `w2/`, `w3/`), each with `kernel_memory.npy` +
  `surface.meta.json`, `write_id` 1/2/3, writer `stage-a`, distinct `bytes_len`. `plan(keep_total=1)` → 2 evictions.
  Record sizes and the snapshot BEFORE compact; call `compact(plan)`:
  `res["deleted"] == 4` (2 records × image+sidecar — assert the file-count unit explicitly, do not let it read as a
  record count) and `res["bytes"] == sum(os.path.getsize(p) for p in the 4 paths)` measured pre-delete.
  The kept pair (write_id 3) still exists with unchanged sha256; its 2 files were not counted in `bytes`.
- **L2 — nothing else is touched.** Add a non-planned pair (`extra/surface.meta.json` + `extra/kernel_memory.npy`,
  `write_id` 99 — not evicted by `keep_total=1` + `keep_per_writer=1`? **do not rely on that**: instead plan with
  `RetentionPolicy(keep_total=1)` and assert `extra`'s two files survive with identical sha256), plus unrelated
  bystanders that are not archive records: `notes.txt`, `orphan/only.npy` (no sidecar), `bad/x.npy` +
  `bad/surface.meta.json` with **no `write_id`**. Full-tree snapshot after compact must equal the before-snapshot
  **minus exactly the 4 deleted paths** — assert set difference equality both ways (no extra deletions, nothing
  missed).
- **L3 — idempotence.** Call `compact(plan)` a second time with the same plan → returns `{"deleted": 0, "bytes": 0}`,
  raises nothing, tree snapshot unchanged between the two calls.
- **L4 — containment refusal.** Build a plan by hand containing one record whose `image_path` is a real file
  **outside** `archive_dir` (e.g. `tmp_path/"outside.npy"`, plus a valid in-tree record) and one whose sidecar escapes.
  `pytest.raises(ValueError)`; assert the message contains the offending path; assert the **whole tree** (including
  the outside file) is byte-identical to the pre-call snapshot — i.e. the in-tree victim was NOT deleted either.
  Assert the refusal happens before any deletion by giving the plan two records: first an out-of-tree one, second a
  fully valid in-tree one → still zero deletions.
- **L5 — plan → compact → re-plan.** 3 pairs, `keep_total=1`; after `compact(plan)`, a fresh
  `store.plan(RetentionPolicy(keep_total=1))` returns `[]` (the evicted pairs are gone, so no eviction remains).
- **L6 — empty plan / nonexistent dir.** `compact([]) == {"deleted": 0, "bytes": 0}` and no error; an
  `ArchiveStore` pointed at a path that does not exist gives `plan(...) == []` then `compact([])` → zeros, and the
  path still does not exist afterwards.
- **L7 — `deleted` counts files, not records (unit lock).** Fixture where the sidecar is already missing for one
  evicted record (delete the sidecar by hand before compact): `deleted == 3` for 2 evictions, and `bytes` equals the
  3 remaining files' pre-delete sizes. This leg exists so a future refactor cannot silently flip the unit.

Gate command (canonical interpreter):
`/usr/bin/python3 -m pytest tests/test_spine_r1_compact.py -q`

## Hard constraints

- Interfaces frozen; additive only. Do NOT touch `tools/geos_emit.py`, `tools/geos_observation_server.py`,
  `tools/geos_witness.py`, `tools/geos_registry.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`,
  `glyph_dispatch/**`, any WGSL, `systems/GLYPH_SPINE_SKELETON.md`, or `.builder_queue/**`.
- Never weaken `retention_plan` to make I/O easier; treat it as a dependency.
- Destructive-op discipline: `compact` is the repo's only planned-delete path. It may `os.remove` **only** paths
  named in the plan and validated as in-archive. No `rmtree`, no `unlink` of directories.

## Evidence you must produce (the orchestrator re-runs everything — be literal)

1. **RED first:** gate written, `compact()` still the stub → run the gate, save to
   `output/spine_r1_step2_red.txt` (expect FAILs, not a collection error).
2. Implement, then run the gate → `output/spine_r1_step2_green.txt` (all passed, exit 0).
3. `/usr/bin/python3 tools/geos_spine_verify.py` → must still print `SKELETON VERIFY: PASS`, save to
   `output/spine_r1_step2_spine_verify.txt`. **If it fails, do NOT edit `tools/geos_spine_verify.py`** (forbidden) —
   report the exact failing leg.
4. Do NOT run `git commit`/`push`/`checkout`/`stash`/`reset`. Do NOT run the arc suite (the orchestrator runs it).
   Do NOT run the step-1 gate as a substitute for this one.
5. End with a DIFF SUMMARY: files changed, exact commands run, literal last lines of each output, and anything you
   could not verify.
