# RECEIPT — OS-SKEL-R2: OS-level skeleton subsystems, populated and gated

**Round:** OS-SKEL-R2 (Phase 3 population of `tools/geos_aspace.py`, `tools/geos_caps.py`,
`tools/geos_proctab.py`, `tools/geos_devtab.py`, plus the cross-module seam `tools/geos_spawn.py`).
**Spec:** `systems/GLYPH_OS_SKELETON.md` § 6 (roadmap items 1–7), plan + progress in
`.builder_queue/brief_osskel_r2_phase3.md` and `.builder_queue/brief_osskel_r2_step7_spawn.md`.
**Lane supply:** OS-SKEL-R2 is a lane-supply item from `.builder_queue/RULING_lane_supply_20260912.md`
(the successor to SPINE-R1, `systems/RECEIPT_SPINE_R1.md`) — **not** a roadmap row, and no roadmap
done-state is claimed here.
**Executed by:** builder cron `af3e62239ce2` — orchestrator judgment/verification, Antigravity CLI for
token-heavy implementation, one step per run.

## 1. What landed

| Step | Body populated | Gate module | Gate | Commit |
|---|---|---|---|---|
| 1 | `AddressSpace.map` / `unmap` | `tests/test_osskel_aspace_map.py` | 5/5 | `e4cfa2c` |
| 2 | `AddressSpace.switch` (one word → injected MMIO sink) | `tests/test_osskel_aspace_switch.py` | 5/5 | `f8e5d79` |
| 3 | `AddressSpace.release` + `AsidAllocator` wiring | `tests/test_osskel_aspace_release.py` | 6/6 | `c9bc790` |
| 4 | `CapTable.grant` / `revoke` / `held` | `tests/test_osskel_caps_table.py` | 7/7 | `5de299c` |
| 5 | `Proctab.admit` / `mark_exited` / `reap` | `tests/test_osskel_proctab_lifecycle.py` | 7/7 | `8b48319` |
| 6 | `Devtab.register_device` + `grant_words` identity | `tests/test_osskel_devtab_register.py` | 7/7 | `db6a973` |
| 7 | Cross-module `spawn()` (+ `BoxAllocator`) | `tests/test_osskel_spawn_integration.py` | 8/8 | `637f6e7` |

Every step: RED before GREEN (test failures, never a collection error), both harnesses PASS
(`python3 tools/geos_os_skel_verify.py` 85 legs + failure-path self-test,
`python3 tools/geos_spine_verify.py`), and the arc regression
(`tests/test_gh*.py tests/test_bk*.py tests/test_spine_r1_*.py tests/test_osskel_*.py`) exit 0.
Arc growth per step: 23 → 30 → 37 → 408 collected (step 6, +7) → **416 collected / 415 passed /
1 skipped / 0 failed** (step 7, +8 = exactly that step's gate).

Interpreter note (honest): every gate was run on `/usr/bin/python3.12` **and** on the
Hermes-venv `python3` (3.11.15, which has `pytest`). The bare `python3.11` on PATH has no `pytest`
installed, so a "py3.11 second interpreter" leg is **not** claimable for step 7 — earlier steps'
"py3.11" phrasing meant the venv interpreter, and that ambiguity is corrected here.

## 2. The judgment calls worth recording (all recorded in the step briefs at the time)

1. **Injection, not invention.** Signatures/fields were LOCKED, so every cross-module dependency that
   a locked signature could not carry is bound at **module level in the owning module**, next to its
   concern, deliberately outside `__all__`: `set_mmio_sink`/`get_mmio_sink` (step 2, `geos_aspace`),
   `set_asid_allocator`/`get_asid_allocator` (step 3, `geos_aspace`), `set_granter_mask`/`get_granter_mask`
   (step 4, `geos_caps`). Three concerns, one idiom — no step was allowed to add a second convention,
   and step 7 consumed the existing hooks rather than adding a fourth.
2. **Refuse, never assume.** An unbound hook raises (`RuntimeError`) instead of silently doing nothing:
   `switch()` with no sink, `release()` with no allocator (leaving `refcount` at 1),
   `grant()` with no granter, `admit`/`reap` with no allocator, `spawn()` with either hook unbound.
3. **Root is explicit, not a wildcard** (caps I5): `CAP_ROOT` does not imply any other bit, and
   revoking it requires `force=True`. The no-amplification rule is enforced by the table, not by callers.
4. **Table identity = the key `name` (instance), not `dev_id` (model).** The first step-6 brief asked for
   `dev_id` policing; the round's own structural harness refuted it (leg 7 registers several same-model
   devices under distinct names), so the gate's L2 is now an explicit **anti-over-reach** leg. This is
   recorded as an orchestrator spec error caught by the harness, not a builder bug.
