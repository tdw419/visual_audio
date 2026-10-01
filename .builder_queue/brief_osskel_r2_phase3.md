# BRIEF — OS-SKEL-R2 (Phase 3): populate the OS-level skeleton subsystems

**Skeleton (read FIRST — it is the spec):** `systems/GLYPH_OS_SKELETON.md` @ `b4ff4d6`-series
**Modules to populate:** `tools/geos_aspace.py`, `tools/geos_caps.py`, `tools/geos_proctab.py`, `tools/geos_devtab.py`
**Interfaces are LOCKED.** Do not change signatures, dataclass fields, state names, cap bit values, or constants —
if one looks wrong, STOP and report; that is a skeleton-sign-off change, not a builder call.
**Structural gate (must stay green throughout):** `python3 tools/geos_os_skel_verify.py` → exit 0 (85 legs)

## Deliverable — SEVEN steps, one per run, in this order

| Step | Populate | New gate | Gate clause (concrete) |
|---|---|---|---|
| 1 | `AddressSpace.map` / `unmap` | `tests/test_osskel_aspace_map.py` | map then read back the PTE; remap of a live entry WITHOUT unmap raises; vpn ≥ 256 raises; returns the previous entry on legitimate remap-after-unmap |
| 2 | `AddressSpace.switch` | `tests/test_osskel_aspace_switch.py` | driven into a fake MMIO sink: exactly ONE word written, to `PAGE_TABLE_ADDR`, equal to `satp_word`; switching twice writes twice with the same word (idempotent value) |
| 3 | `AddressSpace.release` + `AsidAllocator` wiring | `tests/test_osskel_aspace_release.py` | refcount 2→1→0; asid freed only at 0; release on a 0-refcount space raises; the freed asid is reused before a higher one |
| 4 | `CapTable.grant/revoke/held` | `tests/test_osskel_caps_table.py` | granting a cap the caller does not hold raises (no amplification); revoking `CAP_ROOT` without `force=True` raises; `held()` on an unknown pid raises `KeyError`; grant→held round-trips a mask |
| 5 | `Proctab.admit` / `mark_exited` / `reap` | `tests/test_osskel_proctab_lifecycle.py` | spawn→run→exit(42)→reap returns 42; pid AND asid are both reusable only after reap; `reap` on a non-zombie raises; two children, reap both |
| 6 | `Devtab.register_device` + `grant_words` | `tests/test_osskel_devtab_register.py` | duplicate device name raises; `grant_words` returns the descriptor's exact `(lo,hi)`; out-of-aperture descriptor is rejected at construction (not clamped) |
| 7 | Cross-module `spawn()` integration | `tests/test_osskel_spawn_integration.py` | one call allocates pid+asid+box, sets caps, and (when `CAP_DEV_MMIO` is held) binds a driver; without that cap the bind is refused with the missing cap named |

## Progress (orchestrator — one step per run)

