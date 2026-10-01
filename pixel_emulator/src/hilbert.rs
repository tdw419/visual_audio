//! Hilbert Curve Coordinate Mapping
//!
//! Single source of truth for Hilbert curve math used across pixel_emulator.
//! Ported from tools/encode_spatial_container.py (precompute_hilbert_lut).
//!
//! Correct Hilbert curve mapping used by spatial containers.

/// Map distance d along Hilbert curve to (x, y) coordinates on n×n grid.
///
/// # Arguments
/// * `n` - Grid dimension (must be power of 2)
/// * `d` - Distance along curve (0 ≤ d < n²)
///
/// # Returns
/// (x, y) coordinates on the grid
pub fn hilbert_d2xy(n: u32, d: u64) -> (u32, u32) {
    let mut x: u32 = 0;
    let mut y: u32 = 0;
    let mut s: u32 = 1;
    let mut t: u64 = d;

    while s < n {
        let rx = ((t >> 1) & 1) as u32;
        let ry = ((t ^ (rx as u64)) & 1) as u32;

        if ry == 0 {
            if rx == 1 {
                x = s - 1 - x;
                y = s - 1 - y;
            }
            // Swap x and y
            let temp = x;
            x = y;
            y = temp;
        }

        x += s * rx;
        y += s * ry;
        t >>= 2;
        s <<= 1;
    }

    (x, y)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hilbert_d2xy_basic() {
        // Test origin
        let (x, y) = hilbert_d2xy(2, 0);
        assert_eq!((x, y), (0, 0));

        // Test points on 4x4 grid (correct Hilbert sequence)
        let (x, y) = hilbert_d2xy(4, 0);
        assert_eq!((x, y), (0, 0));

        let (x, y) = hilbert_d2xy(4, 1);
        assert_eq!((x, y), (1, 0));

        let (x, y) = hilbert_d2xy(4, 2);
        assert_eq!((x, y), (1, 1));

        let (x, y) = hilbert_d2xy(4, 3);
        assert_eq!((x, y), (0, 1));
    }

    #[test]
    fn test_hilbert_all_points_in_bounds() {
        // All points on 8x8 grid should be in bounds
        for d in 0..64u64 {
            let (x, y) = hilbert_d2xy(8, d);
            assert!(
                x < 8 && y < 8,
                "Out of bounds: d={} -> ({},{})",
                d, x, y
            );
        }
    }

    #[test]
    fn test_hilbert_adjacent_points() {
        // Adjacent distances should be adjacent in space (Hilbert property)
        for d in 0..63 {
            let (x1, y1) = hilbert_d2xy(8, d);
            let (x2, y2) = hilbert_d2xy(8, d + 1);
            let dx = (x1 as i32 - x2 as i32).abs();
            let dy = (y1 as i32 - y2 as i32).abs();
            // Adjacent Hilbert points differ by at most 1 in each coordinate
            assert!(
                dx <= 1 && dy <= 1,
                "Points too far apart: d={}, d+1=({},{})->({},{})",
                d, x1, y1, x2, y2
            );
        }
    }

    #[test]
    fn test_hilbert_unique_points() {
        // All points should be unique
        let mut points = std::collections::HashSet::new();

        for d in 0..64u64 {
            let (x, y) = hilbert_d2xy(8, d);
            let key = (x, y);
            assert!(
                !points.contains(&key),
                "Duplicate coordinate at d={}: ({},{})",
                d, x, y
            );
            points.insert(key);
        }

        assert_eq!(points.len(), 64, "Should have 64 unique points");
    }

    #[test]
    fn test_hilbert_covers_all_pixels() {
        let mut visited = vec![vec![false; 8]; 8];

        for d in 0..64u64 {
            let (x, y) = hilbert_d2xy(8, d);
            visited[x as usize][y as usize] = true;
        }

        // All pixels should be visited exactly once
        for x in 0..8 {
            for y in 0..8 {
                assert!(
                    visited[x as usize][y as usize],
                    "Pixel ({},{}) not visited",
                    x, y
                );
            }
        }
    }

    #[test]
    fn test_hilbert_4096_grid() {
        // Verify that we can handle larger grids
        let (x, y) = hilbert_d2xy(4096, 0);
        assert_eq!((x, y), (0, 0));

        let (x, y) = hilbert_d2xy(4096, 1);
        assert_eq!((x, y), (1, 0));

        let (x, y) = hilbert_d2xy(4096, 2);
        assert_eq!((x, y), (1, 1));

        let (x, y) = hilbert_d2xy(4096, 3);
        assert_eq!((x, y), (0, 1));

        // Test a point in the middle
        let (x, y) = hilbert_d2xy(4096, 1_048_575);
        assert!(x < 4096 && y < 4096);
    }

    #[test]
    fn test_known_points_8x8() {
        // Known sequence from Python implementation
        let expected = [
            (0, 0), (0, 1), (1, 1), (1, 0),
            (2, 0), (3, 0), (3, 1), (2, 1),
            (2, 2), (3, 2), (3, 3), (2, 3),
            (1, 3), (1, 2), (0, 2), (0, 3),
        ];

        for (d, (exp_x, exp_y)) in expected.iter().enumerate() {
            let (x, y) = hilbert_d2xy(8, d as u64);
            assert_eq!(
                (x, y), (*exp_x, *exp_y),
                "Mismatch at d={}: expected ({},{}), got ({},{})",
                d, exp_x, exp_y, x, y
            );
        }
    }
}