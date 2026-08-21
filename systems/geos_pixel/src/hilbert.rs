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
    pub fn xy2d(n: usize, mut x: usize, mut y: usize) -> usize {
        let mut d = 0;
        let mut s = n / 2;
        while s > 0 {
            let rx = 1 & (x / s);
            let ry = 1 & (y / s);
            d += s * s * ((3 * rx) ^ ry);
            if ry == 0 {
                if rx == 1 {
                    x = s - 1 - x;
                    y = s - 1 - y;
                }
                core::mem::swap(&mut x, &mut y);
            }
            s /= 2;
        }
        d
    }
}
