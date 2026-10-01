# RULING — SPINE wire-in: who calls retention, and with which policy

**Ruled:** 2026-09-13 · **Decides:** `.builder_queue/REPAIR_PENDING_spine_wirein_design.md`
**Decision seat:** Jericho · **Drafted by:** Hermes, authorized by "You lead" (2026-09-13).

## Ruling: OPTION 2 — `publish()` best-effort append + operator CLI, with the four sub-questions answered

### The four open questions, answered

1. **Who decides eviction** — the **operator CLI** (`tools/geos_retain.py`). `publish()` never evicts. A publish
   path that can destroy archives is a publish path that can lose data on a typo.
2. **Default policy** — **explicit-plan-only.** With no flags, `--apply` evicts nothing; the operator must name
   a policy (`--keep-last N`, `--max-bytes B`, `--tag-exclude T`) or supply a plan. Retention is the one
   operation in this project that destroys data, so the safe default is the one that does nothing.
3. **Refusal shape on the operator path** — written plan **plus a non-zero exit code**:
   `0` plan/apply succeeded · `2` refused (registry cross-reference or unknown writer), reason written into the
   plan file and stderr · `1` internal error. Scripted callers can therefore detect a refusal without parsing prose.
4. **Failed registry append during `publish()`** — **best-effort, loudly labeled.** The publish still succeeds
   (it succeeds unconditionally today), and the sidecar is written with `unattributed: true` and
   `unattributed_reason: "<why>"`. Never fatal, never silent.

### Why not the other options

- **Option 3 (mandatory append, fails loud):** imports DEFECT-20's *unlocked read-modify-write* into a path that
  currently cannot fail. New failure mode on the hot path for a provenance nicety — reject.
- **Option 1 (operator CLI only, publish untouched):** leaves the write identity unindexed at the exact moment it
  is minted, which is the gap this round exists to close — reject.

### Gate clause (RED first)

New gate `tests/test_spine_r2_wirein.py`:

1. **Best-effort append, negative control.** Point `publish()` at a read-only/unwritable registry path in a temp
   dir -> publish **succeeds**, sidecar has `unattributed: true` with a reason. (RED before implementing: the
   current `publish()` has no such field.)
2. **Happy path.** Successful publish appends **exactly one** line, and `line_sha` of that line equals
   `line_sha_for(entry)` (the DEFECT-20 provenance helper) — no drift between mint and index.
3. **`--plan` is non-destructive.** On a fixture where one archive is referenced by the registry, `--plan` writes
   a plan, exits 0, and **every file still exists** afterwards (assert by directory listing before/after).
4. **`--apply` is idempotent.** First `--apply` removes exactly the planned set; a second `--apply` is a no-op
   (exit 0, nothing further removed).
5. **Refusal.** A plan that would evict a registry-referenced archive exits **2**, writes the reason, and deletes
   nothing.
6. **Default is inert.** `--apply` with no policy flags evicts nothing and says so.

### Cost / unblocks

One new CLI (`tools/geos_retain.py`), a small append in `geos_emit.publish()`, one gate file. Unblocks the last
named SPINE-R1 follow-up. **Does not** change `geos_emit`'s write-id minting, and does not add a lock to
DEFECT-20's counter (explicitly out of scope here — if that counter needs a lock, it is its own ticket).
