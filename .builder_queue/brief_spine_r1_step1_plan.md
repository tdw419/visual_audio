# BRIEF — SPINE-R1 Phase 3 · STEP 1 of 6: populate `ArchiveStore.plan()` (read-only scan)

**Parent plan (read it first):** `.builder_queue/brief_spine_r1_phase3.md` — six steps, ONE per run. You implement **step 1 only**.
**Spec of record:** `systems/GLYPH_SPINE_SKELETON.md` §4 (interface contracts, LOCKED) and §7 item 1 (this step).
**Files in scope (only these two):**
- EDIT `tools/geos_archive.py` — implement `ArchiveStore.plan()`; leave `compact()` a stub (step 2 owns it).
- NEW  `tests/test_spine_r1_plan.py` — the gate.

Nothing else. Interfaces are FROZEN: no signature change, no dataclass field change, no rename.

## What `plan()` must do

Current body is a stub returning `[]`. Make it: scan `archive_dir` for `(image, sidecar)` pairs, parse each sidecar with the already-implemented `parse_record()`, and return `retention_plan(records, policy)`. `retention_plan` is already correct and gated — treat it as a dependency, do not touch it.

Pairing rule — **decided by the orchestrator; use exactly this, do not invent another**:
1. Recursive walk of `archive_dir` in deterministic (sorted) order.
2. A candidate image is any file whose suffix is `.npy` or `.png`.
3. An image pairs with a sidecar **in its own directory**: `surface.meta.json` if present, else `<image-stem>.meta.json`. This mirrors `tools/geos_observation_server.py:88-91` — cite that precedent in a comment.
4. One sidecar is claimed by at most one image: within a directory, images are taken in sorted order and each sidecar can be claimed once. An image with no available sidecar is **skipped, never an exception**.
5. A sidecar that exists but fails `parse_record` (e.g. no `write_id`) is **skipped** — such a write never entered the archive (`parse_record`'s raise stays the writer-path gate). Say this explicitly in the docstring; it is a deliberate rule, not an oversight.
6. `archive_dir` that does not exist → return `[]`. Do **not** create the directory, do **not** raise.
7. Read-only means read-only: no writes, no `mkdir`, no `utime`, no renames, no `tempfile` in the archive dir. Open files read-only.
8. Also store the returned list in `self.plan_cache` (that frozen field exists for exactly this; today it is dead).
9. Stdlib only (`geos_spine_verify.py` AST-scans for third-party imports).

## Gate — `tests/test_spine_r1_plan.py`

Write it **before** implementing, so you can capture a RED run against the stub. Build fixtures in `tmp_path` (do not touch the real archive dir, `/tmp/geos_observation`, or any repo file). Legs:

- **L1 — N pairs → N records.** 3 dirs, each holding `kernel_memory.npy` + `surface.meta.json` with `write_id` 1/2/3, `writer` "stage-a", distinct `bytes_len`. `plan(RetentionPolicy(keep_total=0))` returns exactly 3 evictions, every reason `REASON_OVER_COUNT`, ordered by `(write_id, image_path)`.
- **L2 — records are PARSED, not fabricated.** Tag one write (`tags: ["scratch"]`); `RetentionPolicy(exclude_tags=("scratch",))` returns exactly 1 eviction, that `write_id`, reason `REASON_POLICY_EXCLUDED`. Also assert a parsed `bytes_len` matches the sidecar value (proves the field survives the scan).
- **L3a — sidecar-less image is skipped, not fatal.** Add `orphan/only.npy` (no sidecar): the L1 call still returns exactly 3 evictions and raises nothing.
- **L3b — unattributable sidecar is skipped.** Add `bad/x.npy` + `bad/surface.meta.json` with no `write_id`: still exactly 3 evictions, no exception.
- **L4 — read-only proof.** Snapshot the whole tree (relative names + sha256 + size) before and after two `plan()` calls; snapshots must be byte-identical and no new path may appear.
- **L5 — determinism.** Two calls on the same tree give identical `[(write_id, reason, image_path)]` lists.
- **L6 — nonexistent dir.** `plan()` on a path that does not exist → `[]`, and `os.path.exists(path)` is still `False` afterwards.
- **L7 — `plan_cache` is populated** with the same list the call returned.

Gate command (use `/usr/bin/python3`, it is the canonical interpreter here):
`/usr/bin/python3 -m pytest tests/test_spine_r1_plan.py -q`

## Evidence you must produce (the orchestrator re-runs everything, so be literal)

1. **RED first:** with the gate written and `plan()` still a stub, run the gate → save the output to `output/spine_r1_step1_red.txt` (expect FAILs, not a collection error).
2. Implement, then run the gate → `output/spine_r1_step1_green.txt` (all passed, exit 0).
3. Re-run the structural harness: `/usr/bin/python3 tools/geos_spine_verify.py` → must still print `SKELETON VERIFY: PASS`, save to `output/spine_r1_step1_spine_verify.txt`. **If it fails, do NOT edit `tools/geos_spine_verify.py`** (forbidden) — report the exact failing leg instead.
4. Do NOT run `git commit` / `push` / `checkout` / `stash` / `reset`. Do NOT run the full arc suite (the orchestrator runs that). Do NOT touch `compact()`, `tools/geos_registry.py`, `tools/geos_emit.py`, `tools/geos_observation_server.py`, `systems/GLYPH_SPINE_SKELETON.md`, or `.builder_queue/**`.
5. End with a DIFF SUMMARY: files changed, exact commands run, literal last lines of each output, and anything you could not verify.
