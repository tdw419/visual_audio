# BRIEF — SPINE-R1 Phase 3 · STEP 3 of 6: `compact()` registry cross-reference refusal

**Row id:** SPINE-R1 step 3 of 6 (authority: `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item 3;
parent plan `.builder_queue/brief_spine_r1_phase3.md`; spec of record `systems/GLYPH_SPINE_SKELETON.md` §7 item 3 /
§4 interface contracts, **LOCKED**).

**Steps 1 and 2 are landed** (commits `531bfaa`, `2e10286`; gates `tests/test_spine_r1_plan.py` 9/9,
`tests/test_spine_r1_compact.py` 7/7). You implement **step 3 only**. Prior partial work is NOT a precedent to
copy — read the current file state first (`tools/geos_archive.py` at HEAD is the authority).

**Files in scope (only these two):**
- EDIT `tools/geos_archive.py` — add ONE private helper `_registry_refusal(self, plan) -> Optional[str]` and call it
  from `compact()`'s pre-delete validation pass; update the `compact()` docstring's boundary note only.
  Do **not** touch `plan()`, `retention_plan()`, `parse_record()`, `canonical_record_line()`, any dataclass,
  any public signature, the step-2 containment pass, or the delete loop / accounting.
- NEW  `tests/test_spine_r1_refuse.py` — the gate.

Nothing else. **Do NOT edit `tools/geos_registry.py`** (out of scope; its `register/lookup/conflicts/scan` are
step-4/5/6 stubs and stay stubs).

## The rule (decided by the orchestrator — implement EXACTLY this)

`WriteRegistry` is the global cross-directory index. Its key is the pair `(origin_id, write_id)` (registry
invariant I2/I5). Two entries sharing a key but carrying **different `line_sha`** are the collision case the
registry exists to detect (`geos_registry.py` docstring, `conflicts()`), and the case retention must refuse to
evict through: deleting one claimant's files destroys the evidence that resolves the collision.

**Refusal rule:** `compact(plan)` raises `ValueError` (deleting NOTHING) when the injected registry holds a
conflicted key that is only *partially* evicted — i.e. all three hold for some key `K = (origin_id, write_id)`:

1. the registry has **≥2 entries** with key `K`;
2. those entries carry **>1 distinct `line_sha`** (a genuine conflict, not a duplicate registration);
3. **at least one** of them references an artifact the plan evicts, AND **at least one** of them does
   (the non-evicted sibling).

Linkage is by `image_path`: an entry is *evicted* iff `os.path.realpath(entry.image_path)` is in the set of
`os.path.realpath(p)` for every `p` in `(eviction.record.image_path, eviction.record.sidecar_path)` across the
whole plan. A registry entry with `image_path is None` names no artifact — it can only ever be a sibling, never
count as evicted.

Message template (build it with an f-string; the gate asserts substrings of it):

```
refusing to compact: registry key {key!r} is partially evicted — non-evicted sibling {sibling_image_path} conflicts with evicted record {evicted_image_path} (distinct line_sha)
```

Choose `evicted_image_path` / `sibling_image_path` deterministically: from the entries with key `K`, sort by
`image_path`, take the first evicted one and the first non-evicted one. The message MUST contain the literal
substring `refusing to compact`, `repr(key)` i.e. `{key!r}`, and both chosen paths.

Implementation constraints:

- **Read the registry's public `entries` list only** (`getattr(self.registry, "entries", None) or []`).
  Do **NOT** call `self.registry.conflicts()` or `.lookup()` — both are unimplemented stubs, so calling them
  would make the refusal vacuous and ungated. Do NOT touch the registry object in any other way (read-only).
- `self.registry is None` → no check (step-2 behaviour exactly). Registry object with `entries` empty/None → no
  check.
- **Ordering:** the step-2 containment pass runs first and is unchanged; the registry refusal runs immediately
  after it, still **before the first `os.remove`** (a full pre-pass over the plan). Nothing may be deleted when
  the refusal fires, including evictions that were themselves clean.
- Raise `ValueError` only (no new exception class, no new module-level symbol, no public API change).
- Stdlib only (the AST scan in `geos_spine_verify.py` must stay green).
- Docstring: keep the existing delete-set / accounting / idempotence / containment text verbatim, and replace the
  boundary note's "Step 3 owns the registry refusal …" paragraph with a statement that step 3 implements it —
  naming the three-part rule above and that the link is `realpath(entry.image_path)`.

## Gate — `tests/test_spine_r1_refuse.py`

Write it **before** implementing so the RED run lands on the no-refusal tree (all refusal legs fail; the negative
legs may pass immediately — that is expected and fine). All fixtures in `tmp_path`; never touch the real archive
dir, `/tmp/geos_observation`, or any repo file. Imports:

- from `tools.geos_archive`: `ArchiveRecord`, `Eviction`, `RetentionPolicy`, `ArchiveStore`
- from `tools.geos_registry`: `WriteRegistry`, `RegistryEntry`, `line_sha_for`

Seed the registry by constructing `WriteRegistry(index_path=str(tmp_path / "index.jsonl"))` and appending
`RegistryEntry(...)` values to `reg.entries` (or pass `entries=[...]`). Do **not** use `register()` — it is a
step-4 stub that does not append. Build every `line_sha` with the real serializer: `line_sha_for(record)` over a
distinct `ArchiveRecord` per claimant (no hand-written hash strings), and assert the leg's precondition
`len({e.line_sha for e in rows}) > 1` so a fixture that is not actually a conflict cannot pass silently.

Standard fixtures per leg: a helper `pair(dir, write_id, writer, bytes)` writing `<dir>/kernel_memory.npy` +
`<dir>/surface.meta.json` (sidecar carrying `write_id`, `writer`, `bytes_len`, `written_at`), and the step-2 tree
snapshot helper (relative path → (sha256, size)).

- **L1 — positive refusal, cross-directory conflict.** Archive root `A=tmp/arch` with pairs `A/w1/` (write_id 1)
  and `A/w2/` (write_id 2), both writer `stage-a`; `plan = store.plan(RetentionPolicy(keep_total=1))` → 1 eviction
  (write_id 1). Second directory `B=tmp/other` holding a real pair (`B/kernel_memory.npy` + sidecar, write_id 1 of
  its own emitter). Registry: two entries with key `("origin-x", 1)` — one with `image_path=A/w1/kernel_memory.npy`
  and `line_sha` from the evicted record, one with `image_path=B/kernel_memory.npy` and a different `line_sha`
  (different image_path/content ⇒ different canonical line). `pytest.raises(ValueError)`; assert the message
  contains `"refusing to compact"`, `repr(("origin-x", 1))`, the evicted path and the sibling path; then assert the
  **whole tree** of `tmp_path` is byte-identical to the pre-call snapshot (both A and B untouched).
- **L2 — discriminating negatives (must NOT refuse).**
  (a) same key `("origin-x", 1)`, **identical** `line_sha` on both entries (duplicate registration) → `compact(plan)`
  proceeds and returns `{"deleted": 2, "bytes": <pre-delete sizes of the 2 evicted files>}`;
  (b) two registry entries with **different** keys → proceeds, same result;
  (c) single entry, key appears once → proceeds.
  Each sub-leg uses a fresh copy of the fixture tree (or fresh dirs) so the legs are independent.
- **L3 — no registry / empty registry.** `ArchiveStore(archive_dir=A, registry=None)` and
  `ArchiveStore(archive_dir=A, registry=WriteRegistry(index_path=...))` (entries empty) → both return the step-2
  numbers `{"deleted": 2, "bytes": b}`; result must be identical for the two stores (assert equality of the dicts
  and equality against a `rule-free` reference run on a third identical tree).
- **L4 — refusal happens before ANY deletion.** Plan with **two** evictions where the **second** is the conflicting
  one (the first is fully clean): `pytest.raises(ValueError)` and the first eviction's two files still exist with
  unchanged sha256; full-tree snapshot equals the pre-call snapshot. This proves the pre-pass is complete before
  the delete loop, not an incremental check.
- **L5 — partial-eviction requirement is real.** Conflicted key `K` where **both** claimants are in the plan
  (both evicted, distinct `line_sha`) → **no refusal**, `compact` proceeds (the conflict's files are all being
  removed together; nothing survives to be inconsistent). Assert the returned counts.
- **L6 — message is literal and complete.** On the L1 fixture, assert the caught exception's `str()` contains all
  four required pieces (substring `refusing to compact`, `repr(key)`, evicted image path, sibling image path) and
  that it is a `ValueError` — not a bare `Exception`, not an `OSError`.
- **L7 — the step-2 contract still holds through the new path.** Re-run the step-2 essentials with a registry
  attached and no conflict: 3 pairs, `keep_total=1` → 2 evictions → `deleted == 4` (file unit, not record unit),
  `bytes == sum(os.path.getsize(p) for p in the 4 paths)` measured pre-delete, bystanders intact, second
  `compact(plan)` → `{"deleted": 0, "bytes": 0}` (idempotence preserved).

Gate command (canonical interpreter):

`/usr/bin/python3 -m pytest tests/test_spine_r1_refuse.py -q`

## Hard constraints

- Interfaces frozen; additive only. Do NOT touch `tools/geos_emit.py`, `tools/geos_observation_server.py`,
  `tools/geos_witness.py`, `tools/geos_registry.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`,
  `glyph_dispatch/**`, any WGSL, `systems/GLYPH_SPINE_SKELETON.md`, `tools/geos_spine_verify.py`, or
  `.builder_queue/**`.
- Never weaken `retention_plan` or the step-2 containment validation to make this easier; treat both as
  dependencies. The step-2 gate must still pass unchanged.
- Destructive-op discipline unchanged: `compact` may `os.remove` **only** paths named in the plan and validated as
  in-archive. The refusal path deletes nothing.

## Evidence you must produce (the orchestrator re-runs everything — be literal)

1. **RED first:** gate written, no refusal implemented → run the gate, save to
   `output/spine_r1_step3_red.txt` (expect FAILs on the refusal legs, not a collection error).
2. Implement, then run the gate → `output/spine_r1_step3_green.txt` (all passed, exit 0).
3. `/usr/bin/python3 -m pytest tests/test_spine_r1_compact.py -q` (step 2 must stay green) →
   `output/spine_r1_step3_step2_regress.txt`.
4. `/usr/bin/python3 tools/geos_spine_verify.py` → must still print `SKELETON VERIFY: PASS`, save to
   `output/spine_r1_step3_spine_verify.txt`. **If it fails, do NOT edit `tools/geos_spine_verify.py`** (forbidden)
   — report the exact failing leg.
5. Do NOT run `git commit`/`push`/`checkout`/`stash`/`reset`. Do NOT run the arc suite (the orchestrator runs it).
   Do NOT run the step-1/step-2 gates as a substitute for this one.
6. End with a DIFF SUMMARY: files changed, exact commands run, literal last lines of each output, and anything you
   could not verify.
