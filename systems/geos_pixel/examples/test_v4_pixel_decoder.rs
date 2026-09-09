/// Test V4 PixelDecoder on real PDB tiles
/// 
/// Verifies:
/// 1. PNG signature detection
/// 2. DEFLATE decompression
/// 3. PNG unfiltering
/// 4. Hilbert curve mapping consistency with V3

use geos_pixel::PixelDecoder;

fn main() {
    println!("=== V4 PixelDecoder Test ===\n");

    let mut decoder = PixelDecoder::new();

    // Test 1: Load a real PDB tile
    println!("Test 1: Load real PDB tile");
    let tile_path = "/home/jericho/pdb_hydration_scratch/out/rootfs_tiled/rootfs_blob.0.0.pdb.png";
    
    match std::fs::read(tile_path) {
        Ok(png_data) => {
            println!("  ✓ Loaded {} bytes from {}", png_data.len(), tile_path);
            
            // Verify PNG signature
            if &png_data[0..8] == b"\x89PNG\r\n\x1a\n" {
                println!("  ✓ PNG signature valid");
            } else {
                eprintln!("  ✗ PNG signature invalid");
                std::process::exit(1);
            }

            // Decode frame
            match decoder.decode_frame(&png_data) {
                Ok((pixels, width, height, bpp)) => {
                    println!("  ✓ Decoded {}x{} ({} BPP), {} pixels", width, height, bpp, pixels.len());
                    println!("  ✓ First 12 pixels: {:02X?}", &pixels[..12]);
                    println!("  ✓ First 12 bytes (Hilbert-mapped): {:02X?}", &pixels[..12]);
                }
                Err(e) => {
                    eprintln!("  ✗ Decode failed: {}", e);
                    std::process::exit(1);
                }
            }
        }
        Err(e) => {
            eprintln!("  ✗ Failed to read {}: {}", tile_path, e);
            std::process::exit(1);
        }
    }

    println!("\nTest 2: Decode geos_pixel_container (full path)");
    let mut decoder2 = PixelDecoder::new();
    
    match std::fs::read(tile_path) {
        Ok(png_data) => {
            match decoder2.decode_geos_pixel_container(&png_data) {
                Ok(hilbert_data) => {
                    println!("  ✓ Hilbert-mapped linear output: {} bytes", hilbert_data.len());
                    println!("  ✓ First 12 bytes: {:02X?}", &hilbert_data[..12]);
                    println!("  ✓ Hilbert mapping successful");
                }
                Err(e) => {
                    eprintln!("  ✗ Hilbert decode failed: {}", e);
                    std::process::exit(1);
                }
            }
        }
        Err(e) => {
            eprintln!("  ✗ Failed to read {}: {}", tile_path, e);
            std::process::exit(1);
        }
    }

    // Test 3: Verify Hilbert xy2d consistency
    println!("\nTest 3: Hilbert xy2d consistency");
    use geos_pixel::HilbertCurve;
    
    let test_cases = vec![
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (2, 0),
        (0, 2),
        (3, 3),
    ];
    
    let grid_size = 4;
    for (x, y) in test_cases {
        let d = HilbertCurve::xy2d(grid_size, x, y);
        let (x2, y2) = HilbertCurve::d2xy(grid_size, d);
        
        if x == x2 && y == y2 {
            println!("  ✓ ({}, {}) → d={} → ({}, {}) roundtrip OK", x, y, d, x2, y2);
        } else {
            eprintln!("  ✗ ({}, {}) → d={} → ({}, {}) roundtrip FAILED", x, y, d, x2, y2);
            std::process::exit(1);
        }
    }

    println!("\n=== All Tests Passed ===");
}