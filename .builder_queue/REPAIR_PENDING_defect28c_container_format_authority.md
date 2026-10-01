# REPAIR_PENDING — two .rts.png container formats now coexist and only one is owned/gated

**Filed:** 2026-09-13 by builder cron `af3e62239ce2`, HEAD `6ede59a` (tick that landed DEFECT-28 file (2)).
**Status:** OPEN — **design question for Jericho** (format authority). Not blocking: nothing in this tick's work waits on it.
**Origin:** `.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md` § "(2)" said *"if the deciding fact is the VCC
spec, this becomes a ruling request, not a patch."* The deciding fact turned out to be measurable (see
`systems/RECEIPT_DEFECT28C_VCC_ENCODER.md`), so the patch landed **without** changing either format. What is left over
is the ownership question below.

## Measured (orchestrator's own runs, committed probes)

* **Format A — VCC / VAC1-VAC2 legacy:** Hilbert index = byte index, **1 byte/pixel**, `id = byte + SPECIAL_OFFSET(16)`,
  `A=255` for payload pixels, transparent elsewhere, stop at first `alpha == 0`. Ground truth: `vcc_fixtures.json`'s
  two pinned sha256 both reproduce **byte-exact** (`systems/glyph_os/tile_demo.rts.png` 16 B,
  `window_coordinator.rts.png` 174 B). Specified by `tools/vcc_validate.py` (docstring + decoder),
  `verify_container.sh:59-61`, `docs/VIRTIO_BACKEND_GUIDE.md:297,331-333`.
* **Format B — PXC1 boot:** `tools/pixelrts_v2_converter.py:46-59` since `7e03abb` ("…Converter to successfully boot
  PXC1 PNG"): **3 bytes/pixel (R,G,B)**, no offset, zero-padded to a multiple of 3. **Length-lossy** — a payload whose
  length is not a multiple of 3 cannot be recovered (no length metadata in the PNG), which is precisely why Format A is
  the only one that can satisfy an exact-round-trip contract.
* As of this tick, Format A has an encoder again (`tools/vcc_validate.py::encode_rts_png`, added for DEFECT-28 (2)),
  but the two formats are still only distinguished by *which function you call*; Format B has no test at all and
  Format A has no CLI write path.

## Options (cheapest first)

1. **Declare them distinct and name them (recommended, ~15 min).** Document Format A/B in
   `docs/VIRTIO_BACKEND_GUIDE.md` with one line each about who writes and who reads them; add a module docstring note to
   `tools/pixelrts_v2_converter.py` that its layout is the boot variant and **not** VCC-compliant. No code change.
2. **Give the converter an explicit mode** (`convert_to_rts_png(..., layout="pxc1"|"vcc")`, default unchanged) and add a
   `--encode` CLI flag to `tools/vcc_validate.py`. Additive, but it changes a tracked module's signature and widens
   the CLI surface — hence the seat.
3. **Unify on Format A** by making the converter emit it. Rejected-on-measurement as a *default*: Format B was
   deliberately introduced to make PXC1 boot, and nothing in the tree verifies boot either way.
4. **Give Format B a length header** (e.g. a metadata pixel/tEXt chunk) so both formats can round-trip exactly. Largest
   change, touches the bootable container layout.

## What the loop did instead

Landed option-1 semantics for Format A (an encoder that actually produces what the VCC validator accepts) without
touching Format B or the boot path, and left this note so the choice is Jericho's rather than inferred.
