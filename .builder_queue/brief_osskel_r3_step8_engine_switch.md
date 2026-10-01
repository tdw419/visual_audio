# BRIEF — OS-SKEL-R3 step 8: wire `AddressSpace.switch` to the REAL engine

**Round:** OS-SKEL-R3 (new round; the R2 round closed 7/7 at `637f6e7`, receipt `systems/RECEIPT_OS_SKELETON.md`).
**Target id:** OS-SKEL step 8 (`systems/GLYPH_OS_SKELETON.md` § 6 item 8, lines 175–176; carried forward by the R2
receipt § 5). Roadmap row `OS-SKEL-R3-S8` (promoted this tick).
**Read first (the spec):** `systems/GLYPH_OS_SKELETON.md` § 6 item 8 + § 4 invariant **I4** ("switching a space writes
ONE word (`PAGE_TABLE_ADDR`)"); `systems/RECEIPT_OS_SKELETON.md` § 4 ("No kernel wiring… targets an injected sink,
never `PAGE_TABLE_ADDR` in the engine") and § 5 (this step).

## Deliverable — exactly TWO new files

1. `tools/geos_engine_sink.py` — an **engine-backed MMIO sink**, i.e. the wiring.
2. `tests/test_osskel_engine_switch.py` — the round's dedicated gate.

**Create no other file and modify NO existing file.** In particular: do **not** touch `tools/glyph_isa_v2.py`,
`tools/geos_aspace.py`, `tools/geos_os_skel_verify.py`, any other `tools/geos_*.py`, the WGSL shader,
`tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any existing test, or any roadmap/receipt doc.
Do **not** run `git add` / `git commit` — the orchestrator commits.

## Hard stop (report instead of doing it)

The expected shape is **zero engine lines**: GH-17 already reads `PAGE_TABLE_ADDR` on every USER LD/ST. If the wiring
cannot be made real — the engine must observably *translate differently* because of a `switch()` — **without editing
`tools/glyph_isa_v2.py` or `tools/geos_aspace.py`, STOP and report** what you measured. A change to either file is an
interface question for the lane, not a builder call.

## Facts already measured by the orchestrator (do not re-derive; verify only if you rely on them)

- `tools/glyph_isa_v2.py:40` `BOX_MMIO_BASE = 0x8000`; `:60` `PAGE_TABLE_ADDR = BOX_MMIO_BASE + 0x4C` (0x814C);
  `:61` `PAGE_TABLE_WORD = PAGE_TABLE_ADDR >> 2` = **8211**.
- The engine reads the live word at `tools/glyph_isa_v2.py:626` (LD) and `:696` (ST):
  `pt_base = self.memory[PAGE_TABLE_ADDR >> 2]`; `pt_base != 0` ⇒ translations on, `vpn = (vaddr >> 8) & 0xFF`,
  `pte_idx = pt_base + vpn`, RAM PTE first and the image PTE only as fallback (GH-25 RCA). Supervisor loads from the
  BOX-MMIO word window (`(BOX_MMIO_BASE >> 2) .. +256` words) are exempt from translation.
- `GlyphCPUv2.__init__(opcode_map, cols_instrs, fs_pix_enabled=False)` defaults `self.memory = [0] * 1024`
  (`:417-422`) — **too small to hold word 8211**, so the gate must build an engine whose RAM includes the MMIO word
  window, or the wiring must refuse loudly. How other tests size it: read `tests/test_gh17_paging.py` and
  `tests/test_gh25_hilbert_paging.py` and model your engine construction on them.
- `tools/geos_aspace.py:288` is the only write path: `_mmio_sink(PAGE_TABLE_ADDR, self.satp_word)`; the hook
  `set_mmio_sink()/get_mmio_sink()/MmioSink` is the **one** injection idiom (decided at R2 step 2, deliberately not in
  `__all__`). `AddressSpace.switch()` raises `RuntimeError` when no sink is bound.

## Locked design (do not re-litigate)

- `EngineMmioSink` is a callable `(addr: int, word: int) -> None` bound **through the existing hook**
  (`set_mmio_sink(EngineMmioSink(engine))`) — no second injection idiom, no new module-level global in `geos_aspace`.
- The store is `engine.memory[addr >> 2] = word`, i.e. the engine's own word-array MMIO path — the same array the
  engine reads at `:626`/`:696`. It must be the real array, not a copy/shadow.
- Validation before any write, loud and named (never a silent no-op):
  - `addr` must be an `int` (reject `bool`) inside the BOX-MMIO word window `[BOX_MMIO_BASE, BOX_MMIO_BASE + 0x400)`;
    otherwise raise `ValueError` naming the address;
  - `word` must be an `int` (reject `bool`) in `[0, 0xFFFFFFFF]`; otherwise raise `ValueError`;
  - if the engine's memory cannot hold `addr >> 2` (`len(engine.memory) <= addr >> 2`), raise (`ValueError` or
    `RuntimeError`, your choice — name it in the docstring) rather than resizing or ignoring.
- Module-level helpers `bind_engine(engine)` (returns the sink after installing it) and `unbind_engine()` (restores
  `set_mmio_sink(None)`), so the gate's teardown can never leak the sink into another test.
- A minimal `writes` counter (`sink.writes`, `sink.last`) is allowed for evidence; nothing else.

## Gate command (this is the gate; every leg must pass)

```
python3 -m pytest tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q --tb=short
python3 tools/geos_os_skel_verify.py            # exit 0, 85 legs + self-test
```

Legs to implement (all in the new file, except L5's dependencies):

| leg | what it proves |
|---|---|
| **L1 (falsifier)** | With a real engine bound: `AddressSpace.switch()` writes **exactly one** word, `engine.memory[PAGE_TABLE_ADDR >> 2] == aspace.satp_word`, **and the engine's own translation path is live** — drive the engine's `step()`/LD path (USER mode) at a vaddr whose `vpn` has a RAM PTE at `pt_base + vpn` pointing at a word that differs from the flat RAM word at that address, and assert the engine returns the PTE-mapped word. A test that only reads back the stored number does **not** satisfy L1. |
| **L2 (switch is a switch)** | Two `AddressSpace` objects with different `pt_base_word` (e.g. two disjoint PTE regions in the same engine RAM): switch A, LD the same vaddr → word_A; switch B, LD the same vaddr → word_B ≠ word_A (no stale `pt_base`). |
| **L3 (loud negatives)** | (a) no sink bound → `RuntimeError` from `switch()` and the engine word is still 0 (paging disabled, engine untouched); (b) `sink(BOX_MMIO_BASE + 0x400, 1)` and `sink(0x1234, 1)` → `ValueError` naming the address, engine unchanged; (c) a too-small engine → refusal, engine unchanged; (d) `word` out of range / `True` → `ValueError`. |
| **L4 (non-vacuity)** | Out-of-tree probes (copies under `/tmp`, never the live files): neuter the store in `EngineMmioSink.__call__` → L1 RED; neuter the window check → L3(b) RED. Restore the live modules and re-hash them byte-identical (`md5sum`), and say so in the module docstring. A gate whose assertions survive a neutered mechanism is not a gate. |
| **L5 (no regression)** | `tests/test_osskel_aspace_switch.py` stays green (its dict-sink idiom must keep working), and `python3 tools/geos_os_skel_verify.py` exits 0. Report the arc-regression run you did (see below); the orchestrator re-runs it. |

## Evidence you must report back (the orchestrator verifies independently)

1. `python3 -m pytest tests/test_osskel_engine_switch.py -v` output showing every leg **PASSED** (not skipped), and the
   RED-before-GREEN story: what you ran first that failed and why (module absent counts as RED — record the exit code).
2. The two L4 probe outputs (neutered copy RED, live md5 unchanged).
3. `git status --short` — it must show **only** the two new files.
4. Anything you could not verify, stated plainly. Do not claim a green you did not run.
