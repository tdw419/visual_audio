# BRIEF — SPINE-R1 step 7 (gap found while landing step 6): `WriteRegistry.lookup()`

**Skeleton (read FIRST — it is the spec, interfaces LOCKED):** `systems/GLYPH_SPINE_SKELETON.md` @ `95ee58f`
**Source authority:** `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item (3) ("write new spine items … global"), round brief `.builder_queue/brief_spine_r1_phase3.md`.
**Provenance of this step:** the round brief enumerated six steps and omitted `lookup()`, but the skeleton's boundary map (`systems/GLYPH_SPINE_SKELETON.md:59`) and stub table list **`WriteRegistry.register / lookup / conflicts / scan` [STUB]** as the four bodies Phase 3 must populate. Steps 1–6 landed (`6d07f7f`); step 6's commit recorded `lookup()` as a residual: it still returns `[]` unconditionally, no gate in `tests/` exercises it, and the structural harness only asserts it returns a list (`tools/geos_spine_verify.py:102`). A detectable failure must not be silent — so it is gated here rather than declared done.

## Deliverable (this step ONLY)

Populate `WriteRegistry.lookup()` in `tools/geos_registry.py` (currently `return []` at `tools/geos_registry.py:229-231`) and add its gate module `tests/test_spine_r1_lookup.py`.

**Contract (verbatim from the skeleton):** *"read-only scan; `[]` on miss; never fabricates an entry"* — `tools/geos_registry.py:167-168`.

### Semantics already fixed — quote, do not re-derive

- The registry is an **append-only JSONL index** at `self.index_path`; each line is exactly the shape `entry_line()` writes (`origin_id, write_id, writer, image_path, line_sha, written_at`), see `register()` (`tools/geos_registry.py:184-227`).
- `lookup(origin_id, write_id) -> List[RegistryEntry]` **must read the persisted index**, not only `self.entries`: a fresh `WriteRegistry(index_path=…)` with empty in-memory entries must still find writes registered by another instance/process. (Same reasoning that made step 6's `conflicts()` a disk read.)
- Miss (key absent, empty index, **absent index file**) → `[]`, no exception, **no file/directory creation**.
- Never fabricates: a returned entry's key must equal `(origin_id, write_id)` and its fields must be the values that were persisted — never synthesised defaults.
- Read-only: no writes, no mkdir, `self.entries` untouched.
- Stdlib only (`geos_spine_verify.py` AST-scans for third-party imports). Build the return value from `RegistryEntry` — do not invent a new type or change the dataclass.

## Gate — exact command and legs

```
/usr/bin/python3 -m pytest tests/test_spine_r1_lookup.py -q
```

Every leg must be able to fail on its own. Compute expectations from the module's own helpers (`entry_line`, `registry_key`, `line_sha_for`) — never hardcode a sha or a line index.

| Leg | Assertion |
|---|---|
| **L1 hit round-trips** | `register()` three records with distinct keys, then `lookup(origin, write_id)` for one of them returns exactly one `RegistryEntry` whose `key`, `writer`, `image_path`, `line_sha`, `written_at` equal the values returned by that `register()` call. No extra entries. |
| **L2 miss is `[]`** | An unregistered key on a populated index → `[]` (a list, not `None`, not an exception). |
| **L3 absent index** | A registry pointed at a path that does not exist → `[]` for any key; afterwards the path still does not exist (no file, no parent directory created). |
| **L4 disk-truth (kills a `self.entries`-only implementation)** | Register a key with instance A, then construct a **fresh** `WriteRegistry(index_path=<same file>)` with default (empty) entries and `lookup()` through *that* instance → the entry is found. A `self.entries`-only implementation fails this leg. |
| **L5 read-only** | sha256 snapshot of the whole temp tree (every file + the sorted directory list) is identical before/after a `lookup()` in both the L1 and L2 states, and `self.entries` is unchanged (same length and same key order) across the call. |

## Hard constraints

- **Additive only.** Touch only `tools/geos_registry.py` (`lookup()`'s body plus a private read-only helper if you want one) and the new `tests/test_spine_r1_lookup.py`. Do NOT touch `register()`, `conflicts()`, `scan()`, the pure core, dataclasses, `__all__`, `__main__`, `tools/geos_archive.py`, `tools/geos_emit.py`, `tools/geos_observation_server.py`, `tools/geos_witness.py`, `tools/geos_spine_verify.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL, `systems/**`, `.builder_queue/**`.
- **No signature or dataclass-field changes.** If one looks wrong, STOP and report.
- **Malformed/foreign-schema lines are out of scope of this step's gate** — do not assert on them either way; `conflicts()` skipped them and the two bodies may differ.
- `tests/` is covered by a `.gitignore` rule (`test_*.py`); **create the file anyway** — the orchestrator force-adds it. Never edit `.gitignore`.
- **Do NOT commit. Do NOT run `git add` / `git commit` / `git stash` / `git checkout`.**

## Evidence discipline

1. **RED first:** run the gate with the module absent → `output/spine_r1_step7_red.txt`, ending with `GATE_EXIT=<n>` (expect 4).
2. Implement, then **GREEN:** same command → `output/spine_r1_step7_green.txt`, ending with `GATE_EXIT=0`.
3. **Round gates together:** `/usr/bin/python3 -m pytest tests/test_spine_r1_plan.py tests/test_spine_r1_compact.py tests/test_spine_r1_refuse.py tests/test_spine_r1_register.py tests/test_spine_r1_scan.py tests/test_spine_r1_conflicts.py tests/test_spine_r1_lookup.py -q` → `output/spine_r1_step7_all_gates.txt`, exit 0.
4. **Structural harness:** `/usr/bin/python3 tools/geos_spine_verify.py` → still `SKELETON VERIFY: PASS` → `output/spine_r1_step7_spine_verify.txt`.
5. Do NOT run the full arc regression (the orchestrator runs it once, separately).

Report back: files changed (paths), the literal tail of RED and GREEN, the harness line, and anything you did **not** verify.
