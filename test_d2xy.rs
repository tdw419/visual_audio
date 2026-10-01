mod hilbert {
    pub struct HilbertCurve;
    impl HilbertCurve {
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
    }
}
fn main() {
    println!("{:?}", hilbert::HilbertCurve::d2xy(4096, 0));
    println!("{:?}", hilbert::HilbertCurve::d2xy(4096, 1158));
}
