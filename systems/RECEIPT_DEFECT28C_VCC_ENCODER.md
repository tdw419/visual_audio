# RECEIPT — DEFECT-28 file (2): the VCC contract regains its encoder (roadmap row SUITE-FIX-1, cluster (4))

**Landing:** 2026-09-13, builder cron `af3e62239ce2`, branch `glyph-transpiler-autoloop`, pre-tick HEAD `6ede59a`.
**Files:** `tools/vcc_validate.py` (+28, additive), `tests/test_vcc_validation.py` (3 encoder call sites, untracked →
force-added). Delegate `agy` (`output/agy/agy_impl_20260913_193948.log`, exit 0 / 146 s); **every number below is the
orchestrator's own re-run**, not the delegate's claim.

## What was actually wrong (measured, not inferred)

The ticket asked: *encoder byte-range contract, or fixture geometry?* Neither — the tree contains **two incompatible
container layouts**, and the VCC side had **no encoder at all**.

| reading | scheme | `tile_demo.rts.png` (pinned `2812ccb0…`) | `window_coordinator.rts.png` (pinned `0ac97126…`) |
|---|---|---|---|
| `vcc_validate.decode_rts_png` (1 B/pixel, `id − 16`) | VCC / VAC1-VAC2 legacy | **MATCH** (16 B) | **MATCH** (174 B) |
| 1 B/pixel, no offset | – | no | `ValueError: byte must be in range(0,256)` |
| 3 B/pixel (live converter) | PXC1 boot | 48 B, wrong hash | 522 B, wrong hash |

Two probes, both committed: `.builder_queue/probe_defect28c_fixture_oracle.py` (the pinned-fixture oracle above) and
`.builder_queue/probe_defect28c_vcc_side.py` (first-6-pixel dump: converter emits `(0,1,2,255) (3,4,5,255) …`, i.e.
3 bytes/pixel contiguous).

So: the **decoder is right** (it reproduces the committed ground-truth hashes byte-exact); `vcc_fixtures.json`, the
decoder's docstring, `verify_container.sh:59-61` and `docs/VIRTIO_BACKEND_GUIDE.md:297,331-333` all specify the same
1 B/pixel + `SPECIAL_OFFSET=16` contract; and `tools/pixelrts_v2_converter.py:46-59` is a **deliberate PXC1-boot
variant** (introduced by `7e03abb`, "…Converter to successfully boot PXC1 PNG") that is nobody's VCC encoder. Its only
callers are its own CLI and this test file. Because nothing in the tree could *produce* a VCC container, the three red
legs were the symptom of a **missing half of the contract**.

## The fix (additive; no format change, no boot risk)

`tools/vcc_validate.py` gains **`encode_rts_png(input_path, output_path, grid_size=256)`** — the byte-exact inverse of
its own `decode_rts_png` (Hilbert index `d = i`, `id = byte + SPECIAL_OFFSET`, `A=255`, everything else transparent,
`ValueError` above grid capacity). `decode_rts_png`, `structural_hash`, `SPECIAL_OFFSET`, the CLI surface and
`tools/pixelrts_v2_converter.py` are untouched (`git diff` shows no hunk inside `decode_rts_png`). The three failing
legs now encode with the VCC encoder: `tests/test_vcc_validation.py:46`, `:156`, `:237`. **No assertion was changed,
deleted, skipped or loosened.**

## RED → GREEN

RED, orchestrator's own run at `6ede59a` (pre-change, gate command `/usr/bin/python3 -m pytest tests/test_vcc_validation.py -q`):

```
FF...F...                                                                [100%]
tests/../tools/vcc_validate.py:71: ValueError: Decoded byte out of range at pixel 0 (0,0): 6711656
tests/../tools/vcc_validate.py:71: ValueError: Decoded byte out of range at pixel 1 (1,0): 197621
3 failed, 6 passed in 0.16s
```

RED reproduced from the **pre-fix blob** (re-runnable artifact `output/DEFECT28C_RED_prefix.txt`, probe
`.builder_queue/probe_defect28c_prefix_red.py`, which loads `git show HEAD:tools/vcc_validate.py` as a module):

```
prefix module has encode_rts_png: False
PREFIX RED: ValueError: Decoded byte out of range at pixel 1 (1,0): 197621
```

GREEN, orchestrator's own run (`output/DEFECT28C_gate_green.txt`):

```
.........                                                                [100%]
9 passed in 0.16s        rc=0
```

Decoder non-regression, orchestrator's own runs (fixtures untouched): both containers print
`PASS: structural hash matches reference`, rc=0 (16 B / 174 B payloads).

## Non-vacuity (the gate is discriminating)

* **My own probe**: dropped `+ SPECIAL_OFFSET` from the new encoder → gate goes RED, `2 failed, 7 passed`, rc=1
  (the two round-trip legs); file restored md5-identical `e9a2fa5cd1c4b9b1a4b10dd436e3a1c3`.
* **Delegate's probe** (`.builder_queue/probe_defect28c_nonvacuity.py`, run by me, `output/DEFECT28C_nonvacuity.txt`):
  neutered offset → round-trip RED; one-byte input flip → decoded payload differs at index 42; md5 after == before.

## Honest boundary — what this does NOT prove

1. **`test_fixtures_workflow` is weakly discriminating**: it records a hash from its own decode and compares it to
   itself, so the neuter probe leaves it green. Its redness pre-fix came only from the decoder refusing. It proves the
   workflow runs, not that the bytes are the right ones.
2. **Two container formats now coexist by design and only one is exercised here.** The converter's 3 B/pixel layout
   still cannot be ingested by the VCC validator, and no test covers it; whether the PXC1 boot layout *should* be a
   named, gated variant is left as a question (`.builder_queue/REPAIR_PENDING_defect28c_container_format_authority.md`).
3. No CLI `--encode` entry point was added, so `vcc_validate.py --record` still has no way to *produce* the container
   it records; the encoder is a library function only.
4. No WGSL/GPU leg, no `.nut`/VAC3 container leg, and the arc was not re-run — the change touches neither engine,
   transpiler, WGSL nor `glyph_dispatch`, and `tools/vcc_validate.py`'s only importers are its own CLI and this test
   file (measured repo-wide).
5. The pinned-fixture match is evidence for exactly two committed containers; it is not a survey of every `.rts.png`
   in the tree.
