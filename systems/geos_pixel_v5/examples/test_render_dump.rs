use geos_pixel_v5::window::{self, WindowSystem};
fn main() {
    let ws = WindowSystem::new().expect("init");
    let mut mem = vec![0i32; window::MEM_WORDS];
    window::seed_wcb_state(&mut mem);
    ws.write_memory(&mem);
    let img = ws.render();
    let nonzero = img.iter().filter(|&&b| b != 0).count();
    println!("bytes={} nonzero={}", img.len(), nonzero);
    let mut hist = std::collections::HashMap::new();
    for c in img.chunks_exact(4) {
        *hist.entry((c[0], c[1], c[2])).or_insert(0) += 1;
    }
    let mut v: Vec<_> = hist.into_iter().collect();
    v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    for (color, n) in v.iter().take(10) {
        println!("{:?} x {}", color, n);
    }
}
