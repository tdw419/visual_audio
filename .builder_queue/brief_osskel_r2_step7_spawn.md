# BRIEF — OS-SKEL-R2 Phase 3, Step 7 of 7: cross-module `spawn()` integration

**Target id:** OS-SKEL-R2 Phase 3 step 7 (`systems/GLYPH_OS_SKELETON.md` § 6 item 7, lines 173–174;
`.builder_queue/brief_osskel_r2_phase3.md` row 7).
**New files (the ONLY files you may create):** `tools/geos_spawn.py`, `tests/test_osskel_spawn_integration.py`.
**Do NOT modify:** `tools/geos_aspace.py`, `tools/geos_caps.py`, `tools/geos_proctab.py`, `tools/geos_devtab.py`,
`tools/geos_os_skel_verify.py`, `tools/geos_spine_verify.py`, `systems/GLYPH_OS_SKELETON.md`, any existing test,
`tools/glyph_isa_v2.py`, any WGSL, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, `.builder_queue/**`.
Those four modules are **LOCKED** (fields, signatures, constants, guards). If one of them seems to need a change to
make this step work, **STOP and report** — that is a skeleton-sign-off call, not a builder call.

## What step 7 is

The four locked modules are populated but nothing has ever *driven them together*. `Devtab.bind` records
`CAP_DEV_MMIO` without checking it (skeleton I5: "recorded, not assumed"), `CapTable` has no create-row API,
`Proctab.admit` demands a **predicted** lowest-free pid, and `AsidAllocator.free` refuses a double free.
`tools/geos_spawn.py` is the integration seam that makes those contracts hold end to end:

> one call allocates pid + asid + box, sets caps, binds a driver when `CAP_DEV_MMIO` is held, and refuses the
> bind with the missing cap **named** when it is not.

## LOCKED design (orchestrator ruling — implement exactly this; do not invent a second idiom)

