# BRIEF — OS-SKEL-R2 Phase 3, STEP 3 of 7: `AddressSpace.release` + `AsidAllocator` wiring

**Target id:** OS-SKEL-R2 Phase 3 step 3 (`systems/GLYPH_OS_SKELETON.md` § 6 Phase 3 roadmap rows 3-4, lines 165-166;
round brief `.builder_queue/brief_osskel_r2_phase3.md`, step-3 gate clause). Step 1 (`map`/`unmap`) landed at
`e4cfa2c`; step 2 (`switch` + the module-level MMIO sink) landed at `f8e5d79`.
**Spec is the skeleton — read it FIRST:** `systems/GLYPH_OS_SKELETON.md` lines 165-166, invariant **I5**
(`tools/geos_aspace.py:36`), the class docstring (`tools/geos_aspace.py:220-234`) and the current `release`
body (`tools/geos_aspace.py:279-288`).
**Interfaces are LOCKED** — signatures, dataclass fields, state names, constants, `__post_init__`. If one looks
wrong, STOP and report; that is a skeleton-sign-off change, not a builder call.

**Files in scope (only these may change):**
- `tools/geos_aspace.py` — fill the `release()` body (`:279-288`), add the module-level allocator hook below
  ONLY, and update the module docstring `PHASE STATUS` line if one exists. Do not touch `map`/`unmap`/`switch`,
  `AsidAllocator`, `__post_init__`, the constants, or any invariant text.
- `tests/test_osskel_aspace_release.py` — NEW gate file.
- `output/osskel_r2_step3_red.txt`, `output/osskel_r2_step3_green.txt`, `output/osskel_r2_step3_arc.txt` — evidence captures.

**Do NOT** touch `tests/test_osskel_aspace_map.py`, `tests/test_osskel_aspace_switch.py`, any other existing
`tests/*.py`, `tools/geos_os_skel_verify.py` (the structural harness), `tools/geos_caps.py`,
`tools/geos_proctab.py`, `tools/geos_devtab.py`, `tools/glyph_isa_v2.py`, WGSL, `tools/glyph_gpt/**`,
`tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, `systems/**`, `.builder_queue/**`.
Stdlib only (`geos_os_skel_verify.py` AST-scans for third-party imports). **DO NOT COMMIT.**

## Mechanism — DECIDED by the orchestrator, do not redesign

Fields and signatures are frozen, so `release()` keeps its **zero-argument** signature and the allocator is
reached through a module-level binding — the same idiom step 2 already established for the MMIO write path
(round brief `:30-34`). Do **not** invent a second injection idiom, do not add a dataclass field, and do not add
an `allocator` parameter to `release()`.

```python
_asid_allocator: Optional[AsidAllocator] = None

def set_asid_allocator(allocator: Optional[AsidAllocator]) -> None:
    """Bind the allocator whose asids this module's spaces are drawn from; None unbinds."""

def get_asid_allocator() -> Optional[AsidAllocator]:
    """Current bound allocator (None when unbound) — for tests and teardown."""
```

`set_asid_allocator` raises `TypeError` when given something that is neither `None` nor an `AsidAllocator`.
`set_asid_allocator` / `get_asid_allocator` / the private binding must **NOT** be appended to `__all__`.
Keep them next to the existing `set_mmio_sink` / `get_mmio_sink` helpers so there is visibly ONE injection
convention in this module.

## Behaviour to implement (I5 — exact; do not add features)

`release() -> int`
1. `self.refcount <= 0` → raise `RuntimeError` (keep the existing message/behaviour: released more times than
   acquired).
2. `self.refcount == 1` → this is the transition to zero, i.e. the teardown:
   - **Check before you mutate.** If no allocator is bound (`get_asid_allocator() is None`) → raise
     `RuntimeError` naming the condition (e.g. `"no asid allocator bound: refusing to report a release that
     freed nothing"`) and leave `refcount` at 1. A release that reports success while freeing nothing is the
     anti-pattern this project refuses elsewhere — do not soften it into a no-op and do not invent a default
     allocator.
   - Otherwise call `allocator.free(self.asid)` **exactly once**, then set `self.refcount = 0` and return 0.
     If the allocator raises (e.g. `KeyError` because it never allocated that asid, or a caller bug), let it
     propagate — never catch it and never report a successful teardown.
3. `self.refcount > 1` → decrement and return the new count. The asid must stay live in the allocator; nothing
   is freed until the count reaches 0.

`pin()` is unchanged. Freeing happens exactly once, at the 1 → 0 transition, and never twice.

## Gate — `tests/test_osskel_aspace_release.py` (new; RED before the implementation)

Each leg asserts observable behaviour (allocator `live()` / raised exception / returned count), never internals:

- **L1 refcount descent:** `alloc = AsidAllocator()`; `asp = AddressSpace(asid=alloc.alloc(), pt_base_word=1536)`;
  `asp.pin()` → 2; `release()` → 1 and the asid is still in `alloc.live()`; `release()` → 0 and the asid is gone
  from `alloc.live()`.
- **L2 freed asid is reused before a higher one:** alloc three spaces (asids 0, 1, 2); release the middle one to
  zero; the next `alloc()` returns 1 (lowest free) — not 3 — and `live()` is `[0, 2, 1]`-as-a-set plus the new one.
- **L3 below-zero release raises:** a space already at refcount 0 → `release()` raises `RuntimeError` and the
  allocator's `live()` is unchanged (no double free, no state damage).
- **L4 loud refusal with no allocator bound:** fresh space (refcount 1), `set_asid_allocator(None)` → `release()`
  raises `RuntimeError` **and the refcount is unchanged** — proven by binding a real allocator afterwards and
  getting a normal 1 → 0 release that returns 0 and frees the asid.
- **L5 the allocator's contract is not swallowed:** space whose asid the bound allocator never allocated
  (`AddressSpace(asid=7, ...)`) → release to zero raises `KeyError` from the allocator (propagated).
- **L6 binding hygiene / non-vacuity:** `get_asid_allocator()` is `None` before binding, the bound object after
  `set_asid_allocator(alloc)`, and `None` again after `set_asid_allocator(None)`; `set_asid_allocator(42)` raises
  `TypeError`. Use a fixture/`finally` so this gate cannot leak its binding into other tests.

## Evidence and reporting discipline

- **RED first:** create the gate file, run it BEFORE implementing, save the literal output to
  `output/osskel_r2_step3_red.txt` (expect collected-but-failing legs, not a collection error — if the module
  cannot even import, say so explicitly).
- **GREEN:** `/usr/bin/python3 -m pytest tests/test_osskel_aspace_release.py -q` → exit 0, all legs pass; save
  to `output/osskel_r2_step3_green.txt`. Also run the gate under the repo `.venv` (py3.11) and record the tail.
- **Structural harnesses must stay PASS:** `python3 tools/geos_os_skel_verify.py` (exit 0, 85 legs) and
  `python3 tools/geos_spine_verify.py` (exit 0).
- **Arc regression:** `/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_spine_r1_*.py tests/test_osskel_*.py -q`
  → exit 0; append the tail to `output/osskel_r2_step3_arc.txt`. Report the passed/failed/skipped counts.
- Paste the **literal tail** of every run in your final message (last ~5 lines each). A claim without a pasted
  tail is not evidence.
- **DO NOT COMMIT.** The orchestrator re-runs the gate itself and commits with RED→GREEN in the commit body.
- One step only: stop when step 3 is green. Steps 4-7 (`CapTable`, `Proctab`, `Devtab`, `spawn()`) are later runs.
