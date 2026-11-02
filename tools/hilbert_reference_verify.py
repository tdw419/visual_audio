#!/usr/bin/env python3
"""
Hacker's Delight Hilbert curve reference implementation.
Used to verify the Rust implementation (systems/geos_pixel/src/hilbert.rs)
against a known-correct version.

IMPORTANT: a pure-Python round-trip check (d2xy then xy2d gives back d) is
NOT sufficient to validate the Rust translation. Python ints are signed and
arbitrary-precision, so an expression like `s - 1 - x` going negative is not
an error in Python -- it round-trips fine regardless. The equivalent Rust
code uses `usize` (unsigned, fixed-width) and will panic (debug builds) or
silently wrap (release builds) on that same subtraction. This bit this file
twice: an earlier version of xy2d_ref used `s - 1 - x` and reported "OK" for
n up to 256, while the matching Rust code panicked immediately in QEMU on a
real boot test. See systems/virtio_pixel_rs_v3/SKELETON_PLAN.md Phase 1.9.

xy2d_ref below reflects against the full grid `n`, not the shrinking step
`s` -- this is required because x/y are full-range coordinates in [0, n)
for the whole loop (unlike d2xy, which builds them up incrementally and is
genuinely bounded by s). Do not "simplify" this back to `s - 1 - x` without
rebuilding virtio_pixel_rs_v3 for x86_64-unknown-uefi and booting it in
QEMU against a real Hilbert-encoded PNG to confirm no panic and correct
output -- a passing round-trip here proves nothing about the unsigned Rust
translation's safety.
"""

def d2xy_ref(n, d):
    """Convert 1D distance d to 2D coordinates (x, y) on an n x n grid."""
    x, y = 0, 0
    s = 1
    while s < n:
        rx = 1 & (d // 2)
        ry = 1 & (d ^ rx)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        d //= 4
        s *= 2
    return x, y

def xy2d_ref(n, x, y):
    """Convert 2D coordinates (x, y) to 1D distance d on an n x n grid."""
    d = 0
    s = n // 2
    while s > 0:
        rx = 1 & (x // s)
        ry = 1 & (y // s)
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = n - 1 - x, n - 1 - y  # reflect against full grid n, not step s
            x, y = y, x
        s //= 2
    return d

def xy2d_unsigned_safe(n, x, y):
    """Simulates the Rust usize translation with explicit bounds assertions,
    so a bug that Python's signed ints would silently absorb instead raises
    here, matching what `-C overflow-checks=on` does in Rust."""
    d = 0
    s = n // 2
    while s > 0:
        rx = 1 & (x // s)
        ry = 1 & (y // s)
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                assert x <= n - 1, f"would underflow: n-1-x with x={x} n={n}"
                assert y <= n - 1, f"would underflow: n-1-y with y={y} n={n}"
                x, y = n - 1 - x, n - 1 - y
            x, y = y, x
        s //= 2
    return d

def verify_hilbert(n):
    """Verify d2xy and xy2d are inverses across all points in an n x n grid,
    using the unsigned-safe variant so an underflow would raise, not hide."""
    for d in range(n * n):
        x, y = d2xy_ref(n, d)
        d_back = xy2d_unsigned_safe(n, x, y)
        if d != d_back:
            return False, f"d2xy({n}, {d}) -> ({x}, {y}) -> xy2d({n}, {x}, {y}) -> {d_back} != {d}"
    return True, "OK"

if __name__ == "__main__":
    for n in [2, 4, 8, 16, 32, 64, 128, 256]:
        ok, msg = verify_hilbert(n)
        print(f"n={n}: {msg}")
        if not ok:
            print(f"  ERROR: {msg}")
            break
