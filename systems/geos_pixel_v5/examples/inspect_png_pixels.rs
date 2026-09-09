// inspect_png_pixels.rs - Debug tool to check raw PNG pixel values
//
// Usage:
//   cargo run --example inspect_png_pixels

use image::RgbaImage;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Raw PNG Pixel Inspector ===\n");

    let path = PathBuf::from("/tmp/pdb_tiled_test/test_data.0.0.pdb.png");
    println!("Loading: {}", path.display());

    let canvas = image::open(&path)?.to_rgba8();
    println!("Dimensions: {}x{}", canvas.width(), canvas.height());

    println!("\nFirst row (y=0) - first 50 pixels:");
    for x in 0..50.min(canvas.width()) {
        let pixel = canvas.get_pixel(x, 0);
        println!("  ({:3}, 0) = R,G,B,A = {:3}, {:3}, {:3}, {:3} (hex: {:02X}{:02X}{:02X}{:02X})",
                 x, pixel[0], pixel[1], pixel[2], pixel[3],
                 pixel[0], pixel[1], pixel[2], pixel[3]);
    }

    println!("\nFirst column (x=0) - first 50 pixels:");
    for y in 0..50.min(canvas.height()) {
        let pixel = canvas.get_pixel(0, y);
        println!("  (0, {:3}) = R,G,B,A = {:3}, {:3}, {:3}, {:3}",
                 y, pixel[0], pixel[1], pixel[2], pixel[3]);
    }

    Ok(())
}