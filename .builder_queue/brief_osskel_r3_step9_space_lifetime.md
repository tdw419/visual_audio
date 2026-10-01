# BRIEF — OS-SKEL-R3-S9: space lifetime ownership (ruled OPTION 1, refcount-only teardown)

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` → `OS-SKEL-R3-S9` (⏳ queued 2026-09-13, promotion commit `903ffc4`).
**Authority:** `.builder_queue/RULING_oskel_step9_space_lifetime.md` — OPTION 1 is already ruled; implement it, do not re-litigate it.
**Repo:** `/home/jericho/projects/zion/projects/visual_audio` (branch `glyph-transpiler-autoloop`). Shared with parallel sessions — touch ONLY the files in scope below.

## The defect this closes (measured, do not re-derive)

`Proctab.reap` frees the asid itself: `tools/geos_proctab.py:266` → `allocator.free(desc.asid)`.
`AddressSpace.release()` already frees the asid at refcount 1→0: `tools/geos_aspace.py:296-311`.
Two owners of one asid ⇒ a shared space (refcount > 1, the shape `ready_set()` implies) is freed by the reaper and then freed again by its owner.

## What to implement (exact shape from the ruling)

1. **`tools/geos_aspace.py`** — interface-additive only:
   - `set_space_source(fn)` / module-level getter, in the same idiom as the existing `set_mmio_sink` (`:101`) and `set_asid_allocator` (`:118`) hooks. `fn(asid) -> AddressSpace | None`.
   - `drop_reference(asid: int) -> int` — resolve the space through the bound source; if no source is bound **or** it returns `None`, raise `KeyError(f"unknown asid {asid}")` (loud, never silent); otherwise decrement the space's refcount **through the existing accounting** (`AddressSpace.release()` already implements "free the asid exactly at 1→0" and "refuse below zero" — reuse it, do not duplicate the arithmetic) and **return the remaining refcount**.
   - **No new state names** (no `retire()`, no "retired" flag — the ruling rejects that). No renamed methods, no changed existing signatures.
2. **`tools/geos_proctab.py`** — `Proctab.reap` (`:250`): call `geos_aspace.drop_reference(desc.asid)` instead of `allocator.free(desc.asid)`. Keep every existing loud guard (unknown pid → `KeyError`, non-zombie → `InvalidTransition`, unbound allocator → `RuntimeError`, pid not live → `KeyError`). The `desc.asid not in allocator.live()` guard at `:264` must be re-expressed so that **a shared space (asid still live) is no longer a reap error** — decide the exact new rule, keep it loud for genuinely unknown asids, and state the rule you implemented in your completion note.
3. **`tests/test_osskel_space_lifetime.py`** (NEW file) — the gate, legs exactly as the roadmap row states:
   - **L1 single free at 1→0**: space at refcount 1, reap the owning process → the asid is gone from `allocator.live()` and a counting allocator double records exactly **1** `free` call for that asid.
   - **L2 shared space survives**: space at refcount 2 (second holder), reap the process → asid **still live**; the second `drop_reference` frees it.
   - **L3 second release still refuses**: `release()` / `drop_reference` on a freed space still raises, loudly.
   - **L4 no double free, transitively**: across a `spawn → exit → reap` sequence with a counting allocator double, `free` is called **at most once per asid, ever**.
   - **L5 re-point the old assertion**: `tests/test_osskel_spawn_integration.py` `test_l5_lifecycle_end_to_end` lines **249-253** and **271-273** currently assert `desc.meta["aspace"].release()` raises `KeyError` after reap (the double-free refusal). Rewrite those assertions to the refcount-0 refusal the ruling names (*single free at refcount 0*). **Run the OLD assertion against the NEW code first and show it RED** — if it still passes, the seam was not actually removed and you must say so plainly instead of editing it green.
4. Nothing else. No engine, no WGSL, no locked-signature change.

## Gate commands (run these yourself; paste real output)

```
/usr/bin/python3 -m pytest tests/test_osskel_space_lifetime.py -q
/usr/bin/python3 -m pytest tests/test_osskel_space_lifetime.py tests/test_osskel_spawn_integration.py tests/test_osskel_proctab_lifecycle.py tests/test_osskel_aspace_release.py tests/test_osskel_aspace_switch.py tests/test_osskel_engine_switch.py tests/test_osskel_aspace_map.py tests/test_osskel_caps_table.py tests/test_osskel_devtab_register.py -q
/usr/bin/python3 tools/geos_os_skel_verify.py
```

## Evidence your completion note MUST contain

1. **RED first** (write the gate before the fix is in place): the gate file run against the UNMODIFIED `tools/geos_aspace.py` + `tools/geos_proctab.py` → paste the failing output (this is the RED receipt; save it under `output/`).
2. **GREEN after**: the gate's summary line + exit code.
3. **Old-L5 RED**: the R2 step-7 assertion run against the new code, failing as expected — with the exact assertion text and error.
4. **No regression**: the 9-module osskel summary line + exit code, and `geos_os_skel_verify.py` output (must stay PASS; it prints a leg count — paste it).
5. **Non-vacuity, out-of-tree, live files restored byte-identical afterwards** (paste `md5sum -c` proof): (a) neuter `drop_reference`'s free path → L1 must go RED; (b) make `drop_reference` return without decrementing the refcount → L2 must go RED.

## Boundaries (hard)

- **Do NOT commit, do NOT push, do NOT stash/checkout other sessions' work.**
- **Do NOT run the full arc / pytest over the whole repo** — the orchestrator runs the arc itself.
- In scope: `tools/geos_aspace.py`, `tools/geos_proctab.py`, `tests/test_osskel_space_lifetime.py` (new), `tests/test_osskel_spawn_integration.py` (the L5 assertions only), plus your own evidence files under `output/` and `.builder_queue/`.
- Out of scope: `tools/glyph_isa_v2.py`, WGSL shaders, `tools/glyph_gpt/**`, any locked signature. If an engine or signature change looks necessary, **STOP and report** rather than editing.
- Report honestly: a green you did not run, or a leg you assert without output, is worse than a reported failure.
