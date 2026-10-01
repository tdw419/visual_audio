# RECEIPT — BK-12: WGSL throughput tier

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` BK-12 (promoted from
`systems/GLYPH_BACKLOG.md` at `a636aae`).
**Gate:** `tests/test_bk12_wgsl_tier.py`.
**Status:** ✅ done 2026-09-12 by builder cron `af3e62239ce2`.

Gate clause as promoted: *"1KB block copy WGSL vs CPU byte-identical;
measured speedup receipt in docs/"*. Both halves are satisfied below, plus
two legs (non-vacuity, real-engine pixel tier) that the clause does not
demand but that the claim needs in order not to be a tautology.

---

## 1. Receipts

| Receipt | Path |
|---|---|
| RED — gate collected, module absent | `output/bk12_gate_run1_red.txt` (`ModuleNotFoundError: No module named 'tools.glyph_gpt.wgsl_tier'`) |
| GREEN — 6/6 + MEASURED lines | `output/bk12_gate_run2_green.txt` |
| Arc regression (GH/BK/ENG arc) | `output/bk12_arc_regression.txt` |

Arc at this commit: **307 collected, 306 passed, 1 failed** — the single
failure is `tests/test_bk11_coreutils.py::test_bk11_tool_compiles_transpiles_and_runs[wc]`,
which is BK-11's own known-red leg, blocked on the DEFECT-18 design decision
(`.builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md`), unchanged by
this row. No engine, transpiler or ABI file was touched: this row adds
`tools/glyph_gpt/wgsl_tier.py` + its gate.

## 2. Mechanism

`tools/glyph_gpt/wgsl_tier.py` adds a second tier **beside** the pixel
provenance tier:

* `BLOCK_COPY_WGSL` — a WGSL compute shader (`@workgroup_size(64)`, one word
  per invocation, read-only `src` + read-write `dst` + a uniform for
  `count/src_off/dst_off`). A real second memory region, because a copy
  between two FS extents is not an in-place mutation.
* `WgslBlockCopier` — resident buffers/pipeline, `copy()` submits one
  dispatch, `read_dst()` reads back. `wgsl_block_copy()` is the one-shot form
  the gate's 1KB leg uses.
* `cpu_block_copy()` — the CPU reference the GPU is compared against.
* `fs_write_words()` / `fs_read_words()` — the provenance bridge. They call
  `glyph_isa_v2`'s own `_fs_pix_write` / `_fs_pix_read` (GH-8b: 2 px/word,
  lo24 in pixel RGB, hi8 in the BLUE channel of the odd pixel), so the bridge
  cannot drift from the encoding the CPU dispatch uses on an LD/ST into the
  window.
* `build_pixel_copy_program()` / `run_pixel_copy()` — a real assembled
  engine program (LDI/LD/ST/ADD/SUB/CMP/JZ/JMP, absolute packed `col,row`
  jump targets) whose storage IS the pixel window, executed by `GlyphCPUv2`
  with `fs_pix_enabled=True`.

### Gate legs

1. `test_l1_…` — 256 words (1KB) copied on WGSL compute buffers, compared
   **word-for-word, by md5 and by sha256** against `cpu_block_copy`.
2. `test_l1b_…` — non-vacuity: destination guard words outside the copy
   window stay zero; flipping one source word moves exactly one destination
   word (a shader that copies nothing, or everything, fails).
3. `test_l2_…` — the same 1KB routed through the GH-8b pixel window and back
   decodes to the identical word list, including a layout spot-check; the GPU
   tier over the decoded words still matches the source.
4. `test_l3_…` — the pixel tier is functional: the engine's copy loop HALTs,
   fault-free, in 517 steps for 64 words, and the words read out of **pixels**
   equal the source.
5. `test_l4_…` — like-for-like throughput on the same 64-word block, asserted
   in the direction claimed (GPU tier not slower).
6. `test_l4b_…` — scaling: 1KB vs 16KB, so the receipt can say where the tier
   pays rather than quoting one flattering number.

## 3. Measured numbers

Environment: RTX 5090 Laptop GPU (Vulkan), `wgpu` 0.28.1, `/usr/bin/python3`
3.12.3 (the interpreter the existing arc receipts were produced with), run
`output/bk12_gate_run2_green.txt`:

```
MEASURED bk12 pixel_tier  bytes=256   seconds=0.001373  bytes_per_s=186,450    steps=517   (engine LD/ST loop, /usr/bin/python3)
MEASURED bk12 wgsl_tier   bytes=256   seconds=0.000046  bytes_per_s=5,614,331  submits=200 setup_seconds=0.000272
MEASURED bk12 speedup=30.1x
MEASURED bk12 wgsl_scaling words=256   bytes=1024   seconds=0.000052  bytes_per_s=19,802,286
MEASURED bk12 wgsl_scaling words=4096  bytes=16384  seconds=0.000345  bytes_per_s=47,446,844
```

Re-measured under the 3.11/wgpu-0.32 environment for independence:
pixel tier 230,867 B/s, WGSL tier 5,334,246 B/s (23.1×), 1KB 20.7 MB/s,
16KB 53.4 MB/s — the direction and order of magnitude are stable across both
interpreters, so the claim is not an artifact of one environment.

Reading of the numbers, stated plainly:

* The **like-for-like** comparison (both tiers moving 256 bytes through a
  called operation) is 186 KB/s vs 5.6 MB/s — **~30×**, and the pixel tier's
  517 steps for 64 words is what its cost structure is: one engine
  instruction per word moved.
* At 1KB per call the WGSL tier is ~20 MB/s: a single dispatch is ~52 µs, of
  which almost all is fixed submit overhead. The tier's honest throughput
  only appears as blocks grow (16KB → 47 MB/s).
* The tier's one-time setup (buffers + pipeline + shader compile) measured
  0.27 ms and is excluded from the per-call figure — it is reported rather
  than hidden.

## 4. Honest boundaries

* **No engine change, and no in-image dispatch.** The GPU cannot be driven
  from inside the pixel substrate: the tier is a *host-side service* the
  runner/baker calls, exactly as the GH-24/RECEIPT provenance tooling is
  host-side. Wiring an in-OS `fs_copy` to route through this tier is a
  GH-26-aperture-class integration (agent/host write path), not this row's
  gate, and is not claimed here.
* **Execution speed is unchanged.** This moves bytes; it does not make
  Glyph OS execute faster. Programs still run one pixel-instruction at a
  time on the provenance tier.
* **On the "tens of bytes per second" figure.** `docs/PROVABLE_OS.md` §7
  derived that from the lockstep/per-step-readback harness. This row's
  measurement shows the *interpreter* engine copying at 186 KB/s — a
  different path. Both numbers are now stated with their paths instead of
  one figure standing for the tier (doc updated in the same commit).
* **Scale.** 1KB is the gate's clause and 16KB is the largest block measured
  here; nothing above that is claimed.

## 5. Files

* `tools/glyph_gpt/wgsl_tier.py` (new) — the tier + the pixel bridge.
* `tests/test_bk12_wgsl_tier.py` (new) — the gate (6 legs).
* `docs/RECEIPT_BK12_WGSL_TIER.md` (new, this file).
* `docs/PROVABLE_OS.md` — §7/§8 updated: BK-12 no longer "in-progress", with
  the measured numbers and their caveats.
* `systems/GLYPH_SELF_HOSTING_ROADMAP.md` — BK-12 row closed with mechanism +
  boundary.

*The machine reports; the arithmetic decides.*
