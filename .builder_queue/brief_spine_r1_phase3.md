# BRIEF — SPINE-R1 (Phase 3): populate the archive-retention + write-registry skeleton

**Skeleton (read FIRST — it is the spec):** `systems/GLYPH_SPINE_SKELETON.md` @ `95ee58f`
**Modules to populate:** `tools/geos_archive.py`, `tools/geos_registry.py` (interfaces are LOCKED — do not change signatures)
**Structural gate (must stay green throughout):** `python3 tools/geos_spine_verify.py` → exit 0
**Source authority:** `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item (3)

## Why this exists

The builder loop is out of supply, not out of capability: the roadmap has **0 open rows** and the loop
correctly refuses to invent scope. The two spine items named in the ruling were unauthored because they are
structural questions. The architecture is now locked (`95ee58f`); this brief turns it into mechanical work.

## Deliverable — SIX steps, each its own gate, in this order

Do them **one per run**. Do not bundle. Each step = implement the stub + a dedicated gate module.

| Step | Populate | New gate file | Gate clause (concrete) |
|---|---|---|---|
| 1 | `ArchiveStore.plan()` (read-only scan) | `tests/test_spine_r1_plan.py` | temp dir with N `(image, sidecar)` pairs → N records; a sidecar-less image is skipped, not crashed on; plan does not mutate the dir |
| 2 | `ArchiveStore.compact(plan)` | `tests/test_spine_r1_compact.py` | plan+compact on a temp dir deletes exactly the planned files, nothing else; returns `{"deleted":n,"bytes":b}` |
| 3 | `compact()` cross-reference refusal | `tests/test_spine_r1_refuse.py` | an evicted record referenced by a non-evicted sibling in the registry → loud refusal, **no deletion** |
| 4 | `WriteRegistry.register` + persistence | `tests/test_spine_r1_register.py` | append-only JSONL; duplicate key → refusal; index digest stable across re-open |
| 5 | `WriteRegistry.scan(root)` | `tests/test_spine_r1_scan.py` | sha256 tree snapshot before/after scan is identical (read-only proof) |
| 6 | `WriteRegistry.conflicts()` | `tests/test_spine_r1_conflicts.py` | two distinct records sharing `(origin_id, write_id)` → reported with both `line_sha` values |

## Hard constraints

- **Interfaces are frozen.** No signature or dataclass-field changes; if one seems wrong, STOP and report —
  that is a skeleton-sign-off change, not a builder call.
- **Additive only.** Do NOT touch `tools/geos_emit.py`, `tools/geos_observation_server.py`,
  `tools/geos_witness.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL,
  `systems/GLYPH_SPINE_SKELETON.md`, or `.builder_queue/**`.
- **Read-only means read-only.** `plan()` and `scan()` must not write. Prove it (steps 1 and 5 clauses).
- **Stdlib only** in both modules — `geos_spine_verify.py` AST-scans for this.
- **Do not weaken the pure core** to make I/O easier. `retention_plan` is already correct and gated; treat it
  as a dependency.
- Wire-in (`geos_emit.publish()` → registry, operator-invocable retention) is **NOT** in this round. Separate
  brief, separate gate.

## Receipt discipline (unchanged from the loop's standing rules)

- RED first: run the new gate before implementing, save the red output.
- GREEN after: save the green output; paste the literal tail in the report.
- Re-run `python3 tools/geos_spine_verify.py` after each step — it must stay PASS.
- Arc regression: `/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py` exit 0.
- One commit per step, message citing the gate's literal last line.
- Nothing claimed that was not run this tick.

## Definition of done for SPINE-R1

Steps 1–6 each with RED→GREEN evidence, `geos_spine_verify.py` PASS, arc regression green, and a receipt
written to `systems/RECEIPT_SPINE_R1.md` naming what is **not** claimed.
