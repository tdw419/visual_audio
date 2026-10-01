# BRIEF — DEFECT-28 file (2): give the VCC contract its missing encoder, then re-point three round-trip legs (roadmap row SUITE-FIX-1, cluster (4))

## Spec pointer — read these first, do not re-derive

1. `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` — row **SUITE-FIX-1**, cluster (4), the row this serves.
2. `.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md` § **"(2) `test_vcc_validation.py`"** — the ticket.
3. Measured evidence, already run by the orchestrator, in `.builder_queue/probe_defect28c_fixture_oracle.py` and
   `.builder_queue/probe_defect28c_vcc_side.py` (probe outputs are pasted in the receipt at the end of this tick).

**Measured facts you must not re-litigate:**

* The **decoder** `tools/vcc_validate.py:48-75` (1 byte/pixel, `id = (R<<16|G<<8|B) - SPECIAL_OFFSET(16)`, stop at the
  first `alpha == 0`, `grid_size` shape check) is **CORRECT and load-bearing**: it reproduces the pinned sha256 in
  `vcc_fixtures.json` for **both** committed containers byte-exact (`systems/glyph_os/tile_demo.rts.png` 16 B,
  `systems/glyph_os/window_coordinator.rts.png` 174 B). The 3-byte/pixel reading matches neither.
* `tools/pixelrts_v2_converter.py:46-59` packs **3 bytes/pixel with no offset** since `7e03abb` ("…Converter to
  successfully boot PXC1 PNG") — a deliberate boot-format variant. **DO NOT TOUCH THIS FILE.** Its only callers are its
  own CLI and the test file; nothing in the product calls it.
* Consequence: **the tree contains no encoder that emits the VCC format**, so the VCC contract cannot produce a
  container its own validator accepts, and `vcc_validate.py --record` has nothing valid to record. Closing that gap is
  the work.

## Scope

**Positive (the only files you may change):**

* `tools/vcc_validate.py` — add exactly **one** function, plus one sentence in the module docstring naming it.
* `tests/test_vcc_validation.py` — change the encoder call site in exactly **three** legs (below).

**Negative (must not change):** `decode_rts_png` and every other existing function in `tools/vcc_validate.py`; the
`SPECIAL_OFFSET = 16` constant; the argparse/CLI surface; `tools/pixelrts_v2_converter.py`; `vcc_fixtures.json`;
`docs/*`; any engine, transpiler, WGSL or `glyph_dispatch/**` file. **Interfaces are LOCKED** —
`decode_rts_png(path, grid_size=256)` keeps its name and signature.

## Task

1. In `tools/vcc_validate.py` add:

   ```python
   def encode_rts_png(input_path, output_path, grid_size=256):
   ```

   Byte-exact inverse of `decode_rts_png`: read every byte of `input_path`; for byte `i`, take hilbert index
   `d = i`, `x, y = d2xy(grid_size, d)`, `id_val = byte + SPECIAL_OFFSET`, pixel `= ((id_val >> 16) & 0xFF,
   (id_val >> 8) & 0xFF, id_val & 0xFF, 255)`; every other pixel stays `(0, 0, 0, 0)`; **no padding, one byte per
   pixel** — this is what makes the round-trip exact. Refuse with `ValueError` when
   `len(data) > grid_size * grid_size` (mirroring the converter's own refusal), and save as RGBA PNG via PIL.

2. In `tests/test_vcc_validation.py`, switch the **encode** call to `vcc_validate.encode_rts_png(...)` in exactly
   these three legs (the ones that are red today):

   * `TestVCCHilbertMapping::test_hilbert_round_trip_consistency` (encode at `:46`)
   * `TestVCCEncodingDecoding::test_large_payload` (encode at `:156`)
   * `TestVCCFixtureManagement::test_fixtures_workflow` (encode at `:237`)

   Change **no assertion anywhere**, and leave every other leg (including the converter-encoding
   `test_grid_size_mismatch_detection` and `test_hilbert_locality_preserved`) exactly as it is.

## Gate command

```
/usr/bin/python3 -m pytest tests/test_vcc_validation.py -q
```

## Gate clause (concrete, falsifiable)

* **(a)** Before your change the same command prints `3 failed, 6 passed`; after it prints **`9 passed`** and exits 0.
* **(b)** The two round-trip legs assert **exact byte equality** of 256 B and 1024 B payloads. A correct container has
  **256** and **1024** opaque pixels respectively — not 86/342, which is what the 3-byte packing produces. If your
  encoder pads, these legs fail; do not pad.
* **(c)** `git diff tools/vcc_validate.py` shows **no hunk inside `decode_rts_png`** — the decoder is untouched.
* **(d)** Decoder non-regression, both must still print `PASS`:
  `python3 tools/vcc_validate.py systems/glyph_os/tile_demo.rts.png --fixtures vcc_fixtures.json` and the same for
  `systems/glyph_os/window_coordinator.rts.png`.

## Failure evidence (required — a green you have not shown can go red is not evidence)

Write **out-of-tree** probe `.builder_queue/probe_defect28c_nonvacuity.py` that (i) neuters the new encoder (drop the
`+ SPECIAL_OFFSET` so `id_val = byte`) and runs the round-trip legs, showing them **RED**, and (ii) flips one byte of
the input and shows the decoded payload **differs** (the round-trip is discriminating, not vacuous). Run it, paste the
RED tail, then restore `tools/vcc_validate.py` and confirm its md5 is identical to the pre-probe file.

## Reporting

Report: files changed, the pre-fix RED tail, the post-fix GREEN tail, the probe output, and one honest sentence on what
the green does **not** prove. **DO NOT COMMIT** — the orchestrator re-runs every gate and commits.

## Definition of done

`tests/test_vcc_validation.py` is `9 passed`, `decode_rts_png` is byte-identical to its pre-tick form, both pinned
fixtures still validate `PASS`, the non-vacuity probe has been shown RED, and no file outside the positive scope has a
diff. Nothing is done until the orchestrator's own re-run of the gate clause says so.

## Never weaken a live guard

**Never weaken a live guard to make a leg pass.** In particular: do not relax `encode_rts_png`'s `ValueError`, do not
delete or `skip` a leg, do not loosen an `==` to `in`/`startswith`, and do not touch the decoder's
out-of-range `ValueError` at `tools/vcc_validate.py:70-73` — that refusal is the gate that caught this defect. If a
guard blocks the step, the step is wrong; report it instead.

