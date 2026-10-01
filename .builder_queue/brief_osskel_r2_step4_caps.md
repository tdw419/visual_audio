# BRIEF — OS-SKEL-R2 Phase 3, STEP 4 of 7: `CapTable.grant` / `revoke` / `held`

**Target id:** OS-SKEL-R2 Phase 3 step 4 (`systems/GLYPH_OS_SKELETON.md` § 6 Phase 3 roadmap row 4, line 167;
round brief `.builder_queue/brief_osskel_r2_phase3.md` step-4 gate clause, line 16). Step 1 landed `e4cfa2c`,
step 2 `f8e5d79`, step 3 `c9bc790`.
**Spec is the skeleton — read it FIRST:** `systems/GLYPH_OS_SKELETON.md` lines 74-86 (caps contract table: the
row says *no amplification*), line 167 (step-4 row: "with the no-amplification rule and `force` for CAP_ROOT"),
invariants I1-I5 (`tools/geos_caps.py:19-30`) and the `CapTable` class docstring
(`tools/geos_caps.py:191-206`, which names all three bodies and the no-amplification rule).
**Interfaces are LOCKED** — `grant(self, pid, mask) -> int`, `revoke(self, pid, mask, force: bool = False) -> int`,
`held(self, pid) -> int`, the dataclass field `grants`, the cap bit values, `CAP_NAMES`, `__all__`. If one looks
wrong, STOP and report; that is a skeleton-sign-off change, not a builder call.

**Files in scope (only these may change):**
- `tools/geos_caps.py` — fill the three `CapTable` bodies (currently `:209-219`), add the module-level granter hook
  described below, and update the `PHASE STATUS` docstring line (`:33-35`) to record step 4.
- `tests/test_osskel_caps_table.py` — NEW gate file.
- `output/osskel_r2_step4_red.txt`, `output/osskel_r2_step4_green.txt` — evidence captures.

