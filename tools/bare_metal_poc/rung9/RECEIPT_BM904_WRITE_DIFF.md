# RECEIPT — BM904 guest write-side pixel diff (inverse provenance gate)

**Date:** 2026-09-19 (builder cron af3e62239ce2)
**Brief:** `.builder_queue/brief_bm904_guest_write_diff.md` (contract-complete,
commits `2fc14918` + `ac1ce868`; check_brief PASS)
**Gate:** `python3 tools/bare_metal_poc/rung9/bm904_write_diff_probe.py` —
**GATE PASS ×3 consecutive, exit 0** (final run `output/bm904_gate_final.log`;
run-3 leg detail in `output/bm904_gate_result.json`)
**RED leg:** `--mutant` (corrupted predictor chain) → **exit 1**,
`output/bm904_gate_mutant_red.log`; deterministic synthetic RED via
`--selfcheck`.

## Question answered

BM903 proved the read direction (guest file ≡ pixels ≡ /peek). BM904 closes
the WRITE direction: guest writes 256 random bytes at a known offset of a
preallocated 64 MiB probe file; the host predicts the EXACT changed-pixel set
from the retrieved bytes mapped through the address chain, then asserts the
measured decode diff equals that prediction. Measured: **yes, exactly** —
the diff primitive is a live FS-block→pixel mapping tool, not just a
yes/no oracle.

## Gate legs (final green runs, 2026-09-19 08:2x–08:35)

- **Self-check (deterministic, non-vacuity):** synthetic frame, 3-byte write
  → predicted == {pixel(5,0,0)}; comparator RED against an off-by-one
  physical-block chain. Runs every invocation.
- **Setup:** `fallocate -l 64K→64MiB` BEFORE any data → `filefrag -v` extents
  stable before writes (2 extents, frames [223,224]/[224,225],
  vda3_start=1880192). Prealloc region decodes as zeros through the chain.
- **Control leg (noise floor):** snapshot → barrier → snapshot, NO guest
  write → **0 changed px** on the probe frames, all runs. Zero floor ⇒ the
  gate asserts EXACT equality (stricter than the brief's ⊆-union fallback).
- **Treatment run1:** 256 random bytes at 32 MiB (mid-frame). Guest-written
  (`dd` from guest `/dev/urandom`, saved guest-side, content retrieved
  read-only via `base64`); readback sha quoted by the guest matches the
  predictor's input. **changed=64 == predicted=64, extra=0, missing=0 →
  EXACT.**
- **Treatment run2:** same at the frame-boundary straddle
  (off = to_boundary−128; writes cross the 64 MiB frame edge — one pixel
  per byte, 64 B/pixel-row × channel interleave). **EXACT.**
- **R1 durability boundary (measured, not gated):** AFTER the write, BEFORE
  writeback, `/peek` at the first written disk byte serves the NEW byte
  (peek == written in every run, incl. LRU eviction) while the PNG decode
  still serves the OLD byte (png ∈ {0, previous run's byte}) —
  **`peek_leads_png: true` in both runs.** The peek/overlay plane leads the
  disk PNGs across the journal/writeback boundary, exactly the asymmetry the
  brief predicted. Recorded, never tuned (R1 dies with the shim).
- **R2 one-byte sensitivity:** host paints one R channel of a written-region
  pixel to `old^0xFF` → re-decode diff catches **exactly that pixel**;
  restore → frame byte-identical (`np.array_equal`). Full-revert discipline.
- **Cleanup:** guest `rm` + `sync`; probe GONE; journal empty (0 dirty
  frames) after the final barrier.

## RED-first / falsification

- **Live RED (`--mutant`, exit 1):** extent-0 `physical_first +1` corrupts
  the predictor; run1 stays EXACT (mid-frame offset absorbed the +1 block on
  extent 0's start... measured: run1 EXACT because extent-0 writes map
  +4096 B within the same frame region the file still owns — the boundary
  leg is what catches it), run2 straddle predicts 64 px vs 96 actual →
  `extra=32 → FAIL` → gate exit 1. The assertion is load-bearing on the
  real container, not just in the synthetic self-check.
- **Bring-up RED (defect tails, fixed in-session):**
  1. R1 ordering — peek ran BEFORE the write (measured nothing:
     peek=png=0); fixed to after-write/before-writeback.
  2. R2 tuple order — `changed_pixels` yields (frame,y,x); comparison used
     (frame,x,y) and mis-reported a real catch as False. Fixed; the
     earlier run's `catch=False` was the comparator bug, not a gate miss.
  3. Straddle assert — degenerate file layouts (first disk byte within 128 B
     of a frame boundary) made `off_cross` negative; now clamped with the
     crossing assert retained.

## Survives-the-shim accounting (brief endgoal section)

- **SURVIVES (the deliverable):** `Chain` (extent lba → disk byte →
  frame/x/y/channel; imports the locked `locate_in_container` chain, never
  forks it), `predict_changes` + `changed_pixels` (decoded-pixel diff
  primitive), the control-leg noise-floor method (assert EXACT when the
  floor is 0, ⊆-attribution otherwise). Any replacement decoder must honor
  exactly this contract.
- **DIES WITH THE SHIM:** R1 (peek/PNG asymmetry) — measured and recorded
  here, not deepened.

## Scope

`rung9/bm904_write_diff_probe.py` (new), this receipt, ROADMAP.md Rung 9
cell, `output/bm904_*` artifacts. Guest writes limited to the two probe
files (rm'd + sync'd, verified gone); host-side container changes limited to
the R2 paint, fully reverted and re-verified in-leg. No
`systems/virtio_pixel_rs/` edits, no backend restart, no compaction calls
outside `Container.barrier` (the documented writeback barrier).

## What this PASS does NOT prove

- **n=2 treatment offsets per run, single probe file, single guest session.**
  Multi-file concurrency, ext4 journal replay of the probe extents, and
  fallocate-hole materialization under memory pressure are untested.
- **R2 proves diff sensitivity to a HOST paint, not to a second guest
  writer** — a concurrent guest write during the snapshot window would
  surface as `extra` px; none occurred (quiet container), and the control
  floor was measured once per run, not continuously.
- **R1 is one boundary (write→writeback), n=2, single byte per run** — the
  peek plane's overlay semantics beyond the first written byte are not
  characterized; R1 is shim-forensics and dies with the shim anyway.
- **`/peek` byte order** relies on the `livemap_probe.peek` little-endian
  word convention (imported, not re-derived); a backend word-format change
  would corrupt R1 readings (only) silently.
- The 256 B write granularity means **sub-pixel-byte structure** (2 written
  bytes inside one 4-channel pixel) is exercised (256 B > 64 B/px), but
  single-BYTE pixel-set sensitivity is only probed by the R2 host paint.
- GATE PASS ×3 are same-boot, same-container runs; behavior across a guest
  reboot (extent reassignment) is out of scope.