| Step | Status | Evidence |
|---|---|---|
| 1 `AddressSpace.map`/`unmap` | ✅ done — commit `e4cfa2c` | gate `tests/test_osskel_aspace_map.py` 5/5 (RED 5 FAILED → GREEN exit 0 on py3.12 and py3.11), both skeleton harnesses exit 0, arc (`test_gh*`+`test_bk*`+`test_spine_r1_*`) exit 0 |
| 2 `AddressSpace.switch` | ✅ done — commit `f8e5d79` | gate `tests/test_osskel_aspace_switch.py` 5/5 (RED 5 FAILED → GREEN exit 0 on py3.12 and py3.11), both skeleton harnesses exit 0, arc (`test_gh*`+`test_bk*`+`test_spine_r1_*`) exit 0 |
| 3 `AddressSpace.release` + `AsidAllocator` wiring | ✅ done — commit `c9bc790` | gate `tests/test_osskel_aspace_release.py` 6/6 (RED 6 FAILED → GREEN exit 0 on py3.12; L1 refcount descent, L2 lowest-free asid reuse, L3 below-zero raise, L4 loud refusal with no allocator bound, L5 allocator `KeyError` propagated, L6 binding hygiene), both skeleton harnesses exit 0, arc (`test_gh*`+`test_bk*`+`test_spine_r1_*`+`test_osskel_*`) exit 0; non-vacuity probe: neutered free → 4 legs RED |
| 4 `CapTable.grant`/`revoke`/`held` | ✅ done — commit `5de299c` | gate `tests/test_osskel_caps_table.py` 7/7 (RED 7 FAILED → GREEN exit 0 on py3.12; L1 no-amplification raises + non-mutation, L2 CAP_ROOT is not a wildcard, L3 revoke CAP_ROOT needs `force=True`, L4 unknown pid → `KeyError` on all three, L5 grant→held round-trip + idempotence, L6 unbound granter refuses loudly, L7 binding hygiene + `__all__` untouched), both skeleton harnesses exit 0 (85 legs), steps 1–4 together 23 passed, arc 394 collected / 393 passed / 1 skipped / 0 failed; non-vacuity probes: neutered amplification check → L1+L2 RED, neutered CAP_ROOT force check → L3 RED, module restored byte-identical |
| 5 `Proctab.admit`/`mark_exited`/`reap` | ✅ done — commit `8b48319` | gate `tests/test_osskel_proctab_lifecycle.py` 7/7 (RED 6 failed/1 passed → GREEN exit 0), both skeleton harnesses exit 0 (85 legs + self-test), steps 1–5 together 30 passed, arc 401 collected / 400 passed / 1 skipped / 0 failed; non-vacuity probes: neutered ZOMBIE check → L3 RED, neutered asid free → L1+L2+L4+L6 RED, module restored byte-identical (md5 `dd122fab866101980136fd5a023a07d3`) |
| 6 `Devtab.register_device` + `grant_words` | ✅ done — commit `db6a973` (+ near-escalation doc `d97f6db`) | gate `tests/test_osskel_devtab_register.py` 7/7 (RED 3 failed/4 passed on the stub → GREEN exit 0, junit tests=7 failures=0 errors=0), both skeleton harnesses exit 0 (85 legs + self-test), `tools/geos_devtab.py` smoke exit 0, steps 1–6 together 37 passed, arc (`test_gh*`+`test_bk*`+`test_spine_r1_*`+`test_osskel_*`) 408 collected / 407 passed / 1 skipped / 0 failed exit 0 (delta vs step 5 = +7, exactly this gate); non-vacuity probe: name guard neutered → L1+L2+L6 RED, module restored byte-identical (md5 `2d4645fb25f1bc1b7c9811476a64f0dc`) |
| 7 Cross-module `spawn()` integration | ✅ done — commit `637f6e7` | gate `tests/test_osskel_spawn_integration.py` 8/8 (RED 8 FAILED on the stub module → GREEN exit 0, junit tests=8 failures=0 errors=0 skipped=0), both skeleton harnesses exit 0 (85 legs + self-test), arc 416 collected / 415 passed / 1 skipped / 0 failed exit 0 (delta vs step 6 = +8, exactly this gate); non-vacuity probe (orchestrator-run, out-of-tree copies, committed as `output/osskel_r2_step7_probe.*`): `CAP_DEV_MMIO`+`CAP_SPAWN` guards → `if False:` ⇒ LIVE refuses (`binding a device driver requires CAP_DEV_MMIO`, nothing mutated) while the neutered copy spawns `pid=0 box=0` + binding ⇒ guards load-bearing; live md5 `fc8e0c4a784102641d57551b9ecec057` unchanged. Scope note: `python3.11` on PATH has no `pytest`; the second-interpreter leg ran on the Hermes-venv `python3` (3.11.15). Step-7 brief: `brief_osskel_r2_step7_spawn.md` (locked design: `BoxAllocator`, `spawn()` signature, validate-all-then-mutate ordering, literal `CAP_SPAWN`/`CAP_DEV_MMIO` in refusal messages, `_lowest_free` prediction, `meta["aspace"]`/`meta["binding"]`) |

