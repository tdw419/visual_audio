# REPAIR_PENDING — SPINE wire-in: who calls retention, and with which policy

**Status:** ✅ LANDED 2026-09-13 (commit `722cc27`, receipt `systems/RECEIPT_SPINE_R2_WIREIN.md`) — ruled option 2
implemented (`publish()` best-effort registry append + operator retention CLI); re-verified by the orchestrator at
head `2e045e0`: `pytest tests/test_spine_r2_wirein.py -q` green (13 passed together with the OS-SKEL step-9 +
DEFECT-18 gates, 1.17 s, exit 0). Superseded header kept for the record: RULED 2026-09-13 — see
`.builder_queue/RULING_spine_wirein.md` (OPTION 2; gate `tests/test_spine_r2_wirein.py`). · **Type:** design question (not a
defect) · **Seat:** lane (Jericho) · **Filed:** 2026-09-12,
builder cron `af3e62239ce2`, the tick that held at `64bd407` (OS-SKEL-R3 step 8 was the last eligible row).

## The question

`systems/GLYPH_SPINE_SKELETON.md:148` § 7 item 7 — *"Wire-in (separate brief, separate gate)":*
`tools/geos_emit.publish()` should record to the `WriteRegistry`, and retention should be invocable from the
operator path. Both halves are **unbuilt**, measured this tick not re-read from prose:

- `grep -rln geos_registry tools/ tests/` → matches in `tools/geos_registry.py`, `tools/geos_archive.py`,
  `tools/geos_spine_verify.py`, `tests/test_spine_r1_*.py` — **no `tools/geos_emit.py`** (the publish path
  never touches the registry).
- The round's own receipt already classified this as Jericho's call, not a builder call:
  `systems/RECEIPT_SPINE_R1.md:98-99` — *"The registry → `publish()` wire-in remains a named, unauthored
  follow-up (design question: who calls retention, and with which policy — Jericho's call, not the
  builder's)"*, and `:75-77` — *"No wire-in … nothing in the publish or teleop path changed in this round."*

## Why the loop stopped here

The mechanical half of SPINE-R1 is finished and gated (7 steps, `6168944` + `systems/RECEIPT_SPINE_R1.md`).
What remains is a **policy + call-path choice**, and each candidate answer changes the interface that the
round's "interfaces are LOCKED" clause covers — so it is exempt from self-promotion under the standing rule
("no design judgment"):

1. which process decides eviction — the publisher inline, or an operator CLI;
2. what the default retention policy is (keep-N / max-age / max-bytes / explicit plan only);
3. what a `compact()` cross-reference refusal (step 3's loud refusal) looks like **on the operator path** —
   an exit code, or a written plan the operator must apply;
4. whether a failed registry append during `publish()` is fatal or best-effort (the DEFECT-20 write-id
   counter is a read-modify-write with no lock, so "fatal" imports that weakness into the publish path).

## Options (cheapest first — for the ruling, not for the builder)

1. **Operator CLI only** (`tools/geos_retain.py --plan/--apply`), `publish()` unchanged. Smallest change and
   touches no existing caller, but DEFECT-20's write identity stays *unindexed* at the moment it is minted.
2. **`publish()` best-effort append + operator CLI for retention.** The index gets written where the
   identity is minted; needs an explicit rule for a failed append (log-and-continue vs mark the write
   unattributed). This is the option the round's own wording ("`geos_emit.publish()` records to the
   registry") most directly describes.
3. **`publish()` mandatory append (fails loud) + operator CLI.** Strongest invariant, but every publish path
   then depends on the registry file being writable — a new failure mode on a path that today succeeds
   unconditionally.

Prerequisite already landed: the write-id / `line_sha` provenance work (DEFECT-20,
`systems/RECEIPT_DEFECT20_WRITE_IDENTITY.md`, `tools/geos_registry.py` `line_sha_for` / `entry_line`).

## What the loop will do until a ruling lands

Nothing on this item. `tools/geos_emit.py` is **not** touched by the builder loop for this purpose, and a
future tick that finds this note should treat the item as BLOCKED-ON-DESIGN and pick the next eligible
source instead of re-deriving it.

Related open lane items, so one ruling can clear them together:
`.builder_queue/REPAIR_PENDING_oskel_step9_space_lifetime_ownership.md` (OS-SKEL step 9, 3 options) and the
`tools/geos_os_skel_verify.py` leg-6g lane review noted at
`.builder_queue/NEXT_TARGET_oskel_step8_or_defects.md:23`.
