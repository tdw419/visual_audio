# REPAIR_PENDING — OS-SKEL step 9: ownership of a space's lifetime is still on `reap`

**Status:** ✅ LANDED 2026-09-13 (commit `d0f4ced`, receipt `systems/RECEIPT_OS_SKELETON_R3_STEP9.md`) — ruled option 1
implemented; re-verified by the orchestrator at head `2e045e0`: `pytest tests/test_osskel_space_lifetime.py -q`
green (13 passed together with the SPINE wire-in + DEFECT-18 gates, 1.17 s, exit 0). Superseded header kept for the
record: RULED 2026-09-13 — see `.builder_queue/RULING_oskel_step9_space_lifetime.md` (OPTION 1, refcount-only
teardown; gate `tests/test_osskel_space_lifetime.py`). · **Type:** needs an interface
decision (not a defect) · **Seat:** lane (Jericho) · **Filed:** 2026-09-12,
builder cron `af3e62239ce2`, the tick that closed step 8 (`systems/RECEIPT_OS_SKELETON_R3_STEP8.md`).

## The question

`systems/RECEIPT_OS_SKELETON.md` § 5 asks for two things after the R2 round. The first —
wire `AddressSpace.switch` to the real engine — **landed** (`tools/geos_engine_sink.py` + gate
`tests/test_osskel_engine_switch.py`). The second is this one:

> "move ownership of a space's lifetime off `reap`".

Measured state (R2 receipt § 2, seam (b)): `Proctab.reap` **retires the asid through the bound `AsidAllocator`**, so a
later `AddressSpace.release()` on that same retired space frees the asid a second time — refused loudly by
`AsidAllocator.free`, and asserted as such (R2 step-7 L5). The consequence is a *second* owner of the space's lifetime:
the address-space module and the process table both think they may free it.

## Why the loop did not do it

The fix that the R2 round itself names — a `CapTable.create(pid)`-class API for the cap row, and an
`AddressSpace.retire()`/refcount-driven teardown for the asid — is an **interface change**: the R2 round ran under
"interfaces are LOCKED, do not change signatures, dataclass fields, state names, cap bit values, or constants — if one
looks wrong, STOP and report; that is a skeleton-sign-off change, not a builder call"
(`.builder_queue/brief_osskel_r2_phase3.md`). So this is not a builder call and is not self-promotable under the
standing rule ("no design judgment").

## Options (for the ruling, cheapest first)

1. **Refcount-only teardown.** `reap` stops calling `AsidAllocator.free` directly and instead drops the space's
   refcount (the space owns its asid); the asid frees at the 1 → 0 transition, exactly where `AddressSpace.release`
   frees it today. Needs one new call path from `geos_proctab` into `geos_aspace` (a module-level hook in the same idiom
   as `set_mmio_sink` / `set_asid_allocator`, or an explicit `AddressSpace.retire()`).
2. **Explicit ownership hand-off.** `reap` calls `space.retire()`, which frees the asid and marks the space retired;
   `release()` on a retired space returns 0 instead of double-freeing. Least code, but adds a state name — a
   skeleton-sign-off change.
3. **Leave it, document it.** The current behaviour is a *loud* refusal, not silent corruption; step-7 L5 already
   pins it. Cheapest, and defensible if nothing consumes the lifecycle yet (`ready_set()` has no consumer).

No option is a builder call; option 1 or 2 needs Jericho's sign-off on the interface, option 3 is a decision to stop.

## Until it is ruled

The loop holds on this item (it will not invent the interface) and, per `.builder_queue/NEXT_TARGET_oskel_step8_or_defects.md`,
has no other eligible self-promotable unit: self-hosting roadmap 0 open rows, `GLYPH_BACKLOG.md` BK-1..BK-14 + OBS-1 all
landed, OSS GL-6/GL-7 loop-side done, GL-8+ waiting on a stranger's friction report, and the lane choice / publication /
Tier C reserved to Jericho (`.builder_queue/RULING_lane_supply_20260912.md` § Reserved).
