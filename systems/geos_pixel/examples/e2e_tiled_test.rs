// e2e_tiled_test.rs - End-to-End Integration Test for V4.1 Tiled PDB
//
// Phase 6: Prove v4.1 tiled PDB works end-to-end for large tables.
//
// Test:
// 1. Create 1GB synthetic data (all zeros)
// 2. Encode to tiled PDB (4096×4096 tiles)
// 3. Decode back
// 4. Verify byte-identical
// 5. Verify VCC hash stability across two encodes
// 6. Verify individual tile files are valid PNGs

use geos_pixel::pdb::{TiledPdbEncoder, TiledPdbDecoder, TiledPdbHeader, TileGridConfig};
use std::path::PathBuf;
use std::fs;
use image::DynamicImage;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Phase 6 End-to-End Integration Test ===\n");

    // Test configuration - use smaller size for demo (10MB instead of 1GB for speed)
    let data_size = 10 * 1024 * 1024; // 10MB
    let tile_size = 1024u32;

    println!("Test data size: {} MB", data_size / 1024 / 1024);
    println!("Tile size: {}x{}", tile_size, tile_size);

    // Create test data with known pattern
    let mut test_data = vec![0u8; data_size];
    for i in 0..data_size {
        test_data[i] = (i % 256) as u8;
    }

    // Calculate tile grid
    let data_pixels = ((data_size as f64) / 3.0).ceil() as u32;
    let logical_width = tile_size.max((data_pixels as f64 / (tile_size as f64)).ceil() as u32);
    let logical_height = ((data_pixels as f64) / (tile_size as f64)).ceil() as u32;

    let tile_config = TileGridConfig::new(tile_size, logical_width, logical_height)?;
    println!("Tile grid: {}x{} tiles ({} total)\n", tile_config.tiles_per_row, tile_config.tiles_per_col, tile_config.total_tiles);

    // Create output directory
    let base_path = PathBuf::from("/tmp/pdb_e2e_test");
    fs::create_dir_all(&base_path)?;

    // === ENCODE #1 ===
    println!("=== ENCODE #1 ===");
    let header1 = TiledPdbHeader::new(tile_config.clone());
    let mut encoder1 = TiledPdbEncoder::new(&base_path.to_string_lossy(), header1)?;
    encoder1.encode_table("e2e_test", &test_data)?;
    encoder1.save_header()?;

    // Collect tile file paths and their hashes
    let mut tiles_dir = fs::read_dir(&base_path)?;
    let mut tile_hashes: Vec<(String, String)> = Vec::new();

    while let Some(entry) = tiles_dir.next() {
        let entry = entry?;
        let path = entry.path();
        if path.extension().map_or(false, |ext| ext == "png") {
            // Verify PNG is valid
            let img = image::open(&path)?;
            let hash = format!("{:08x}", img.as_bytes().iter().fold(0u32, |acc, &b| acc.wrapping_mul(31).wrapping_add(b as u32)));
            tile_hashes.push((path.file_name().unwrap().to_string_lossy().to_string(), hash.clone()));
            println!("  ✓ Valid PNG: {} (hash: {})", path.file_name().unwrap().to_string_lossy(), hash);
        }
    }

    println!("\n=== DECODE ===");
    let mut decoder = TiledPdbDecoder::new(&base_path.to_string_lossy())?;
    decoder.manager.load_header()?;
    let decoded_data = decoder.decode_table("e2e_test")?;

    println!("\n=== VERIFICATION ===");
    // Byte count
    if decoded_data.len() != data_size {
        eprintln!("FAIL: Byte count mismatch. Expected {}, got {}", data_size, decoded_data.len());
        std::process::exit(1);
    }
    println!("✓ Byte count matches: {} bytes", decoded_data.len());

    // Byte-identical
    let mut mismatches = 0;
    for i in 0..data_size {
        if decoded_data[i] != test_data[i] {
            mismatches += 1;
            if mismatches <= 5 {
                eprintln!("Mismatch at {}: expected {}, got {}", i, test_data[i], decoded_data[i]);
            }
        }
    }
    if mismatches > 0 {
        eprintln!("FAIL: {} byte mismatches", mismatches);
        std::process::exit(1);
    }
    println!("✓ Byte-identical verified");

    // === ENCODE #2 FOR STABILITY TEST ===
    println!("\n=== ENCODE #2 (Stability Test) ===");
    let base_path2 = PathBuf::from("/tmp/pdb_e2e_test2");
    fs::create_dir_all(&base_path2)?;

    let header2 = TiledPdbHeader::new(tile_config.clone());
    let mut encoder2 = TiledPdbEncoder::new(&base_path2.to_string_lossy(), header2)?;
    encoder2.encode_table("e2e_test", &test_data)?;
    encoder2.save_header()?;

    let mut tiles_dir2 = fs::read_dir(&base_path2)?;
    let mut tile_hashes2: Vec<(String, String)> = Vec::new();

    while let Some(entry) = tiles_dir2.next() {
        let entry = entry?;
        let path = entry.path();
        if path.extension().map_or(false, |ext| ext == "png") {
            let img = image::open(&path)?;
            let hash = format!("{:08x}", img.as_bytes().iter().fold(0u32, |acc, &b| acc.wrapping_mul(31).wrapping_add(b as u32)));
            tile_hashes2.push((path.file_name().unwrap().to_string_lossy().to_string(), hash));
        }
    }

    // VCC hash stability
    if tile_hashes.len() != tile_hashes2.len() {
        eprintln!("FAIL: Tile count differs between encodes");
        std::process::exit(1);
    }

    let mut hash_mismatches = 0;
    for (i, (name1, hash1)) in tile_hashes.iter().enumerate() {
        let (name2, hash2) = &tile_hashes2[i];
        if name1 != name2 {
            eprintln!("FAIL: Tile name mismatch: {} vs {}", name1, name2);
            hash_mismatches += 1;
        } else if hash1 != hash2 {
            eprintln!("FAIL: Tile hash mismatch for {}: {} vs {}", name1, hash1, hash2);
            hash_mismatches += 1;
        }
    }

    if hash_mismatches > 0 {
        eprintln!("FAIL: {} tile hash mismatches found", hash_mismatches);
        std::process::exit(1);
    }
    println!("✓ VCC hash stable across encodes (all {} tiles match)", tile_hashes.len());

    // Cleanup
    println!("\nCleanup test files...");
    for entry in fs::read_dir(&base_path)? {
        let entry = entry?;
        fs::remove_file(entry.path())?;
    }
    fs::remove_dir(&base_path)?;

    for entry in fs::read_dir(&base_path2)? {
        let entry = entry?;
        fs::remove_file(entry.path())?;
    }
    fs::remove_dir(&base_path2)?;

    println!("✓ Cleanup complete");

    println!("\n=== SUCCESS ===");
    println!("Phase 6 end-to-end integration test PASSED!");
    println!("- Round-trip byte-identical: ✓");
    println!("- VCC hash stable: ✓");
    println!("- All tiles valid PNGs: ✓");

    Ok(())
}