**Sink mechanism decided at step 2 (recorded so step 6/7 reuse it, not a new one):** fields are LOCKED, so the
MMIO write path is injected at module level — `MmioSink`/`set_mmio_sink()`/`get_mmio_sink()` in
`tools/geos_aspace.py`, deliberately NOT in `__all__`. `switch()` refuses (`RuntimeError`) when no sink is
bound rather than returning a word it did not write. Step 6 (`grant_words` into a fake engine sink) and step 7
(`spawn`) must use this same hook — do not add a second injection idiom.

**Allocator binding decided at step 3 (same idiom, second concern only):** `AddressSpace.release()` keeps its
zero-argument signature (fields and signatures are LOCKED), so the `AsidAllocator` its teardown frees into is
bound at module level too — `set_asid_allocator()` / `get_asid_allocator()` in `tools/geos_aspace.py`, next to
the sink helpers and deliberately NOT in `__all__`. `release()` frees the asid exactly once at the 1 → 0
transition; with no allocator bound it refuses (`RuntimeError`) and leaves `refcount` at 1 rather than reporting
a release that freed nothing. Steps 5 (`reap`) and 7 (`spawn`) must use this hook, not a third convention.

**Granter binding decided at step 4 (same idiom, third concern only):** the no-amplification rule needs a
"caller", and `CapTable` has exactly one field (`grants`) with `grant(pid, mask)` frozen — so the granting
authority's own mask is bound at module level too: `set_granter_mask()` / `get_granter_mask()` in
`tools/geos_caps.py`, deliberately NOT in `__all__`. `grant()` raises `KeyError` on an unknown pid, `RuntimeError`
when no granter is bound (refusal, never a skipped check), and `PermissionError` naming the deficit caps
(`cap_names`, I2) when the granter lacks a requested bit, mutating nothing; `CAP_ROOT` is not a wildcard (I1).
`revoke()` requires `force=True` for `CAP_ROOT` (I5) and deliberately applies no granter check. Step 7 (`spawn`)
must use this hook, not a fourth convention.

**Lifecycle mechanism decided at step 5 (same allocator hook as step 3 — no new idiom):** `admit` reserves both
identities and `reap` releases both, through `PidAllocator` (in-table field) and `get_asid_allocator()`.
`admit` validates first and mutates last: the descriptor must be `NEW`, the pid must not be live or an unreaped
descriptor, and the pid the table hands out must be exactly `desc.pid` (I1) or the reservation is rolled back and
`ValueError` is raised. For the asid: if the descriptor's asid is not yet live in the bound allocator, `admit`
allocates and requires the allocator to hand back exactly that asid — otherwise it frees it and refuses (I5).
So after any admitted process, `desc.asid ∈ allocator.live()`, which is what makes `reap` able to release it.
With no allocator bound, `admit` and `reap` both refuse loudly (`RuntimeError`) and mutate nothing. `reap` is
atomic: unknown pid → `KeyError`; a non-`ZOMBIE` process → `InvalidTransition` (**explicitly checked**, because
`READY → DEAD` is a legal table edge — a bare `transition(pid, DEAD)` would reap a pre-run process); no allocator
→ `RuntimeError`; then both frees are pre-flighted before `ZOMBIE → DEAD` + `pids.free(pid)` +
`allocator.free(asid)`, so no half-release is reachable. The descriptor stays in `Proctab.procs` in state `DEAD`
(the harness asserts it) and pid reuse flows through `PidAllocator` + `admit`'s DEAD-entry rule. Step 6
(`Devtab.grant_words`) and step 7 (`spawn`) must reuse this hook and this admission rule — a spawn that hands
`admit` an asid nobody allocated is now a loud refusal, not a silent default.

