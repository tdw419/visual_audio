// Test WindowSystem::render() on host, no DRM needed
#[cfg(feature = "gpu")]
fn main() {
    let ws = geos_pixel_v5::window::WindowSystem::new().expect("WindowSystem init failed");
    println!("GPU adapter: {}", ws.adapter_name());
    println!("Adapter features: {:?}", ws.adapter_features());

    let mut mem = vec![0i32; geos_pixel_v5::window::MEM_WORDS];
    geos_pixel_v5::window::seed_wcb_state(&mut mem);
    ws.write_memory(&mem);

    // Render once
    let img = ws.render();
    println!("Render output size: {} bytes (expected: {})", img.len(), geos_pixel_v5::window::SCREEN_W * geos_pixel_v5::window::SCREEN_H * 4);

    // Check if all bytes are zero
    let nonzero = img.iter().filter(|&&b| b != 0).count();
    println!("Non-zero bytes in output: {} / {}", nonzero, img.len());

    // Sample pixels from each window region
    let sample_pixels = [(50, 50), (100, 100), (20, 20), (400, 300)];
    for (x, y) in sample_pixels {
        let p = ws.pixel(&img, x, y);
        println!("Pixel ({},{}) = R:{} G:{} B:{} A:{}", x, y, p[0], p[1], p[2], p[3]);
    }
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}
