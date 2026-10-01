# BRIEF — OS-SKEL-R2 Phase 3, STEP 1 of 7: `AddressSpace.map` / `unmap`

**Target id:** OS-SKEL-R2 Phase 3 step 1 (`systems/GLYPH_OS_SKELETON.md` § 6 Phase 3 roadmap;
round brief `.builder_queue/brief_osskel_r2_phase3.md`, row 1).
**Spec is the skeleton, read it FIRST:** `systems/GLYPH_OS_SKELETON.md` (Phase 3 todo list +
the `AddressSpace` class docstring in `tools/geos_aspace.py:195-217`). Interfaces are LOCKED.
**Files in scope (only these may change):**
- `tools/geos_aspace.py` — fill in the bodies of `map()` (`:238`) and `unmap()` (`:242`) ONLY.
- `tests/test_osskel_aspace_map.py` — NEW gate file.
- `output/osskel_r2_step1_red.txt`, `output/osskel_r2_step1_green.txt` — evidence captures.

**Do NOT** change signatures, dataclass fields, constants, `__post_init__`, `pin`, `release`, or the
other stubs (`switch`, `clone_for_fork` stay stubs — they are steps 2 and 3). Do NOT touch
`tools/glyph_isa_v2.py`, WGSL, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`,
`systems/**`, `.builder_queue/**`, or any existing `tests/*.py`. Stdlib only.

## Behaviour to implement (from the class docstring — do not re-derive, do not redesign)

`map(vpn, pfn, flags) -> Optional[int]`
- validate `vpn` range: `0 <= vpn < 256` (VPN capacity is 256) — out of range raises `ValueError`.
- if `vpn` is already present in `self.entries`, this is a remap of a **live** entry without an explicit
  `unmap()` first: raise `RuntimeError` (silent aliasing is how two processes end up sharing a frame).
- otherwise write `self.entries[vpn] = pte_pack(pfn, flags)` and return the previous entry or `None`.

`unmap(vpn) -> Optional[int]`
- pop and return the previous entry for `vpn`; return `None` when the vpn is absent.
- refuse (raise `RuntimeError`) when the entry is `PTE_HILB` **and** a live frame binding exists
  (GH-25 spatial frames are shared) — if the skeleton gives no way to observe "a live frame binding
  exists", say so plainly in your report and implement the observable part only; do NOT invent a
  field or a flag to make it observable. Additive-only answer expected: **unmap may be a pure pop+
  return** if the sharing observable does not exist in the skeleton. That is acceptable this step.

## Gate — `tests/test_osskel_aspace_map.py`, run it yourself and paste the real tail

Gate command (orchestrator re-runs this exact one):
```
/usr/bin/python3 -m pytest tests/test_osskel_aspace_map.py -q 2>&1 | tail -20
```

Legs (all four must exist and assert the committed behaviour, not a tautology):
- **L1** map → read back the PTE: `map(5, 7, PTE_V|PTE_W|PTE_U)` then `entries[5]` equals
  `pte_pack(7, PTE_V|PTE_W|PTE_U)` and `pte_unpack(entries[5]) == (7, PTE_V|PTE_W|PTE_U)`.
- **L2** remap of a live entry WITHOUT unmap raises (`pytest.raises(RuntimeError)`), and the original
  PTE is unchanged after the refusal.
- **L3** `vpn >= 256` raises `ValueError` (test both 256 and a large value); a legal `vpn == 255` succeeds.
- **L4** legitimate remap-after-unmap: `map` → `unmap` (returns the previous PTE) → `map` same vpn with a
  different pfn succeeds and the **returned value is the previous entry**, not `None`, and not the new one.
- Add one **non-vacuity / discriminator leg** that fails against the current `return None` stub: the RED
  capture below is exactly that, so keep the gate honest by asserting the readback (L1) and the raisings
  (L2/L3) — a `return None` body must make the file RED, not GREEN.

## Evidence discipline

1. BEFORE implementing: create the gate file, run the gate command, save the literal output to
   `output/osskel_r2_step1_red.txt` (expect failures — module raises nothing / returns None).
2. After implementing: re-run the same command, save to `output/osskel_r2_step1_green.txt`.
3. Structural harnesses must both stay PASS (they pin the engine constants and the skeleton structure):
   `python3 tools/geos_os_skel_verify.py` (85 legs, exit 0) and `python3 tools/geos_spine_verify.py` (exit 0).
4. **DO NOT COMMIT.** Leave the changes in the working tree. The orchestrator re-runs the gate, checks
   `git status --short` for out-of-scope writes, and commits with the RED/GREEN receipts.
5. Report at the end: exact files changed, the literal gate tail, the two harness tails, and anything you
   could NOT do (state it, never approximate it).