**Table identity decided at step 6 (design ruling by the orchestrator, after a first attempt
over-reached):** a row is identified by its key `name` — INSTANCE identity — and `register_device` refuses
a duplicate name with `DeviceConflict`, mutating nothing. `dev_id` is a MODEL id (`vendor<<16|class`) that
a driver MATCHES on (I3): two devices of the same model at different windows are legitimate and both must
register. The first revision of `brief_osskel_r2_step6_devtab.md` asked for `dev_id` policing; that was an
orchestrator spec error and it was caught by the round's own hard constraint — `tools/geos_os_skel_verify.py`
leg 7 registers several same-model devices under distinct names, so the over-strict version made the
structural harness exit 1 (and the gate's L2/L3/L5 red). The amendment is recorded in the brief and the
gate's L2 is now the explicit anti-over-reach leg. Registration does not police windows either; `bind`
does (I1/I2, live, unchanged). Step 7 (`spawn`) therefore does NOT need a device-identity check on top of
`register_device` — a spawn that binds a driver gets the table's name discipline for free.

**Harness amendment needing lane review (step 5):** `tools/geos_os_skel_verify.py` leg 6g admitted
`asid=0` and reaped it with **no allocator ever bound** — a stub-era assumption (the same class as the step-1
leg-4 amendment). It now binds an `AsidAllocator`, admits the asid that allocator handed out, and unbinds after
the reap check. Assertions and leg count are unchanged (85 legs + the failure-path self-test, exit 0); the
amendment is **necessary**, not cosmetic: with the amendment removed, the populated module makes the harness die
at `admit` (`RuntimeError: no asid allocator bound` — captured in
`output/osskel_r2_step5_harness_amendment_necessity.txt`). Flag if that reading is wrong.

**Orchestrator amendment needing lane review (step 1):** `tools/geos_os_skel_verify.py` leg 4
asserted *stub-body behaviour* on the space its own preceding probe had just populated
(`asp.unmap(1) is None` held only while `map()` was a stub), so populating step 1 made a
structural leg red by construction. It now checks the **declared return annotation** plus the
value on a never-populated space. Leg count unchanged (85); non-vacuity proven out-of-tree
(module copy with `map` annotated `"int | None"` → harness exit 1). Flag if that reading of
leg 4 is wrong — the rest of leg 4 and every guard/pure-core leg are untouched.

**Leg-4 review CLOSED (2026-09-12, orchestrator):** re-verified independently, not from the
commit's own claim. Out-of-tree copy of `tools/geos_aspace.py` with `map`'s return annotation
mutated to `"int | None"` → the amended leg-4 predicate evaluates False (leg RED); the real
module → True (leg GREEN). The replacement asserts a declared annotation plus the value on a
never-populated space, so it is non-vacuous and strictly stronger than the stub-behaviour probe
it replaced. No further lane action needed.

## Hard constraints

- **Additive only.** Do NOT touch `tools/glyph_isa_v2.py`, any WGSL, `tools/glyph_gpt/**`,
  `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, `systems/GLYPH_*_SKELETON.md`, `.builder_queue/**`,
  or any existing `tests/*.py`. Step 8 (real-engine wiring) is explicitly OUT of this round.
- **Keep the live guards live.** `Proctab.transition` and `Devtab.bind` already enforce invariants — never
  weaken them to make a new step pass. If a guard blocks a step, the step is wrong.
- **Stdlib only** — `geos_os_skel_verify.py` AST-scans for third-party imports.
- **Do not change the engine constants.** The harness parses `glyph_isa_v2.py` and asserts equality; if the
  skeleton and the engine disagree, report it — do not edit either to force agreement.
- **No MMIO writes to real hardware.** Step 2 must target an injected sink/double. Nothing in this round may
  write an actual box word.

## Receipt discipline (unchanged)

- RED first (run the new gate before implementing, save output), then GREEN.
- Paste the literal tail of both runs in the commit message and the report.
- `python3 tools/geos_os_skel_verify.py` must stay PASS after every step, and
  `python3 tools/geos_spine_verify.py` must stay PASS too.
- Arc regression: `/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_spine_r1_*.py` exit 0.
- One commit per step. Nothing claimed that was not run this tick.

## Definition of done

Steps 1–7 each with RED→GREEN evidence, both skeleton harnesses PASS, arc regression green, and a receipt at
`systems/RECEIPT_OS_SKELETON.md` naming what is **not** claimed (kernel wiring, real MMIO, bare metal).

**CLOSED 2026-09-12 — all seven steps landed; last code commit `637f6e7`; round receipt written at
`systems/RECEIPT_OS_SKELETON.md` (this commit). Step 8 (engine wiring via `PAGE_TABLE_ADDR`, own gate) is a
separate round and was explicitly out of this one. The step-6g harness amendment remains flagged for lane review
in the receipt.**