5. **`Proctab.admit` is the oracle for pid prediction.** `admit` itself calls `pids.alloc()` and requires
   the result to equal `desc.pid`, so `spawn()` must predict the lowest-free pid rather than pre-allocate it.
   The prediction (`_lowest_free`) is documented as a prediction whose independent oracle is `admit` —
   drift is a loud `ValueError`, never silent divergence.
6. **Two seams are named, not papered over** (module docstring of `tools/geos_spawn.py`):
   (a) `CapTable` has no create-row API, so `geos_spawn` writes `captab.grants[pid]` once — the only place
   outside `geos_caps` that does (a `CapTable.create(pid)` would be the fix; interface locked this round);
   (b) `reap` retires the asid through the allocator, so releasing a retired `AddressSpace` again is a
   double free — refused loudly by `AsidAllocator.free`, and asserted as such (step 7 L5).

## 3. Falsification (beyond the gates) — every probe is an out-of-tree module copy

| Step | Mutation applied to a `/tmp` copy | Reddened legs |
|---|---|---|
| 3 | neuter the asid free in `release()` | 4 legs |
| 4 | neuter the amplification check | L1, L2 |
| 4 | neuter the `CAP_ROOT` force check | L3 |
| 5 | neuter the `ZOMBIE` check in `reap` | L3 |
| 5 | neuter the asid free in `reap` | L1, L2, L4, L6 |
| 6 | neuter the duplicate-name guard | L1, L2, L6 |
| 7 | flip the `CAP_DEV_MMIO` and `CAP_SPAWN` guards to `if False:` | L2 (dev_mmio), L4 (spawn) |

In every case the live module was restored and re-hashed byte-identical (step 5 `dd122fab…`,
step 6 `2d4645fb…`, step 7 `fc8e0c4a…`). Step 7's probe is committed as runnable evidence:
`output/osskel_r2_step7_probe.py` + `.txt` — LIVE refuses with `binding a device driver requires
CAP_DEV_MMIO` and mutates nothing (`procs=0 asids=[] boxes=[] bindings=0`); the neutered copy spawns
`pid=0 box=0` and creates a binding, i.e. **the guards are load-bearing**.
Structural harness self-test: both harnesses ship a live failure-path check ("a RED is reachable").

## 4. What this receipt does NOT claim

- **No kernel wiring.** Nothing here writes a real page table or a real box word; `AddressSpace.switch`
  targets an injected sink, never `PAGE_TABLE_ADDR` in the engine.
- **No engine integration.** `tools/glyph_isa_v2.py`, the WGSL shader, and `glyph_dispatch/**` are
  untouched (the harness's engine cross-check reads constants *out of* the engine; nothing wrote to it).
- **No scheduler.** `ready_set()` is populated but nothing consumes it (GH-16 territory).
- **No bare metal, no driver ecosystem, no filesystem permissions/ownership, no production network
  stack, no SMP semantics** — the five gaps § 8 of the skeleton names as each their own project.
- **Leg-6g harness amendment not yet lane-reviewed.** `geos_os_skel_verify.py` leg 6g assumed a
  stub-era world (admit/reap an `asid=0` with no allocator ever bound); step 5 made it bind an
  `AsidAllocator` and unbind after the check. Assertions and leg count unchanged (85 + self-test),
  necessity is captured in `output/osskel_r2_step5_harness_amendment_necessity.txt`. Flagged for review,
  not silently absorbed. (The step-1 leg-4 amendment was independently re-verified and **closed**.)
- No roadmap row is marked ✅ by this receipt.

## 5. Next

- **Step 8 (own round, own gate):** wire `AddressSpace.switch` to the real engine via `PAGE_TABLE_ADDR`
  and move ownership of a space's lifetime off `reap` — the seam step 7 named.
- Lane supply is otherwise exhausted for OSS rounds until a new ruling (.builder_queue/RULING_*.md).
