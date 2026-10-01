# SKELETON SIGNED OFF — Glyph OS Spine, Round 1: Archive Retention + Write Registry

**Date:** 2026-09-12
**Lane:** self-hosting spine (supply for the builder loop)
**Status:** Phase 1 (structure) + Phase 2 (architectural lock) COMPLETE — Phase 3 (population) is builder work
**Pattern:** skeleton-driven development (`skeleton-driven-development` skill)
**Source authority:** `.builder_queue/RULING_lane_supply_20260912.md` § Reserved to Jericho item (3) —
"retention policy for per-write archives; global cross-directory write registry"

---

## 1. Why this skeleton exists

The builder loop is **not broken — it is out of supply**. Measured this session:

- Roadmap open rows: **0** (`GH-1..GH-26`, `BK-1..BK-14`, `ENG-1`, `DEFECT-17/18`, `OBS-1`, `GL-6/GL-7` all ✅)
- The loop's own footer: *"the ruling's two-item primary supply is exhausted … GL-8+ are fenced behind a
  stranger's friction report, and the three reserved product questions remain open"*
- The loop holds rather than authors work (correct behaviour: `GLYPH_BACKLOG.md` forbids inventing scope)

The two named-but-unauthored spine items in the ruling are the next real work. They were unauthored because
they are **structural questions**, not mechanical ports: what retention *means*, and how a write is identified
globally. That is the definition of a skeleton job — lock the architecture, then let the builder populate it
without re-deriving design.

## 2. The two problems, stated precisely

**P1 — retention.** `tools/geos_emit.py` publishes to one fixed filename (`IMAGE_NAME = "kernel_memory.npy"`,
`META_NAME = "surface.meta.json"`), so every publish overwrites the last. DEFECT-20 gave writes an identity
(`write_id`, `writer`) in the sidecar, but nothing *retains* the history that identity names, and nothing bounds
disk growth once per-write archives exist.

**P2 — global identity.** Write identity is recorded only *next to* the image it describes. There is no global
index, so: you cannot answer "which write produced this artifact?" from outside its directory; you cannot detect
`write_id` collisions across directories (independent emitters each count from their own start); and retention
cannot refuse to evict something another directory still references.

## 3. Boundary map

```
    tools/geos_emit.publish()                     tools/geos_observation_server
        |  writes image + sidecar                      |  reads a snapshot window
        |  sidecar carries write_id, writer             |  surfaces write_id / writer
        v                                               v
    +-------------------------------------------------------------+
    |  geos_archive.py         (retention contract)                |
    |                                                              |
    |    ArchiveRecord ──┐                                         |
    |    RetentionPolicy ┼──> retention_plan()  == PURE CORE       |
    |    Eviction     ──┘         |                                |
    |                             v                                |
    |    ArchiveStore.plan() / .compact()   [STUB — Phase 3 I/O]   |
    +-----------------------------|--------------------------------+
                                  |  refuse to evict a record that is
                                  |  still referenced elsewhere
                                  v
    +-------------------------------------------------------------+
    |  geos_registry.py        (global cross-directory index)      |
    |    WriteRegistry.register / lookup / conflicts / scan [STUB] |
    |    registry_key / entry_line / index_digest      == PURE     |
    +-------------------------------------------------------------+
```

**No file is modified in place.** Both modules are additive: they read emit metadata and index it. Nothing here
rewrites a committed image or sidecar (I4 / I1).

## 4. Interface contracts (LOCKED — changing these invalidates the skeleton sign-off)

### `geos_archive`

| Symbol | Kind | Contract |
|---|---|---|
| `ArchiveRecord` | frozen dataclass | `write_id:int, writer:str, image_path:str, sidecar_path:str, bytes_len:int=0, written_at:str="", tags:tuple=()` — frozen: a retention decision must not mutate its inputs |
| `RetentionPolicy` | frozen dataclass | `keep_per_writer:Optional[int]`, `keep_total:Optional[int]`, `max_bytes:int=0`, `exclude_tags:tuple=()` — every bound explicit, no implicit default |
| `Eviction` | frozen dataclass | `record`, `reason` — every condemnation names its rule |
| `retention_plan(records, policy) -> list[Eviction]` | **IMPLEMENTED, pure** | ordered passes: tag-exclusion → per-writer quota → global count → global bytes. Survivors chosen newest-first by `write_id`. Output sorted by `(write_id, image_path)`. Never raises on empty input |
| `parse_record(sidecar, image_path, sidecar_path) -> ArchiveRecord` | **IMPLEMENTED, pure** | a sidecar with no `write_id` **raises** — unattributable writes do not enter the archive |
| `canonical_record_line(record) -> str` | **IMPLEMENTED, pure** | sorted keys, compact separators, no trailing space — identical events must produce identical bytes |
| `ArchiveStore.plan(policy)` | **STUB** | read-only scan → records → plan |
| `ArchiveStore.compact(plan)` | **STUB** | apply the plan; refuse if a record is still referenced |

Eviction reasons are module constants: `REASON_SUPERSEDED`, `REASON_OVER_COUNT`, `REASON_OVER_BYTES`,
`REASON_POLICY_EXCLUDED`.

### `geos_registry`

