# BK-8 Receipt — GH-8b Pixel-Resident FS as SHA-256 Working-Set Storage

**Item:** BK-8, promoted from GLYPH_BACKLOG at ff387f9 (builder cron af3e62239ce2)
**Gate clause:** "spec review + measured before/after on the 13/13 gate"
**Branch:** glyph-transpiler-autoloop · **Date:** 2026-09-11
**Gate:** `tests/test_bk8_fs_pix_sha256.py` — RED `output/bk8_gate_run1_red.txt` (15 failed) → GREEN `output/bk8_gate_run2_green.txt` (15 passed in 0.51s)

## Spec review (implementation contract)

The SHA-256 kernel's ENTIRE working set now lives in the GH-8b pixel-resident
FS window [1024, 1280) — 2 pixels per 32-bit word aliasing the saved ndarray,
bit-exact through PNG round-trips:

| region | legacy (host-RAM) | pixel-resident (window) | size |
|---|---|---|---|
| K[0..63] round constants | 100 | **1024** | 64 words |
| W[0..63] schedule | 200 | **1088** | 64 words |
| block index / count | 270 / 271 | **1152 / 1153** | 2 words |
| message blocks | 280 | **1154** | ≤80 words (5 blocks max) |
| digest out | 400 | **1234** | 32 words |

Working-set total 242 words ≤ 256-word window. Text = 506 instrs = 8 rows =
pixel words [0, 1024); the image is padded by 8 rows so window words wrap
onto padding pixels, never text (word 1024 → (0,8), first pad row, via the
linear-wrap `_addr_to_xy`).

### What actually had to change (the finding)

`build_sha256_glyph_program()` bakes every base as an **LDI immediate in the
program body** (`LDI r19 271`, `LDI r21 100`, the W-copy's `LDI r19 200..215`
stores, `LDI r29 280`…). Relocation is therefore a **program rebuild with
shifted constants**, not a seed-address change: relocating only the host-side
seed leaves the kernel reading `memory[271]` (= 0 → CMP equal → branch to
`outer_end` → 245 steps → zero digest, the RED run's failure mode).
`_build()`/`build_sha256_glyph_program()` gained base parameters (defaults =
legacy values, so every existing caller — lockstep test, dispatcher,
`sha256_glyph()` — is untouched); the gate test rebuilds with window bases
and seeds through `_mem_write` (the engine's own window-write path), reading
the digest back with `_fs_pix_read`.

## Measured before/after on the 13/13 gate

BEFORE (committed baseline, 0x8bf3724f…): `glyph_dispatch/tools/sha256_lockstep_test.py` **13/13** on
host-RAM bases. AFTER: same 13/13 run re-executed post-change **13/13**
(`output/bk8_lockstep_after.txt`, exit 0) plus the identical vector set on
pixel bases (gate L1, 13/13).

### Timing (5 fresh-instance runs, median; 300-byte input, 5 blocks, 43,735 steps)

| config | seed cost | exec time |
|---|---|---|
| BEFORE host-RAM working set | 9 µs | **75.1 ms** |
| AFTER pixel-resident window | 92 µs | **77.0 ms** |

Interpretation (honest boundary): the CPU interpreter's working-set access is
address-path only (window predicate + pixel-word math vs a list index), so
execution is ~2.5% slower and host-side seeding ~10× costlier (pixel writes).
The point of BK-8 was never CPU speed — it is that the working set now rides
in the image, so the working set **survives PNG round-trips and reboots with
zero host-side buffers**, which is what the other session's SHA-256 lane
wants for in-image storage. `sha256_glyph()` and the dispatcher keep the
legacy fast path.

## Gate legs (15 tests)

- **L1 FIPS (3)** + **L1 sweep (10)**: all FIPS 180-4 + boundary/stress
  vectors digest byte-exact with the working set in pixels.
- **L2 fs_pix_enabled is the storage (1)**: digest reads back from image
  pixels; with the flag off a window-address read linear-wraps onto raw
  pixels and does NOT see the seeded BCNT=1 (window view ≠ legacy view).
- **L3 PNG persistence (1)**: post-run image → PNG → reload is bit-exact and
  still yields the correct digest — "the image is the disk" now proven over
  a full SHA-256 working set.

## Regressions

- `tests/test_gh8_fs.py` + `test_gh8c_canonical_replay.py` (GH-8b prereq): 11 passed
- `tests/test_gh9_loader.py`, `test_bk6_integrity.py`, `test_bk7_fs_grow.py`: 24 passed
- `tests/test_bk1_argv.py`, `test_bk3_signals.py`, `test_bk4_join.py`: 14 passed
- WGSL/parity + arc core: `test_gh4_wgsl_parity.py`, `test_gh7_processes.py`,
  `test_gh16_preemption.py`, `test_gh18_syscall_abi.py`,
  `test_gh25_hilbert_paging.py`, `test_gh26_resident.py`: 41 passed
- `test_gh26_glass_box.py` (py3.12 venv): 8 passed
- glyph_dispatch suite: `test_sha256_dispatch.py`, `test_item2_dispatch_sha256.py`,
  `test_dispatch.py`: 12 passed; `tools/sha256_lockstep_test.py` 13/13 exit 0;
  `test_item5b_wgsl_parity.py` script: "WGSL/Python glyph ISA parity: ALL PASS"
  (incl. the sha256_glyph(b'abc') leg)

## Notes / caveats

- WGSL has no FS-window branch (its mem_read/mem_write have no [1024,1280)
  predicate), so a WGSL leg of the pixel-resident kernel is NOT included —
  that is a BK-2-style follow-up ("FS-window parity for WGSL"), not part of
  BK-8's gate clause. Noted here so nobody mistakes the omission for an
  oversight.
- `glyph_dispatch/tools/regression_gate.py` times out standalone (600s; it
  chains slow emulator suites) — the individual suites it references were run
  directly instead, all green.
- Roadmap order note: BK-1 (queued 19:00) is also implemented and green at
  HEAD (5/5, run this session); its row will be closed with its own receipt.
