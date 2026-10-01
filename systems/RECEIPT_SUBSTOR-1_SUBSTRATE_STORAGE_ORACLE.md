# RECEIPT — SUBSTOR-1: substrate storage oracle (boot a real guest from substrate-backed memory)

**Row:** `SUBSTOR-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:350`) · **Date:** 2026-09-12 ·
**Seat:** builder orchestrator, cron `af3e62239ce2` · **Implemented by:** `agy` CLI lane from
`.builder_queue/brief_substor_boot_witness.md`; gate, probes and receipt re-run/written by the orchestrator.

## Gate

```
/usr/bin/python3 -m pytest tests/test_substor_boot_witness.py -q
```

- **RED (pre-change):** module absent. Reproduced by holding the three new files out of the tree —
  `ERROR: file or directory not found: tests/test_substor_boot_witness.py`, **exit 4**.
  The module has never existed in any commit (`git log --all -- tests/test_substor_boot_witness.py` → empty).
- **GREEN (post-change):** **5 passed in 3.32s, exit 0** (`-v`: one PASSED per leg L1–L5).
- **RED → GREEN** ran on the same tree, same interpreter, no intervening edit.

## Mechanism (three new files; nothing else touched)

| File | Role |
|---|---|
| `tools/substor_surface_ram.py` (472 l) | `SubstorSurfaceRAM` — the store whose **authority is the pixel surface** (RGB image, GH-8b 2 px/word: lo24 in RGB, hi8 in BLUE). `read_word`/`get_words` **decode from pixels**, never from a host word array. Declared regions per writer, per-word attribution (`writer` + monotonic `write_id`), audit `write_log`, clobber tracking. `commit_surface()` writes the PNG **and** a `.meta.json` sidecar (`write_id`, `writer`, `image_md5`, …) done atomically via `os.replace` — the DEFECT-20 identity discipline applied to guest RAM. `SubstorWitness` = `verify_zero_clobbers` / `verify_attribution` / `verify_writeback_survival`. |
| `tools/substor_boot.py` (270 l) | `SubstorBootDriver` — bounded guest boot on the existing `SpatialRV32ICore`: `load_from_surface()` → `step_chunk()` → `writeback_to_surface()`, so the surface is authoritative at every chunk boundary. |
| `tests/test_substor_boot_witness.py` (273 l) | The gate (L1–L5, below). |

## Legs (all five binding, all green)

- **L1 bounded boot** — reaches the named marker `pc = 0x80000020`, UART byte `'B'`, exactly 8 guest
  instructions in 8 steps; a word **mutated on the surface between chunks** is what the guest's next
  chunk reads (assertion at `tests/test_substor_boot_witness.py:80`), and the guest's store is visible on
  the surface afterwards (`:101`) with the PNG committed to disk (`:102`).
- **L2 substrate witness** — `clobbers == 0`, `attribution_verified is True` with `attributed_words = 10`,
  every word attributed to `loader`/`guest_boot` with `write_id > 0`; **writeback survival**:
  `last_pre_writeback == last_post_writeback` (byte-identical, no dropped writes).
- **L3 negative leg** — rogue second writer → `WITNESS_CLOBBER_DETECTED`; tampered writeback → `WITNESS_DROPPED_WRITE`.
- **L4 non-vacuity** — unattributed word trips `WITNESS_ATTRIBUTION_MISSING`; monkeypatching the attribution
  check to `{"verified": False}` turns L2's contract red; `monkeypatch.undo()` restores a green run.
- **L5 no regression** — `tests/test_spatial_rv32i_cpu.py` invoked as a subprocess: exit 0, >0 passed.

## Orchestrator probe beyond the gate (independent of the test file)

`output/substor_orch_probe.py` → `output/substor_orch_probe.txt` builds its **own** boot through the live
modules and checks the witness discriminates:

```
BASE  check_witness -> status=PASS clobbers=0 attributed_words=10 core_pc=0x80000020 steps=8 uart=bytearray(b'B')
BASE  surface png exists=True
PASS  A rogue-writer clobber: refused loudly -> WITNESS_CLOBBER_DETECTED: 1 clobbered writes outside declared regions
PASS  B dropped/corrupted writeback word: refused loudly -> WITNESS_DROPPED_WRITE: 1 words differed across writeback
PASS  C unattributed word: refused loudly -> WITNESS_ATTRIBUTION_MISSING: Word 0 has unattributed writer
PROBE_VERDICT: ALL DISCRIMINATING
```

## HONEST BOUNDARIES (what this does **not** prove)

1. **The guest is not Linux.** The booted guest is a hand-written **8-instruction RV32IMA program**
   (`lui/addi/lw/addi/sw/lui/addi/sw` at `RAM_BASE = 0x80000000`) that touches RAM and the UART MMIO word.
   The prebuilt 3.4 MB `boot_images/rv32ima_nommu/Image` kernel was **not** booted, and no OS reached a
   shell. The row said "smallest guest first"; this is the smallest guest that satisfies L1 — **not** an
   OS boot, and it must not be cited as one.
2. **Substrate-backed RAM is a 1024-word window, not the guest's 64 MB.** The surface store is
   1024 words on a 64×32 grid; the emulator's own 64 MB device buffer is untouched. The claim
   "guest RAM lives on the substrate" holds **for the exercised window only**.
3. **Surface authority is per chunk boundary, not per cycle.** Between `load_from_surface()` and
   `writeback_to_surface()` the executing copy is the engine's *device* buffer; the **host** never holds an
   authoritative word array (that is what "no host-side shadow buffer" means here). A cycle-accurate
   pixel-resident RAM would need an engine-side hook — out of scope and not claimed.
4. **Declared regions are self-declared.** A writer owns the ranges it declares; the clobber check catches
   writes *outside* declarations (the L3 rogue writer). A rogue that declares its range first is not caught —
   this is a region audit, not a per-word ownership proof.
5. **Not run this tick:** the full arc suite (only the gate plus its L5 leg were run), the GPU/WGSL parity
   legs, and any QEMU lockstep run. No performance number is claimed anywhere in this receipt or in the new
   code. Label discipline from the row is honoured: the 4 KB glyph-program memory figure is MEASURED; the
   ~37× DSL→glyph expansion is a MEASURED different quantity (never cited as interpreter overhead); the
   ~30–100 glyph-steps-per-guest-instruction figure stays an **ESTIMATE, unmeasured**.

**Scope:** three new files, nothing else modified (`git status` shows zero tracked edits). No core file
(`tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL shaders) was touched, so
no worktree isolation was required.