| Symbol | Kind | Contract |
|---|---|---|
| `RegistryEntry` | frozen dataclass | `origin_id, write_id, writer, image_path, line_sha, written_at`; `.key == (origin_id, write_id)` |
| `registry_key(origin_id, write_id) -> (str,int)` | **IMPLEMENTED, pure** | empty/blank `origin_id` **raises** — an origin-less key recreates the collision this module exists to prevent |
| `entry_line(entry) -> str` | **IMPLEMENTED, pure** | canonical JSONL (sorted keys, compact) |
| `index_digest(lines) -> str` | **IMPLEMENTED, pure** | sha256 over ordered lines — changes when the log changes, stable when it does not |
| `line_sha_for(record) -> str` | **IMPLEMENTED, pure** | sha256 of the canonical record line |
| `WriteRegistry.register(record, origin_id)` | **STUB** | append-only; must reject duplicate keys rather than rewrite history |
| `WriteRegistry.lookup(origin_id, write_id)` | **STUB** | read-only scan; `[]` on miss; never fabricates an entry |
| `WriteRegistry.conflicts()` | **STUB** | keys mapping to >1 distinct `line_sha` |
| `WriteRegistry.scan(root)` | **STUB** | discover `(image, sidecar)` pairs; read-only |

## 5. Invariants (do not weaken without a ruling)

| # | Invariant | Enforced by |
|---|---|---|
| I1 | **Determinism** — same `(records, policy)` ⇒ same eviction set and order | pure core; leg 6 |
| I2 | **No silent loss** — every eviction names its rule | `Eviction.reason`; leg 5c |
| I3 | **Newest-wins is not the default** — per-writer quotas protect one writer's history from another's volume | pass 2; legs 5a/5d |
| I4 | **Additive only** — nothing here rewrites a committed image or sidecar | boundary map; stub design |
| I5 | **Global key is a pair** — `(origin_id, write_id)`, never `write_id` alone | `registry_key` refusal; leg 8 |
| I6 | **Canonical bytes** — a hash is a receipt in this repo, so identical events ⇒ identical lines | legs 7 |

## 6. Verification (Phase 5 gate for the skeleton)

```bash
python3 tools/geos_spine_verify.py      # exit 0
```

Result this run: **PASS — 36 legs green** across 10 sections: compiles, stdlib-only (AST scan, not grep),
imports, declared interfaces, stub return types, discriminating pure core, determinism, canonical bytes +
digest sensitivity, loud refusal paths, non-mutation, and failure-path liveness.

**What the gate proves:** the skeleton is structurally valid, the pure core is discriminating (each leg-5 check
has both directions, so an inverted or stubbed plan cannot satisfy them all), and the harness's own failure path
fires.
**What the gate does NOT prove — stated plainly:** Phase 3 I/O behaviour (stubs are unimplemented *by design*),
and semantic sensitivity of the harness to a mutated `retention_plan`. That mutation probe was attempted three
times this session and is **blocked by this host's operator-consent guard** (any command that rewrites source
text is refused). It is therefore **not claimed**. The compensating evidence is the bidirectional design of
leg 5 plus leg 10's liveness check. This boundary is recorded in the harness source at leg 10.

Per the skeleton rule: **do not run integration tests until there is a plausible path to success.** The stubs
here cannot yet do real work; that is correct for Phase 2.

## 7. Implementation roadmap (Phase 3 — the builder's fill-in order)

Ordered so each step is independently gate-able, and so nothing depends on an unverified step.

1. **`ArchiveStore.scan`-equivalent inside `plan()`** — read `archive_dir`, pair images with sidecars, call
   `parse_record`. Gate: a temp dir with N pairs yields N records; a sidecar-less image is skipped, not crashed on.
2. **`ArchiveStore.compact(plan)`** — delete exactly the planned records, return `{"deleted", "bytes"}`.
   Gate: plan then compact on a temp dir removes exactly the planned files and nothing else.
3. **The reference check** — `compact` refuses when an evicted record is referenced by a non-evicted sibling in
   the registry. Gate: construct the cross-reference, expect a loud refusal (not a silent delete).
4. **`WriteRegistry.register` / `lines` persistence** — append-only JSONL, duplicate-key rejection.
   Gate: register twice with the same key ⇒ refusal; index digest stable across re-open.
5. **`WriteRegistry.scan(root)`** — discover sidecars under a root, read-only.
   Gate: scanning a tree mutates nothing (sha256 tree snapshot before/after).
6. **`WriteRegistry.conflicts()`** — duplicate keys with differing `line_sha`.
   Gate: two distinct records sharing `(origin_id, write_id)` ⇒ reported.
7. **Wire-in (separate brief, separate gate)** — `geos_emit.publish()` records to the registry; retention is
   invocable from the operator path. Do **not** bundle this with steps 1–6.

**Definition of done for the whole round:** steps 1–6 each with their own RED→GREEN gate, plus a full
`tools/geos_spine_verify.py` PASS, plus the arc regression green. Step 7 is its own item.

## 8. Out of scope (explicit, so it is not assumed)

- No change to `tools/geos_emit.py`, `tools/geos_observation_server.py`, `tools/geos_witness.py` in Phase 1/2.
- Residency / Tier C — parked by the ruling, not touched here.
- Any publication-facing work (OSS GL-6/GL-7 publication) — Jericho's step per the ruling.
- Compaction *of the registry log itself* — the append-only invariant (I1 of the registry) means compaction
  would need its own ruling.

## 9. Files

| File | Role |
|---|---|
| `tools/geos_archive.py` | retention contract; pure core implemented, I/O stubbed |
| `tools/geos_registry.py` | global index contract; pure helpers implemented, I/O stubbed |
| `tools/geos_spine_verify.py` | structural verification harness (10 sections, 36 legs) |
| `systems/GLYPH_SPINE_SKELETON.md` | this document — architecture lock + Phase 3 roadmap |
