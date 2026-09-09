# SHA-256 Lockstep Gate — Negative Control Receipt (2026-09-06)

Proof that `tools/sha256_lockstep_test.py` fails loudly on a wrong hash, not
just passes on a correct one.

## Method

1. Backed up `src/glyph/sha256_kernel.py` (md5 `2495b7e20c19573256ea3597a5e427a1`).
2. Tampered K[0]: `0x428A2F98` → `0x428A2F99`.
3. Ran the gate. 4. Restored from backup and re-ran.

## Results

| State | Gate exit | Result |
|-------|-----------|--------|
| Tampered K[0] | **1 (non-zero)** | 13/13 FAIL — e.g. `abc` produced `85fb6b7d…9e118` instead of `ba7816bf…15ad`; supervisor would log `lockstep_mismatch` |
| Restored (md5 matched backup) | 0 | 13/13 PASS (3 FIPS 180-4 vectors + 10 boundary/sweep inputs) |

## Conclusion

The gate is a real oracle: any single-constant corruption of the Glyph ISA
kernel flips all 13 cases to FAIL with a printed diff and non-zero exit.
Combined with `SHA256_PERFORMANCE.md`, the green 13/13 in the supervisor log
is meaningful, not a false green.

Kernel left untouched (verified via md5). Working tree unchanged except
pre-existing untracked files in `output/`.