**Module surface.** `__all__ = ["BoxAllocator", "spawn"]`. Nothing else public. No module-level mutable state in
`geos_spawn.py` — every collaborator is passed in or read from an existing locked hook. Stdlib + the four in-repo
modules only (`from tools.geos_aspace import ...` style, matching the other modules' import style).

**`BoxAllocator`** — a minimal deterministic pool over the engine's three boxes, mirroring `PidAllocator` /
`AsidAllocator` policy exactly (lowest-free, no randomness, no heuristics):

```python
class BoxAllocator:
    def __init__(self, capacity: int = 3) -> None: ...   # capacity <= 0 -> ValueError
    def alloc(self) -> int: ...      # lowest free box; exhausted -> RuntimeError("box space exhausted (3 live)")
    def free(self, box: int) -> None: ...  # not live -> KeyError (double-free is a caller bug)
    def live(self) -> List[int]: ...  # sorted
```

**`spawn` signature (locked):**

```python
def spawn(
    proctab: Proctab,
    captab: CapTable,
    devtab: Devtab,
    box_allocator: BoxAllocator,
    *,
    caps: int = 0,
    pt_base_word: int = 0,
    parent_pid: Optional[int] = None,
    driver: Optional[Driver] = None,
    device: Optional[DeviceDescriptor] = None,
) -> ProcessDescriptor:
```

Two dependencies come from the **existing locked hooks**, never from new state:
`geos_aspace.get_asid_allocator()` and `geos_caps.get_granter_mask()`.

**Ordering — validate ALL, then mutate (a refusal must never leave a trace):**

1. Pre-flight (no mutation): `get_asid_allocator()` is None → `RuntimeError` naming `no asid allocator bound`.
   `get_granter_mask()` is None → `RuntimeError` naming `no granter mask bound`.
2. Pre-flight: granter must itself hold `CAP_SPAWN` (`cap_implies`) → else `PermissionError` whose message
   contains the **literal** token `CAP_SPAWN` (the "who may spawn" rule; `CAP_SPAWN` is GH-7/9's bit and this is
   its first enforcement).
3. Pre-flight: `caps` must be a subset of the granter mask → else `PermissionError` naming the deficit
   (use `cap_names`), **not** a bare mask. (`CapTable.grant` enforces the same rule later; pre-flighting keeps
   the refusal atomic.)
4. Pre-flight, device legs:
   - exactly one of `driver` / `device` given → `ValueError`, nothing mutated;
   - both given and `caps` lacks `CAP_DEV_MMIO` → `PermissionError` whose message contains the **literal**
     token `CAP_DEV_MMIO` (this is I5 becoming enforced — the whole point of the row);
   - both given and `device.name not in devtab.devices` → `ValueError` naming the device (register before bind);
   - both given and `devtab.conflicts(device.window_lo, device.window_hi)` non-empty, or the device already
     bound → `DeviceConflict` (`devtab.bind`'s own guards, pre-flighted so no identity is ever allocated on a
     bind that cannot succeed). Let the real `bind` guard remain the authority — do not re-implement overlap
     logic, call `conflicts()`.
5. Mutate, in this order: `box = box_allocator.alloc()`; `asid = allocator.alloc()`;
   `space = AddressSpace(asid=asid, pt_base_word=pt_base_word)`;
   `desc = ProcessDescriptor(pid=<predicted>, asid=asid, box=box, caps=0, parent_pid=parent_pid,
   meta={"aspace": space})`; `proctab.admit(desc)`; then `captab.grants[desc.pid] = CAP_NONE` followed by
   `desc.caps = captab.grant(desc.pid, caps)`; then, if both `driver` and `device` were given,
   `desc.meta["binding"] = devtab.bind(driver, device, pid=desc.pid)`. Return `desc`.
6. `<predicted>` pid: `Proctab.admit` calls `self.pids.alloc()` itself and requires it to equal `desc.pid` (I1),
   so spawn must NOT pre-allocate the pid. Compute the lowest-free pid with a small private helper
   (`_lowest_free(live, capacity)`) and document in the helper's docstring that `admit` is the independent oracle
   for it — a drift is a loud `ValueError`, never silent divergence. If `admit` raises, roll back exactly what
   was allocated (`asid_allocator.free(asid)`, `box_allocator.free(box)`) and re-raise.
7. Every post-admit operation is guaranteed infallible by the pre-flight in 2–4 (that is why the pre-flight
   exists) — say so in a comment. `desc.caps` must equal `captab.held(desc.pid)` on success.
8. `desc.meta` is the locked extension point for extra kernel state ("LOCKED fields; extra kernel state lives in
   `meta`") — `meta["aspace"]` and `meta["binding"]` are the ruled names.

**Two seams to document in the module docstring, do not paper over:** (a) `CapTable` exposes no create-row API, so
`geos_spawn` is the one place outside `geos_caps` that writes `captab.grants[pid]` — a `CapTable.create(pid)` would
be the fix, but the interface is locked this round; (b) `reap` retires the asid through the allocator, so a retired
`AddressSpace` must not be released again — that double free is refused loudly by `AsidAllocator.free`, and step 8
(engine wiring) is where ownership of the space's lifetime moves.

## Gate — `tests/test_osskel_spawn_integration.py` (one leg per clause, read the failure it asserts)

Fixture: fresh `Proctab`, `CapTable`, `Devtab`, `BoxAllocator`, `AsidAllocator`; `set_asid_allocator(...)`;
`set_granter_mask(CAP_SPAWN | CAP_DEV_MMIO | CAP_OBSERVE)`; one registered device + matching `Driver`.
Teardown unbinds both hooks (`set_asid_allocator(None)`, `set_granter_mask(None)`) so leg order cannot matter.

- **L1 happy path**: spawn with a driver → `desc.state == STATE_READY`, `pid == 0`, `asid == 0`, `box == 0`,
  `captab.held(0) == caps`, `type(desc) is Proctab's ProcessDescriptor`, `desc.meta["aspace"].asid == 0`,
  the asid is live in the allocator, `desc.meta["binding"].device == device.name`, and
  `devtab.grant_words(desc.meta["binding"]) == (device.window_lo, device.window_hi)`.
- **L2 `CAP_DEV_MMIO` missing** (the row's headline clause): same call, `caps=CAP_OBSERVE`, driver+device given →
  `PermissionError` containing `"CAP_DEV_MMIO"`, and **nothing mutated**: `proctab.procs == {}`,
  `proctab.pids.live() == []`, `asid_allocator.live() == []`, `box_allocator.live() == []`,
  `devtab.bindings == []`, `captab.grants == {}`.
- **L3 unbound hooks**: with `set_asid_allocator(None)` → `RuntimeError` naming the missing allocator, nothing
  mutated; with `set_granter_mask(None)` → `RuntimeError` naming the missing granter, nothing mutated.
- **L4 who may spawn / no amplification**: granter holding everything *except* `CAP_SPAWN` → `PermissionError`
  containing `"CAP_SPAWN"`, nothing mutated. Granter holding `CAP_SPAWN` + `CAP_OBSERVE`, spawn requesting
  `CAP_DEV_MMIO` with no driver/device → `PermissionError` naming the deficit cap, nothing mutated.
- **L5 full lifecycle, end to end**: spawn → `transition(pid, RUNNING)` → `mark_exited(pid, 42)` →
  `reap(pid) == 42` → a second spawn gets `pid == 0` **and** `asid == 0` again (lowest-free reuse through the
  step-3/step-5 hooks). Then the named seam: `desc.meta["aspace"].release()` on the retired space raises
  (`KeyError` from `AsidAllocator.free`) and leaves `asid_allocator.live()` unchanged — a loud refusal, not a
  silent double free.
- **L6 box allocation**: three spawns → boxes `0, 1, 2` (lowest-free order); the fourth → `RuntimeError` naming
  box exhaustion **with nothing mutated** (proctab/pids/asids/bindings unchanged); `box_allocator.free(3)` →
  `KeyError`; after `free(1)`, the next spawn gets box `1`.
- **L7 device legs**: driver without device (and device without driver) → `ValueError`, nothing mutated;
  unregistered device → `ValueError` naming it, nothing mutated; a second spawn binding the already-bound device →
  `DeviceConflict` **with no pid/asid/box leak** (the pre-flight runs before mutation); `CAP_DEV_MMIO` held with
  no driver/device → success and `"binding" not in desc.meta`.
- **L8 integration hygiene**: `type(desc) is geos_proctab.ProcessDescriptor` and `desc.state ==
  geos_proctab.STATE_READY` (the state constant is imported from the locked module, not re-declared);
  `geos_spawn.__all__ == ["BoxAllocator", "spawn"]`; the four locked modules' `__all__` are unchanged and none of
  them mentions `geos_spawn` (no back-imports — the seam is one-directional).

## Evidence discipline (RED first, then GREEN) — no commit

1. `RED`: write the gate first, run it against the stub-free tree (module absent → collection error is NOT the RED
   you want; write the module skeleton first so the RED is **test failures**, then implement). Paste the literal
   tail.
2. `GREEN`: `/usr/bin/python3.12 -m pytest tests/test_osskel_spawn_integration.py -q 2>&1 | tail -20` exit 0, and
   the same on `python3.11`.
3. Structural harnesses must stay green: `python3 tools/geos_os_skel_verify.py` (85 legs, exit 0) and
   `python3 tools/geos_spine_verify.py` (exit 0).
4. Arc regression: `/usr/bin/python3.12 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_spine_r1_*.py
   tests/test_osskel_*.py -q 2>&1 | tail -20` → exit 0, with the pytest summary line (collected/passed/skipped/
   failed) pasted. Expect +N over step 6's 408 collected, exactly this gate's leg count.
5. **Non-vacuity probe** (out-of-tree copy, never the live tree): copy `tools/geos_spawn.py` to `/tmp`, neuter the
   `CAP_DEV_MMIO` check → L2 must go RED; neuter the `CAP_SPAWN` check → L4 must go RED; then show the live module
   is byte-identical to its pre-probe `md5sum`.
6. **DO NOT COMMIT.** Report `git status --short` at the end: only `tools/geos_spawn.py` and
   `tests/test_osskel_spawn_integration.py` may be new; nothing else may be modified.

## Hard constraints

- **Additive only** — new files, no edits to the locked modules, the harnesses, or any existing test.
- **Keep the live guards live.** `Proctab.transition`, `Devtab.bind`, `Devtab.grant_words`, `AsidAllocator.free`
  already enforce invariants — never weaken them, and never bypass them (call them).
- **Stdlib only.** No third-party imports anywhere.
- **Do not change engine constants**; if the skeleton and `tools/glyph_isa_v2.py` disagree, report it.
- **No real MMIO / no box writes.** No engine integration, no `AddressSpace.switch` call — step 8 is a separate
  round and is explicitly OUT of scope.
- **Nothing claimed that was not run this tick.** Literal tails only; if a leg is flaky or skipped, say so.
