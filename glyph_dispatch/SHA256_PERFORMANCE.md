# SHA-256 Glyph ISA Performance

Measured: 2026-09-06 ~15:45 CDT by the sha256-real-implementation cron supervisor
(after 63 verified lockstep iterations). All numbers are live runs on this host:
GlyphCPUv2 interpreting the Glyph ISA kernel (`src/glyph/sha256_kernel.py`),
compared against `hashlib.sha256` and the FIPS 180-4 published vectors.

## Implementation Status

- [x] Padding phase implemented
- [x] Message schedule implemented
- [x] Compression rounds implemented (64 rounds, real K constants)
- [x] GlyphCPUv2 execution wired (assemble → load → run; no hashlib in the kernel)
- [x] Lockstep tests passing (13/13: 3 FIPS vectors + 10 boundary/stress inputs)
- [x] Random-input oracle check: fresh 127-byte input matched hashlib (not just stored vectors)

## Performance Metrics (GlyphCPUv2, software interpreter)

| Input length | GlyphCPUv2 wall time | Matched hashlib |
|---|---|---|
| 0 bytes  | ~30–36 ms | yes |
| 3 bytes  | ~20 ms    | yes |
| 55 bytes | ~16 ms    | yes |
| 56 bytes | ~30 ms    | yes |
| 64 bytes | ~30 ms    | yes |

- Program size: 506 glyph instructions (64-instruction-wide layout).
- Note: the 15–36 ms per hash is interpreter overhead in GlyphCPUv2 itself, not
  the algorithm; per-block SHA-256 logic is O(1) extra work per 512-bit block.

## Test Vectors

| Input | Expected Hash | Glyph Result | Status |
|-------|--------------|--------------|--------|
| empty | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | same | PASS |
| abc | ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad | same | PASS |
| abc... (56B) | 248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1 | same | PASS |

## Verification chain (receipts)

1. `tools/sha256_lockstep_test.py` — 13/13 PASS, non-zero exit on any mismatch.
2. Baseline + fresh random 127-byte input both match hashlib (guards against a
   hashlib passthrough; `sha256_kernel.py` contains no hashlib import).
3. Kernel is committed (`git log: 0957eec → f100843 → 7793b18`); working tree
   clean for `src/glyph/sha256_kernel.py` and `tools/sha256_lockstep_test.py`.

## Notes

This roadmap's S1/S2 tasks were completed and committed in earlier iterations;
the supervisor's gate (the real lockstep test) has been the source of truth
since iteration ~13. This document replaces the TODO placeholder originally
specified by task S3-2 with measured data instead of TBD entries.
