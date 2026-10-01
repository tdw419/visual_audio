# BRIEF — OS-SKEL-R2 Phase 3, Step 6: `Devtab.register_device` (+ `grant_words` identity)

**Round:** `.builder_queue/brief_osskel_r2_phase3.md` (step 6 of 7)
**File in scope (ONLY):** `/home/jericho/projects/zion/projects/visual_audio/tools/geos_devtab.py`
**Gate (authored by the orchestrator this tick — do NOT edit it):** `tests/test_osskel_devtab_register.py`
**Harness (do NOT edit):** `tools/geos_os_skel_verify.py`

## Gate command (run it yourself; it must end `7 passed`, exit 0)

```
cd /home/jericho/projects/zion/projects/visual_audio
/usr/bin/python3 -m pytest tests/test_osskel_devtab_register.py -q --junitxml=/tmp/step6.xml
```

RED baseline (`output/osskel_r2_step6_gate_RED_20260912.txt`, exit 1) — recorded in two stages:
against the **stub** module `3 failed, 4 passed` (L1, L2-as-then-written, L6 red); against **attempt 1**
(current tree, which over-reached on `dev_id`) `3 failed, 4 passed` with **L2 / L3 / L5** red purely
because same-model devices are refused. Both must go green:
`/usr/bin/python3 -m pytest tests/test_osskel_devtab_register.py -q` → `7 passed`, exit 0.

Also must stay green (run each, report exit codes):
```
/usr/bin/python3 tools/geos_os_skel_verify.py     # exit 0, 85 legs + self-test, count unchanged
/usr/bin/python3 tools/geos_spine_verify.py       # exit 0
/usr/bin/python3 tools/geos_devtab.py             # exit 0 (module smoke must still print and exit 0)
/usr/bin/python3 -m pytest tests/test_osskel_aspace_map.py tests/test_osskel_aspace_switch.py \
    tests/test_osskel_aspace_release.py tests/test_osskel_caps_table.py \
    tests/test_osskel_proctab_lifecycle.py -q     # steps 1-5 must all stay green
```

## What is missing (the whole task)

`Devtab.register_device` today is:

```python
def register_device(self, desc: DeviceDescriptor) -> DeviceDescriptor:
    # TODO(Phase 3): duplicate-name/dev_id rejection.
    self.devices[desc.name] = desc
    return desc
```

A second registration under an existing **name** silently replaces the first device, and a second
registration of the same packed **dev_id** under a new name silently aliases it. Both destroy the
table's ability to say which device is which. Step 6 adds that identity discipline. Nothing else in
the file changes.

## Exact semantics to implement

`register_device(self, desc) -> DeviceDescriptor` — validate first, mutate last; any refusal must
leave `self.devices` and `self.bindings` byte-identical:

1. `desc` is not a `DeviceDescriptor` → `TypeError` (a typo'd argument must not become a table row).
2. `desc.name` already in `self.devices` → raise **`DeviceConflict`**, message naming the device and
   the fact that it is already registered. The existing entry must NOT be replaced (the gate asserts
   `tab.devices[name] is first_registered_descriptor`).
3. Only then insert (`self.devices[desc.name] = desc`) and return `desc`. The insert path must not
   touch `self.bindings` — registration has no window side effects.

**Do NOT police `dev_id` duplicates (orchestrator amendment — the previous revision of this brief
asked for this and it was WRONG).** A first attempt implemented `same dev_id → DeviceConflict`; that
breaks two gates: `tools/geos_os_skel_verify.py` leg 7 registers several same-model devices under
distinct names (the structural harness must stay PASS — it is the round's hard constraint), and the
step-6 gate's L2/L3/L5 do the same. `dev_id` is a MODEL id that a driver MATCHES on (I3); `name` is
the row's INSTANCE identity. Two devices of one model at different windows are legal, both must
register, and stage L2 asserts exactly that (it is the anti-over-reach leg). Registration alone does
not police windows — `bind` does (I1/I2, live).

`DeviceConflict` is `RuntimeError`-derived and already in `__all__`; use it, do not add a new
exception class. The gate accepts `DeviceConflict` or `ValueError` for the refusals, but the brief
asks for `DeviceConflict` so the refusal is unambiguous at the call site.

## Do NOT change

- `grant_words`, `bind`, `probe`, `conflicts`, `window_overlap`, `window_ok`, `device_id`,
  `device_vendor`, `device_class`, `match_score`, all dataclasses and every constant. The live
  guards stay live — never weaken one to make a leg pass.
- The LOCKED signatures/annotations, and `__all__` (the gate asserts its exact set; **no new
  exports**). No module-level hook may be added to this file — the step-2 MMIO sink and the step-3
  asid allocator are the only injection idioms and both live in `tools/geos_aspace.py`.
- **Additive only, this file only.** Do not touch any other file: not the gate, not the harness, not
  `tools/geos_aspace.py`, `tools/geos_caps.py`, `tools/geos_proctab.py`, `systems/**`,
  `.builder_queue/**`, `tests/**`.
- Stdlib only (the harness AST-scans imports).

## Also update

- The module docstring's `PHASE STATUS` block: Phase 3 is now populated for the table identity path
  (`register_device`) while `probe`/`bind`/`grant_words` guards were already live; keep the plain
  statement that the unprivileged driver-task wiring (GH-22) and real MMIO emission are still NOT
  done.
- Drop the `TODO(Phase 3)` comment from the method (it is now implemented), and add a short
  docstring to `register_device` stating the three refusals and the non-mutation guarantee.

## Hard constraints

- **Do NOT commit.** Leave the tree dirty; the orchestrator verifies and commits.
- If any gate leg looks wrong or contradicts the frozen interfaces, STOP and report the conflict
  instead of editing the gate.
- Report: files changed, the literal tail of the gate run (the `N passed` line), the exit code of
  each "must stay green" command, and anything you could not make pass.
