/// True Hilbert curve coordinate mapping (Hacker's Delight).
/// Preserves Manhattan distance 1 spatial locality.
pub struct HilbertCurve;

impl HilbertCurve {
    /// Convert 1D distance `d` to 2D coordinates `(x, y)` on an `n` x `n` grid.
    /// `n` must be a power of 2.
    pub fn d2xy(n: usize, mut d: usize) -> (usize, usize) {
        let mut x = 0;
        let mut y = 0;
        let mut s = 1;
        while s < n {
            let rx = 1 & (d / 2);
            let ry = 1 & (d ^ rx);
            if ry == 0 {
                if rx == 1 {
                    x = s - 1 - x;
                    y = s - 1 - y;
                }
                core::mem::swap(&mut x, &mut y);
            }
            x += s * rx;
            y += s * ry;
            d /= 4;
            s *= 2;
        }
        (x, y)
    }

    /// Convert 2D coordinates `(x, y)` to 1D distance `d` on an `n` x `n` grid.
    ///
    /// MUST reflect against the full grid size `n`, not the shrinking step `s`.
    /// `x`/`y` are full-range coordinates in `[0, n)` for the entire loop (unlike
    /// `d2xy` above, which builds them up incrementally and genuinely is bounded
    /// by `s`), so `s - 1 - x` underflows `usize` whenever `x > s - 1`.
    ///
    /// This has been reverted back to the buggy `s - 1 - x` form twice already,
    /// each time backed by a "verification" that was actually flawed:
    ///   - tools/hilbert_reference_verify.py "verifies" xy2d by round-tripping
    ///     through d2xy in pure Python. Python ints are signed/arbitrary-precision,
    ///     so `s - 1 - x` going negative is not an error there — it just works out
    ///     via Python's native handling of negative operands, silently hiding the
    ///     exact fault that breaks Rust's unsigned `usize`. A round-trip check in
    ///     Python cannot validate unsigned-integer safety in Rust; don't treat it
    ///     as if it can.
    ///   - a debug build (`cargo build`, checked arithmetic — the profile this
    ///     whole project uses) of the `s - 1 - x` version panics immediately:
    ///     `attempt to subtract with overflow` at this line, reproduced live by
    ///     booting virtio_pixel_rs_v3's bootloader_uefi in QEMU against a real
    ///     PXC1 Hilbert-encoded PNG — the exact same image that boots cleanly to
    ///     kernel handoff (`HANDOFF-OK` on COM1) with `n - 1 - x`.
    ///
    /// Before changing this again: rebuild virtio_pixel_rs_v3 for
    /// x86_64-unknown-uefi and boot it in QEMU/OVMF against a real Hilbert PNG
    /// (see SKELETON_PLAN.md Phase 1.9 for the exact recipe). A Python
    /// self-consistency check is not sufficient evidence either way.
    pub fn xy2d(n: usize, mut x: usize, mut y: usize) -> usize {
        let mut d = 0;
        let mut s = n / 2;
        while s > 0 {
            let rx = 1 & (x / s);
            let ry = 1 & (y / s);
            d += s * s * ((3 * rx) ^ ry);
            if ry == 0 {
                if rx == 1 {
                    x = n - 1 - x;
                    y = n - 1 - y;
                }
                core::mem::swap(&mut x, &mut y);
            }
            s /= 2;
        }
        d
    }
}