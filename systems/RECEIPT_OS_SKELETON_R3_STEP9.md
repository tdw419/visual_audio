# RECEIPT — OS-SKEL-R3 step 9: space lifetime ownership (refcount-only teardown)

**Status:** ✅ done 2026-09-13 · **Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` → `OS-SKEL-R3-S9`
**Authority:** `.builder_queue/RULING_oskel_step9_space_lifetime.md` (OPTION 1) — implemented as ruled, not re-derived.
**Commits:** promotion `903ffc4` · implementation `d0f4ced` · **Head at verification:** `d0f4ced`
**Delegation:** `agy` (`output/agy/agy_impl_20260913_071338.log`, exit 0, 431 s) — every number below is the orchestrator's own run, not the delegate's claim.

## The defect

One asid, two owners. `Proctab.reap` freed the asid itself (`tools/geos_proctab.py` →
`allocator.free(desc.asid)`), while `AddressSpace.release()` already frees the asid at
refcount 1→0 (`tools/geos_aspace.py:296`). A shared space (refcount > 1 — the shape
`ready_set()` implies) was therefore freed by the reaper **and then again by its owner**.

## Mechanism landed

- `tools/geos_aspace.py` — `SpaceSource` type + `set_space_source()` / `get_space_source()`
  (same idiom as `set_mmio_sink` / `set_asid_allocator`) and
  `drop_reference(asid) -> int`: resolve through the bound source, `KeyError` for an
  unknown/unresolvable asid, else `AddressSpace.release()`'s existing accounting
  (frees exactly at 1→0, refuses below zero). No new state names, no signature changes.
- `tools/geos_proctab.py` — `reap` calls `geos_aspace.drop_reference(desc.asid)` instead of
  `allocator.free`. **Added (orchestrator): an I5 refusal** — a descriptor that names no
  space is malformed, so reap raises `KeyError` and mutates nothing rather than inventing a
  space. The kernel-level binder is not wired yet, so reap synthesizes a proctab-backed
  source for the duration of the call and restores the previous hook in a `finally`.
- `tests/test_osskel_space_lifetime.py` (NEW) — L1 single free at 1→0 (counting allocator
  double records exactly 1 `free`), L2 shared space survives one reap / second
  `drop_reference` frees it, L3 second release still refuses, L4 transitive no-double-free
  across spawn→exit→reap, L5 space-less descriptor refused loudly and nothing mutated.
- `tests/test_osskel_spawn_integration.py` — the R2 step-7 assertion re-pointed from the
  double-free `KeyError` to the refcount-0 refusal (the ruling's leg 5).

## RED (before the fix) — three independent falsifiers

| Probe | Artifact | Result |
|---|---|---|
| Gate vs pre-fix `tools/*` at HEAD | `output/osskel_r3_step9_gate_RED_prefix.txt` | pytest **exit 2**, collection error (`drop_reference`/`set_space_source` absent) |
| `drop_reference` neutered (returns without releasing) | `output/osskel_r3_step9_probe_neutered_dropref.txt` | **4 failed / 1 passed** — L1–L4 RED, L5 unaffected |
| I5 refusal neutered | `output/osskel_r3_step9_probe_neutered_i5.txt` | **1 failed / 4 passed** — L5 RED (reap mutated, then raised) |
| **Pre-fix R2 assertion vs the new code** (the ruling's decisive leg) | `output/osskel_r3_step9_oldL5_RED.txt` | `RuntimeError: aspace asid=0 released more times than acquired` — the seam really was removed; a green here would have meant nothing changed |

All three probes reverted the live modules to their committed bytes (`md5sum` verified
before and after each probe).

## GREEN (after the fix)

- Gate + 4 landed osskel gates: **55 passed in 0.36 s, exit 0** (`output/osskel_r3_step9_gate_GREEN.txt`).
- `python3 tools/geos_os_skel_verify.py` **exit 0** — "OS SKELETON VERIFY: PASS — structure
  locked, engine facts pinned, pure core discriminating, live guards enforcing"
  (`output/osskel_r3_step9_skel_verify.txt`).
- Module smoke `python3 tools/geos_proctab.py` **exit 0** ("reap(1) -> 42") — it had to be
  fixed too: it admitted a space-less process (`output/osskel_r3_step9_proctab_smoke.txt`).
- **Arc leg A, pinned:** `SEED=973012357 bash tools/arc_lega.sh` at head `d0f4ced` →
  **325 passed / 1 skipped / 1 deselected, rc=0, crashes=0, 119.68 s**
  (`output/arc_lega_seed973012357_d0f4ced.txt` + `.json` sidecar). The 1 deselected is the
  gh12 live-draft smoke leg (`-m "not live_smoke"`), per `RULING_arc_determinism_standing.md`.

## Decisions taken in this tick (not inherited from the ruling)

1. **The delegate's `admit()` invented a default space.** agy had added
   `if "aspace" not in desc.meta: desc.meta["aspace"] = AddressSpace(asid=desc.asid,
   pt_base_word=1536)` inside `Proctab.admit` — which contradicts the module's own locked
   invariant I5 ("A process without an aspace is a malformed process, not a default one").
   Measured consequence: with that line removed, 4 landed R2 legs went red
   (`test_osskel_proctab_lifecycle.py` L1/L2/L4/L6 — they admit space-less descriptors and
   then reap them).
2. **Chosen resolution: fixtures, not production defaults.** Removed the invention, made
   reap refuse a space-less descriptor loudly (I5), and gave the affected fixtures a space
   (`_spawn` helper + 2 direct admits in `test_osskel_proctab_lifecycle.py`; the live probe
   in `tools/geos_os_skel_verify.py`; the `__main__` smoke). **No assertion was weakened** —
   the fixtures now describe well-formed processes. The alternative (keep the default)
   would have made the module's own I5 statement false.
3. **Added gate leg L5** to gate the refusal introduced by (2) — behavior I introduced
   must be gated, and it is (probe above turns it RED).

## Honest boundary (what this does NOT show)

- The `set_space_source` hook has no production binder yet: the kernel does not register a
  source, so reap synthesizes a transient one from the proctab. Reaping a process whose
  asid belongs to a space the proctab cannot see is therefore still untested — that is the
  kernel-wiring step, not this one.
- The proctab still holds a *direct* `allocator` guard (`desc.asid not in allocator.live()`)
  before the drop; the allocator is thus still consulted for validity, even though the
  space is now the owner. Removing that belongs to the kernel-wiring round.
- No engine, WGSL or locked-signature change was needed (as the ruling predicted).
- L4's "at most once per asid, ever" is asserted over a single spawn→exit→reap sequence
  with a counting double, not over an arbitrary interleaving.
