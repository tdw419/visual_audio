# BRIEF — SPINE-R1 step 6/6: `WriteRegistry.conflicts()` (last stub of the round)

**Skeleton (read FIRST — it is the spec, interfaces LOCKED):** `systems/GLYPH_SPINE_SKELETON.md` @ `95ee58f`
**Source authority:** `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item (3), round brief `.builder_queue/brief_spine_r1_phase3.md`
**Round:** SPINE-R1 (archive-retention + write-registry skeleton). Steps 1–5 are landed at `b3090a4`. This is step 6 — the last one.

## Deliverable (this step ONLY)

Populate `WriteRegistry.conflicts()` in `tools/geos_registry.py` (currently `return {}` at `tools/geos_registry.py:233-235`) and add its gate module `tests/test_spine_r1_conflicts.py`.

**Gate clause (verbatim from the round brief):** *two distinct records sharing `(origin_id, write_id)` → reported with both `line_sha` values.*

### Semantics already fixed by the skeleton — quote, do not re-derive

- `systems/GLYPH_SPINE_SKELETON.md:96` — `WriteRegistry.conflicts()` → **"keys mapping to >1 distinct `line_sha`"**.
- `register()`'s own docstring (`tools/geos_registry.py:188-190`) — *"This is deliberately stricter than conflicts()'s rule (>1 distinct line_sha)"*.
- Therefore `conflicts()` **must be able to observe the state `register()` refuses to create**. `self.entries` alone can never hold a duplicate key, so a `self.entries`-only implementation is **vacuous by construction**. `conflicts()` MUST read the persisted append-only index at `self.index_path` (each non-blank line is one entry JSON, the shape `entry_line()` writes) and group those lines by `(origin_id, write_id)`.
- Same key + **one** distinct `line_sha` is **not** a conflict (byte-identical history is not a collision). Same key + 2+ distinct `line_sha` is.
- Return shape: `Dict[Tuple[str, int], List[str]]` — key `(origin_id, write_id)`, value = the distinct `line_sha` strings, **sorted and de-duplicated**.
- Absent index file → `{}` (a miss is not an error; do not create the file).
- Read-only: `conflicts()` must not write, not create directories, and not mutate `self.entries`.
- Stdlib only (`geos_spine_verify.py` AST-scans for third-party imports).

## Gate — exact command and legs

```
/usr/bin/python3 -m pytest tests/test_spine_r1_conflicts.py -q
```

Every leg must be able to fail on its own. Compute expected shas from the module's own helpers (`entry_line` + `hashlib.sha256`, or `line_sha_for`) — **never hardcode a sha**.

| Leg | Assertion |
|---|---|
| **L1 conflict found** | Write an index file directly (bypassing `register()`, which is the point): two JSONL lines built from two `RegistryEntry`s that share `(origin_id, write_id)` and differ in at least one of `writer` / `image_path` / `written_at` (so their stored `line_sha` differs). `conflicts()` returns **exactly** that key, mapped to a list whose set equals **both** distinct shas. |
| **L2 "distinct" discriminator** | Two lines with the same key **and the same** `line_sha` → **not** reported (`conflicts() == {}`). This is what makes the `>1 distinct` clause discriminating rather than a duplicate-counter. |
| **L3 no false positives** | A healthy index built through `register()` (≥3 distinct keys) → `conflicts() == {}`. |
| **L4 read-only** | sha256 of the whole temp tree (index + every file, before/after) is identical across a `conflicts()` call in both the L1 and L3 states; and an **absent** index file → `{}` with no file created and no exception. |
| **L5 shape + multiplicity** | One index holding two independent conflicting keys **plus** one healthy key → exactly the two conflicting keys are reported, each with its own 2 shas, the healthy key absent, keys are 2-tuples `(str, int)`. |

## Hard constraints

- **Additive only.** Touch only `tools/geos_registry.py` (the `conflicts()` body, plus a private read-only helper if you want one) and the new `tests/test_spine_r1_conflicts.py`. Do NOT touch `lookup()` (it is a known residual, out of scope here), `scan()`, `register()`, `tools/geos_emit.py`, `tools/geos_observation_server.py`, `tools/geos_witness.py`, `tools/geos_archive.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL, `systems/GLYPH_SPINE_SKELETON.md`, `systems/*ROADMAP*.md`, or `.builder_queue/**`.
- **No signature or dataclass-field changes.** If one looks wrong, STOP and report — that is a skeleton-sign-off change, not a builder call.
- **Do not weaken the pure core** or the harness. `python3 tools/geos_spine_verify.py` must still print `SKELETON VERIFY: PASS`.
- `tests/` is covered by a `.gitignore` rule (`test_*.py`); **create the file anyway** — the orchestrator force-adds it. Do not edit `.gitignore`.
- **Do NOT commit. Do NOT run `git add`/`git commit`/`git stash`/`git checkout`.** The orchestrator verifies and commits.

## Evidence discipline (the orchestrator re-runs everything; your report is a claim, not evidence)

1. **RED first:** run the gate with the module absent, save stdout+stderr to `output/spine_r1_step6_red.txt`, record `GATE_EXIT=<n>` at the end.
2. Implement, then **GREEN:** same command + `tee`/redirect to `output/spine_r1_step6_green.txt`, ending with `GATE_EXIT=0`.
3. **Round gates together:** `/usr/bin/python3 -m pytest tests/test_spine_r1_plan.py tests/test_spine_r1_compact.py tests/test_spine_r1_refuse.py tests/test_spine_r1_register.py tests/test_spine_r1_scan.py tests/test_spine_r1_conflicts.py -q` → `output/spine_r1_step6_all_gates.txt`, exit 0.
4. **Structural harness:** `/usr/bin/python3 tools/geos_spine_verify.py` → still `SKELETON VERIFY: PASS` → `output/spine_r1_step6_spine_verify.txt`.
5. Do NOT run the full arc regression (the orchestrator runs it once, separately).

Report back: files changed (paths), the literal tail of the RED and GREEN runs, the harness line, and anything you did **not** verify.
