# RECEIPT — OS-SKEL-R3 step 8: `AddressSpace.switch` wired to the real engine

Row: **OS-SKEL-R3-S8** in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (promoted this tick, then closed with this receipt).
Spec: `systems/GLYPH_OS_SKELETON.md` § 6 item 8 (lines 175–176) + invariant **I4** (switching writes ONE word,
`PAGE_TABLE_ADDR`); carried forward from `systems/RECEIPT_OS_SKELETON.md` § 4/§ 5.
Tick: builder cron `af3e62239ce2`, 2026-09-12 (the run that found HEAD moved to `f48ffa9` and re-verified the two
ruled defects already closed).
Brief: `.builder_queue/brief_osskel_r3_step8_engine_switch.md` (written by the orchestrator; the design was locked
there before delegating). Implementation delegated to `agy` (`output/agy/agy_impl_20260912_201958.log`); gate runs,
probes and this receipt by the orchestrator.

## 1. What landed (two new files, zero modified files)

| file | role |
|---|---|
| `tools/geos_engine_sink.py` | **the wiring.** `EngineMmioSink(engine)` is a `(addr, word) -> None` callable that validates (int, not `bool`; `addr` inside `[BOX_MMIO_BASE, BOX_MMIO_BASE + 0x400)`; `word` in `[0, 0xFFFFFFFF]`; engine RAM large enough for `addr >> 2`) and then performs the engine's own word-array MMIO store `engine.memory[addr >> 2] = word`. Bound through the **existing** hook `geos_aspace.set_mmio_sink` via `bind_engine(engine)` / `unbind_engine()` — no second injection idiom, `tools/geos_aspace.py` untouched. Tracks `writes` / `last` for evidence. |
| `tests/test_osskel_engine_switch.py` | the round's dedicated gate: 5 legs (L1 falsifier, L2 switch-is-a-switch, L3 loud negatives, L4 non-vacuity probes, L5 aspace-switch compatibility), 351 lines. |

**Zero engine lines.** `tools/glyph_isa_v2.py` and `tools/geos_aspace.py` are unmodified (`git status --short` showed
no tracked modifications; the brief's hard-stop clause was never reached) — GH-17 already reads the live word at
`tools/glyph_isa_v2.py:626` (LD) / `:696` (ST), so the round needed a channel, not an engine change.

## 2. Gate evidence (orchestrator-run, not agy's claim)

- Gate + compatibility: `python3 -m pytest tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q --tb=short`
  → **10 passed, exit 0** → `output/osskel_r3_step8_gate_green.txt`.
  (The scoped paging set — the same command plus `test_gh17_paging.py` + `test_gh25_hilbert_paging.py` — is 22 passed, exit 0.)
- Structural harness: `python3 tools/geos_os_skel_verify.py` → `OS SKELETON VERIFY: PASS` (85 legs + live self-test).
- Arc regression, `/usr/bin/python3` (py3.12, the interpreter with `mcp`):
  `pytest tests/test_gh*.py tests/test_bk*.py tests/test_spine_r1_*.py tests/test_osskel_*.py -q`
  → **~410 passed / 1 skipped / 0 failed, exit 0** → `output/osskel_r3_step8_arc_py312.txt`.
- **L1 is the load-bearing leg**: with the sink bound, `switch()` writes exactly one word (`sink.last == (PAGE_TABLE_ADDR, satp)`,
  `engine.memory[PAGE_TABLE_ADDR >> 2] == satp`) **and** the engine's own USER-mode LD path returns the PTE-mapped word —
  the same program with the word still 0 returns the flat RAM word, and after the switch it returns a *different* word
  (`tests/test_osskel_engine_switch.py:116` vs `:153-154`). A stored number alone would not pass.

## 3. Falsification (out-of-tree, no live-file mutation)

`output/osskel_r3_step8_probe.py` + `.txt` (run by the orchestrator, monkeypatching the class method in memory —
the live files were never written to):

| probe | mutation | result |
|---|---|---|
| phase 1 | sink `__call__` keeps the counters but **drops the store** | L1 RED — `AssertionError` at `tests/test_osskel_engine_switch.py:139` (`assert cpu.memory[PAGE_TABLE_WORD] == expected_satp`), i.e. the gate notices a switch that wrote nothing |
| phase 2 | sink `__call__` **drops the validation**, stores anyway | L3 RED — `Failed: DID NOT RAISE ValueError` at `tests/test_osskel_engine_switch.py:249` (the out-of-window address is refused by the check, not by luck) |

Live md5s after the probes: `tools/geos_engine_sink.py` `13c5c6ae7ffa7ecb6529caf3cc14ea13`,
`tests/test_osskel_engine_switch.py` `859dcbba1c255c549c0d83400b19f95c` (both unchanged by the probes).

## 4. What this receipt does NOT claim

- **No in-OS consumer.** The gate drives the engine's translation with a synthetic program and a single LD step. Nothing
  in the skeleton *schedules* or *uses* a switched space yet (`ready_set()` still has no consumer — GH-16 territory),
  so this proves the wiring is real, not that an OS boots on it.
- **Not a kernel store path.** The sink writes the engine's word array directly (the array the engine itself reads at
  `:626`/`:696`). It does not execute a kernel `ST` to the MMIO word through the interpreter; the equivalence of the two
  is GH-17's own contract, not re-proved here.
- **The R2 receipt's second clause is NOT done.** `systems/RECEIPT_OS_SKELETON.md` § 5 also asks to "move ownership of a
  space's lifetime off `reap`". That is an interface question (`reap` currently retires the asid through the allocator,
  so a later `release()` on a retired space double-frees — R2 receipt § 2 seam (b)). Filed, not silently absorbed:
  `.builder_queue/REPAIR_PENDING_oskel_step9_space_lifetime_ownership.md`.
- **Leg-6g harness amendment still lane-unreviewed** (carried forward from R2 § 4, unchanged by this round).
- No other roadmap row is marked ✅ by this receipt.

## 5. Notes for the next run

- `python3` in this session is the Hermes runtime CPython 3.11 and **cannot** import `mcp.server.fastmcp`, so the glob
  arc aborts at collection on `tests/test_gh26_glass_box.py` (pre-existing: it pulls
  `tools/geos_observation_server.py:28`). Arc evidence must be produced under `/usr/bin/python3`. This is the same
  interpreter constraint OBS-1 recorded.
- Next candidate units, in the loop's own recorded order: (1) the lifetime-ownership seam above (needs an interface
  decision — a `CapTable.create(pid)`-class change is the natural fix, again an interface question); (2) rows the lane
  reserves to Jericho (GL-6/GL-7 publication, "declare the lane complete", Tier C). The self-hosting roadmap and the
  BK backlog are otherwise exhausted.