**Do NOT** touch `tools/geos_aspace.py`, `tools/geos_proctab.py`, `tools/geos_devtab.py`,
`tools/geos_os_skel_verify.py` (the structural harness), `tools/geos_spine_verify.py`, any existing
`tests/*.py` (including `tests/test_osskel_aspace_*.py`), `tools/glyph_isa_v2.py`, WGSL, `tools/glyph_gpt/**`,
`tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, `systems/**`, `.builder_queue/**`.
Stdlib only (`geos_os_skel_verify.py` AST-scans for third-party imports). **DO NOT COMMIT.**

## Mechanism — DECIDED by the orchestrator, do not redesign

### 1. The granter (no-amplification needs a "caller", and the fields are frozen)

`CapTable` has exactly one field (`grants: Dict[int, int]`) and `grant` has exactly two parameters, so the
granter's own mask has to arrive from outside the instance — the same module-level injection idiom this round
already established twice (`set_mmio_sink` in `tools/geos_aspace.py` for step 2,
`set_asid_allocator` for step 3). This is a THIRD concern on the SAME idiom, deliberately not a new convention.

```python
_granter_mask: Optional[int] = None

def set_granter_mask(mask: Optional[int]) -> None:
    """Bind the capability mask the granting authority itself holds; None unbinds."""

def get_granter_mask() -> Optional[int]:
    """Currently bound granter mask (None when unbound) — for tests and teardown."""
```

- `set_granter_mask` raises `TypeError` for anything that is neither `None` nor a non-negative `int`, and
  `ValueError` for a bit that is not in `CAP_NAMES` (same discipline as `cap_mask`).
- `set_granter_mask` / `get_granter_mask` / `_granter_mask` must **NOT** appear in `__all__` (the frozen
  block stays byte-identical apart from nothing — do not touch it at all).

### 2. `grant(pid, mask) -> int` (no amplification — I1/I2)

1. `mask` not a non-negative `int` → `ValueError`.
2. `pid` not a key of `self.grants` → `KeyError(pid)` (the class docstring: "refuse if pid unknown"; same
   discipline as `held`).
3. No granter bound (`get_granter_mask() is None`) → `RuntimeError` naming the condition (e.g.
   `"no granter mask bound: refusing to grant without an amplification check"`). Same refusal-not-a-noop rule
   as `AddressSpace.switch` (no sink → RuntimeError) and `AddressSpace.release` (no allocator → RuntimeError,
   left at refcount 1). Never default to a permissive granter, never silently skip the check.
4. `deficit = mask & ~granter`; `deficit != 0` → raise `PermissionError` whose message is LOUD AND NAMED (I2):
   it must contain the canonical `cap_names(deficit)` strings of the refused bits **and** the requesting pid.
   Nothing is mutated when this raises.
5. Otherwise set `self.grants[pid] |= mask`, return the new mask (i.e. `held(pid)`).

`CAP_ROOT` is NOT a wildcard here either (I1, `cap_implies` docstring `:110-117`): a granter holding
`CAP_ROOT` may grant `CAP_ROOT` only if `CAP_ROOT` is literally in its granter mask.

### 3. `revoke(pid, mask, force=False) -> int` (root is explicit — I5)

1. `mask` not a non-negative `int` → `ValueError`.
2. `pid` not a key of `self.grants` → `KeyError(pid)`.
3. `(mask & CAP_ROOT) and not force` → raise `PermissionError` naming that `force=True` is required
   ("revoking root silently is how a privileged task becomes an unkillable one" — class docstring `:196-200`).
   Nothing is mutated when this raises.
4. Otherwise `self.grants[pid] &= ~mask`, return the new mask. **No granter check on revoke** — removing
   privilege is never amplification, and requiring one would make a revocation of an unbound table impossible.

### 4. `held(pid) -> int`

Unknown pid → `KeyError(pid)` (explicit gate clause). Known pid → its stored mask. No mutation.

## What the gate file must contain (one test per clause; names are the orchestrator's, keep them)

- `test_l1_no_amplification_raises` — granter `CAP_FS_WRITE|CAP_OBSERVE`; `grant(pid, CAP_FS_WRITE)` returns
  the mask and `held(pid)` sees it; `grant(pid, CAP_NET)` raises `PermissionError` and the message contains
  `net` (canonical name) and the pid; the mask is **unchanged** after the refusal (non-mutation).
- `test_l2_cap_root_not_a_wildcard` — granter holds `CAP_ROOT` only; `grant(pid, CAP_FS_WRITE)` still raises
  (root is not a wildcard, I1); granting `CAP_ROOT` from a `CAP_ROOT` granter succeeds.
- `test_l3_revoke_root_requires_force` — `revoke(pid, CAP_ROOT)` raises `PermissionError` and CAP_ROOT stays
  held; `revoke(pid, CAP_ROOT, force=True)` removes it and returns the new mask.
- `test_l4_unknown_pid_raises_keyerror` — `held(999)`, `grant(999, CAP_NET)` and `revoke(999, CAP_NET)` all
  raise `KeyError`.
- `test_l5_grant_held_roundtrip` — grant→`held()` round-trips a multi-bit mask exactly, and a second grant is
  idempotent (same value, no double-count).
- `test_l6_unbound_granter_refuses_loudly` — with no granter bound, `grant` raises `RuntimeError` and the mask
  is unchanged (refusal, not a silent no-op).
- `test_l7_binding_hygiene` — `set_granter_mask("x")` → `TypeError`; `set_granter_mask(-1)` → `ValueError`
  (or `TypeError`); `set_granter_mask(1 << 20)` (unknown bit) → `ValueError`; `set_granter_mask(None)`
  round-trips to `get_granter_mask() is None`; and neither helper name appears in `geos_caps.__all__`.
- Use an autouse fixture that saves/clears/restores the granter binding and asserts it is unbound after each
  test (same shape as `tests/test_osskel_aspace_release.py:14-24`).

## Gate command and evidence (the orchestrator re-runs all of this — your claim is not evidence)

```
/usr/bin/python3 -m pytest tests/test_osskel_caps_table.py -q -p no:warnings
```
RED FIRST: write the gate file, run it against the still-stubbed `CapTable` BEFORE implementing, save the
literal output to `output/osskel_r2_step4_red.txt`. Then implement and run again into
`output/osskel_r2_step4_green.txt`. Every gate clause above must map to a named leg that provably fails before
the change and passes after it.

Also run (do not edit the outputs' meaning into anything else):
```
python3 tools/geos_os_skel_verify.py          # must exit 0, 85 legs
python3 tools/geos_spine_verify.py            # must exit 0
/usr/bin/python3 -m pytest tests/test_osskel_*.py -q -p no:warnings   # steps 1-4 gates together
```

**Report back:** files changed, the literal tail of the RED run and of the GREEN run, the three harness results,
and anything you could NOT verify. If a leg cannot be made to fail on the stubbed body, say so explicitly
instead of weakening it.
