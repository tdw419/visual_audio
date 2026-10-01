# RCA: GH-9 loader patch invisible to instruction fetch (E_ATLAS_INJECT regression)

**Date:** 2026-09-10
**Branch:** glyph-transpiler-autoloop (HEAD c8b72e9)
**Tickets:** `.builder_queue/gh15-step3-eatlas-inject.json` (+ 3 latent reds found during RCA: `test_gh9_loader` x2, `test_gh11_drives_gh9`)
**Root commit:** 087f29b "fix(spadsl): PARALLEL_* opcodes address word RAM"

## Symptom

`tests/test_gh15_step3_autoatlas.py::test_ingest_dispatches_kernel_through_ir_gate`
fails with:

```
E_ATLAS_INJECT: still diverges on-die after 6 re-escalation cycles
(last kernel result 0x0, expected 0x10)
```

Deterministic (monkeypatched router, no model), reproduces at clean HEAD,
6/6 re-escalation cycles with the identical signature: kernel status
`0xCAFE0009` (clean), result word 0, exit word 0, no fault.

## Failure chain (symptom → root cause, all measured)

1. `ingest()` packs the candidate tile into mailbox words and the host
   seeds them into RAM; the resident GH-9 loader kernel copies them with
   a `PARALLEL_ST r15 r8 1` loop into its reserved exec window at
   linear pixel index 304 (`:__g9window` = instr cell (col 4, row 9),
   image 32 px wide -> 9*32 + 4*4 = 304), then latches USER and KJMPs in.
2. **The Python engine fetches instructions from IMAGE pixels**
   (`GlyphCPUv2.step()`: `opcode_px = image[y, x]`), not from RAM.
   The patch window's pixels are therefore the execution truth.
3. 087f29b changed `PARALLEL_ST` from `self._mem_write(image, ...)` to
   `self.memory[...] = ...` (word RAM), to fix SpaDSL region divergence
   (see `RCA_PARALLEL_MEM_MODEL.md`). That fix is correct for region
   DATA — but it silently broke the GH-9 loader contract, because the
   patch now lands in RAM **words 304..**, which the fetch never reads.
4. Measured: after `drive()`, RAM[304..399] holds the exact payload
   (`probe_gh15_step3i.py`: "payload matched at RAM base: 304") while
   image pixel (16,9) still reads `0xff6347` = **HALT** (the window's
   baked padding).
5. So the tile's very first instruction executes as HALT: the machine
   stops cleanly (status pre-seeded `0xCAFE0009` by the launch leg),
   result 754 = 0, exit 703 = 0 — exactly the observed signature. Step
   trace: 917 steps, last instr idx 76 (= the window), one USER step.
6. Host-side image stamping (the GH-18 admit path's `_pix_write_word`)
   makes the same payload pass (`probe_stamp_fix3.py`: result 0x10,
   exit 0xFEED0009) — isolating the defect to the in-image patch path.

## Why 087f29b's own gate stayed green

SpaDSL suites only exercise RAM region data; the GH-18 gate (admit path)
stamps tiles into the image **host-side** (`runner.image` mutation), so
no gate in the merged commits executed the kernel-side PARALLEL_ST
patch until a GH-9/GH-11/GH-15 e2e leg ran. The GH-9/GH-11 reds existed
at HEAD but were outside the tracked ticket's file, and the arc
regression run (`gh23_arc_regress_0910c`) only surfaced the GH-15 leg.

## Fix

`tools/glyph_isa_v2.py` + twin `glyph_dispatch/src/glyph/glyph_isa_v2.py`:
`PARALLEL_ST` keeps the 087f29b word-RAM store AND additionally mirrors
each stored word into the image pixel at the same linear index when in
bounds. This is the **GH-8b write-through mirror pattern** already used
by `_fs_pix_write` ("memory[] coherent; the PIXELS remain the persisted
truth"). Consequences:

- SpaDSL region semantics unchanged: `PARALLEL_LD` reads RAM, regions
  still round-trip (no image-space side effect visible to them).
- GH-9 loader patch lands in the pixels the fetch reads: the window
  becomes executable again.
- Addresses beyond the image (large SpaDSL regions) skip the mirror —
  no behavior change there.
- WGSL twin unaffected (no image plane; it never executed these gates).

## Receipt discipline

- RED before fix (at HEAD c8b72e9, WIP stashed):
  - `test_gh15_step3_autoatlas.py::test_ingest_dispatches_kernel_through_ir_gate`
  - `test_gh9_loader.py::test_gh9_injected_program_computes_on_argv` (result 0x0 != 0x1a2d)
  - `test_gh9_loader.py::test_gh9_offline_rerun_replays_launch`
  - `test_gh11_launcher_endtoend.py::test_gh11_drives_gh9`
- GREEN after fix: 26/26 across test_gh9_loader + test_gh11 +
  test_gh14 + test_gh15_step3; full arc re-run receipt in
  `output/gh15fix_arc_rerun_0910.txt`.
- Probes kept: `output/probe_gh15_step3{,b..l}.py`, `probe_stamp_fix3.py`.
