# RULING — OS-SKEL step 9: ownership of a space's lifetime

**Ruled:** 2026-09-13 · **Decides:** `.builder_queue/REPAIR_PENDING_oskel_step9_space_lifetime_ownership.md`
**Decision seat:** Jericho · **Drafted by:** Hermes, authorized by the directive "You lead" (2026-09-13).
Provenance is recorded because the seat is Jericho's; the ruling is executed under explicit authorization.

## Ruling: OPTION 1 — refcount-only teardown

A space's asid is owned by the **space**, not by the process table. `Proctab.reap` stops calling
`AsidAllocator.free` directly and instead **drops a reference** to the space; the asid is freed exactly at the
`1 -> 0` transition, which is where `AddressSpace.release()` already frees it today.

### Shape of the change (interface-additive; no locked signature changes)

- `tools/geos_aspace.py` gains a module-level **space source hook**, in the same idiom the module already uses
  for `set_mmio_sink` / `set_asid_allocator`:
  - `set_space_source(fn)` — `fn(asid) -> AddressSpace | None`
  - `drop_reference(asid) -> int` — looks up the space, decrements its refcount, frees the asid at 0, and
    returns the remaining refcount. Unknown asid raises `KeyError` (loud, not silent).
- `Proctab.reap` calls `geos_aspace.drop_reference(asid)` instead of the allocator's `free`.
- **No new state name.** `retire()` + a "retired" state (option 2) is rejected: it adds vocabulary to a locked
  interface and encodes a weaker invariant than `refcount == 0`.

### Why not the other options

- **Option 2 (explicit `retire()` hand-off):** more sign-off churn on a locked interface, and "retired" is a
  flag that can drift out of sync with the refcount, where refcount==0 cannot.
- **Option 3 (leave it, document it):** the current loud refusal only protects callers that route through
  `free()`. `ready_set()` has no consumer *yet*; the moment one exists this is a live double-free. "Documented"
  is not "safe" — reject.

### Gate clause (RED first)

New gate `tests/test_osskel_space_lifetime.py`:

1. **Single free at 1 -> 0.** Space at refcount 1, reap the owning process -> asid is gone from
   `allocator.live()`, exactly once (a counting double asserts `free` called 1x for that asid).
2. **Shared space survives.** Space at refcount 2 (a second holder), reap the process -> asid **still live**;
   the second `drop_reference` frees it.
3. **Second release still refuses.** `release()`/`drop_reference` on a freed space raises, unchanged.
4. **No double free, transitively.** Across a spawn -> exit -> reap sequence with a counting allocator double:
   `free` is called at most once per asid, ever. This is the leg that would have caught the R2 seam.
5. **RE-POINT the old assertion.** R2 step-7 `L5` asserted the *double-free refusal*; that assertion must be
   rewritten to assert *single free at refcount 0*. Re-run the old L5 against the new code first and show it
   RED — if it still passes, the seam was not actually removed.

### Cost / unblocks

~1 new function + 1 hook setter in `geos_aspace`, the `reap` body, one new gate file, and the L5 rewrite.
Unblocks OS-SKEL step 9 and restores a single owner for space lifetime. Does **not** touch the engine, WGSL,
or any existing locked signature.
