# BRIEF — SUBSTOR-1: substrate storage oracle (boot a real guest from substrate-backed memory)

**Row:** `SUBSTOR-1` — `systems/GLYPH_SELF_HOSTING_ROADMAP.md:350` (status cell: `⏳ queued 2026-09-12`, eligible supply).
**Seat:** builder orchestrator (cron af3e62239ce2). You (agy) implement; the orchestrator re-runs the gate and commits. **DO NOT COMMIT ANYTHING.**

## What to build (three NEW files, nothing else)

1. `tools/substor_surface_ram.py` — **substrate-backed RAM**: a word-addressed store whose backing medium is a
   substrate surface (a Memory-Palace-style PNG frame via `tools/geos_memory_palace_viz.py::PalaceState` /
   `render_to_png` / `decode_png`, and/or the landed GH-8b pixel-FS word encoding surfaced by
   `tools/glyph_gpt/wgsl_tier.py::fs_write_words` / `fs_read_words`). Every write is logged with
   **writer attribution + write id** (reuse the DEFECT-20 discipline: see `tools/geos_witness.py` and the
   `write_id` / `writer` sidecar fields written by `tools/geos_emit.py`). Provide an explicit
   **declared-region** mechanism: a writer declares the word ranges it owns; a write outside declared ranges
   is a **clobber** and must be reported (not silently accepted).
2. `tools/substor_boot.py` — **bounded guest boot driver**: runs a real guest on the existing emulator
   `tools/spatial_rv32i_cpu.py::SpatialRV32ICore` (`MEMORY_SIZE`/`RAM_BASE` convention as in
   `tools/boot_rv32ima_linux.py`: `RAM_BASE = 0x80000000`), with the guest's RAM served from the
   substrate-backed store instead of a host-side Python array. Load from the surface before a chunk, write
   back to the surface after the chunk ("writeback"), and expose the state a witness can check.
   **Bounded by construction**: a step cap / chunk cap so the whole gate finishes in well under 120 s.
   Choose the **smallest guest that still reaches a named progress marker** (a single UART byte, a named pc,
   or a named step) and record in the module docstring exactly which guest was run and how many steps were
   actually executed. `boot_images/rv32ima_nommu/Image` (3.4 MB) + `sixtyfourmb.dtb` exist but a full
   kernel boot may be too slow/big for the surface path — if so, use the smallest real RV32IMA guest that
   satisfies L1 and SAY SO HONESTLY in the docstring and in your final report. Do not claim a Linux boot
   you did not perform.
3. `tests/test_substor_boot_witness.py` — the **gate** (this path is the acceptance contract; it must be
   RED before your change and GREEN after, run by the orchestrator too).

## Gate command (exact)

```
/usr/bin/python3 -m pytest tests/test_substor_boot_witness.py -q
```

`/usr/bin/python3` is 3.12 and has `wgpu`; the repo `.venv` (3.11) also has `wgpu`. The canonical
interpreter for this gate is `/usr/bin/python3`.

## Gate legs (all five must be present and BINDING)

- **L1 bounded boot** — a bounded guest sequence reaches a named first-instruction/progress marker, and the
  emulator's RAM reads and writes are served from the substrate-backed surface (**no host-side shadow
  buffer in the path** — assert the surface is the authority, e.g. mutate the surface between chunks and
  show the guest's next chunk sees the mutated word).
- **L2 substrate witness** — after the boot, a witness reads the surface and asserts:
  (a) **zero clobbered words** outside the writer's declared regions;
  (b) **writer attribution** for every written word (each write traced to writer + write id);
  (c) **survival across a writeback** — the guest's memory image after writeback is byte-identical to the
      pre-writeback image (no dropped writes).
- **L3 negative leg** — a deliberately injected clobber (one wrong word written by a *second* writer) MUST
  report RED through the same checker, and a dropped write on writeback MUST report RED. The witness must be
  shown to fail before it is trusted.
- **L4 non-vacuity** — neutering the attribution check turns L2 red (do this in-test with an out-of-tree
  copy or a monkeypatch the test removes; live modules restored byte-identical).
- **L5 no regression** — `tests/test_spatial_rv32i_cpu.py` stays green (invoke it as a subprocess leg with
  exit 0 and >0 tests collected). The `SpatialRV32ICore` QEMU-lockstep path is load-bearing.

## Files in scope (ONLY these)

- NEW `tools/substor_surface_ram.py`
- NEW `tools/substor_boot.py`
- NEW `tests/test_substor_boot_witness.py`

**FORBIDDEN to edit** (read them freely): `tools/spatial_rv32i_cpu.py`, `tools/geos_witness.py`,
`tools/geos_emit.py`, `tools/geos_memory_palace_viz.py`, `tools/glyph_gpt/**`, any WGSL shader,
`glyph_dispatch/**`, any `systems/RECEIPT_*.md`, any roadmap/backlog file.
If one of the five legs cannot be met without editing a forbidden file, **STOP and report** which leg,
which file, and the exact interface you would need — do not edit it and do not work around it by weakening
the leg.

## Honesty rules specific to this row (from the roadmap row's label requirements)

The row carries measured-vs-estimated labels that any prose you write must honour:
- the **4 KB glyph-program memory** figure is **MEASURED** (1024 words × 4 B);
- the **~37× DSL→glyph expansion** is **MEASURED but a different quantity** (compile-time expansion, NOT
  interpreter overhead) — never cite it as evidence for interpreter overhead;
- the **~30–100 glyph steps per guest instruction** figure is an **ESTIMATE, unmeasured**.
Do not add performance claims of any kind. No numbers you did not measure.

## Non-negotiables

- Implement, then run the gate yourself and paste the literal tail of its output.
- Do NOT commit, do NOT `git add`, do NOT touch `tools/builder_eval/results.jsonl` (a sibling seat owns it).
- No drive-by refactors, no reformatting, no renames, no edits outside the three in-scope paths.
- End with a DIFF SUMMARY: files changed, the gate command, and the literal last lines of its output.
