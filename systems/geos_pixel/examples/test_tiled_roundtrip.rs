// test_tiled_roundtrip.rs - Tests Phase 2 Tiled Encoding/Decoding
//
// Verifies that large data can be split across multiple tile frames,
// encoded, saved, loaded, and decoded back to the original bytes.
//
// Usage:
//   cargo run --example test_tiled_roundtrip

use geos_pixel::pdb::{
    TiledPdbDecoder, TiledPdbEncoder, TiledPdbHeader, TileGridConfig,
};

use std::path::PathBuf;
use std::fs;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Phase 2 Tiled Encoding/Decoding Roundtrip Test ===\n");

    // Create a test dataset larger than a single tile can hold
    // Each tile at 1024x1024 holds 3MB (1024*1024*3)
    // We'll create 2.5 tiles worth of data to test partial tiles
    let tile_size = 1024u32;
    let tile_capacity = (tile_size * tile_size * 3) as usize; // 3MB per tile

    let data_len = (tile_capacity as f64 * 2.5) as usize;
    let mut test_data = vec![0u8; data_len];

    // Fill with a known pattern for verification
    for i in 0..data_len {
        test_data[i] = (i % 256) as u8;
    }

    println!("Test data size: {} bytes (2.5 tiles)", data_len);

    // Create tile grid configuration
    let logical_size = tile_size * 4; // 4x4 logical space, will use ~2.5 tiles
    let tile_config = TileGridConfig::new(tile_size, logical_size, logical_size)?;

    println!(
        "Tile config: {} tiles per row, {} tiles per col",
        tile_config.tiles_per_row,
        tile_config.tiles_per_col
    );

    // Create output directory
    let base_path = PathBuf::from("/tmp/pdb_tiled_test");
    fs::create_dir_all(&base_path)?;
    println!("Output directory: {}", base_path.display());

    // Create tiled header
    let header = TiledPdbHeader::new(tile_config.clone());

    // Encode test data into tiles
    println!("\n=== ENCODING ===");
    let mut encoder = TiledPdbEncoder::new(&base_path.to_string_lossy(), header)?;
    encoder.encode_table("test_data", &test_data)?;

    // Save the tiled header
    encoder.save_header()?;

    println!("\n=== DECODING ===");
    // Create decoder
    let mut decoder = TiledPdbDecoder::new(&base_path.to_string_lossy())?;

    // Load header
    decoder.manager.load_header()?;

    // Decode table
    let decoded_data = decoder.decode_table("test_data")?;

    println!("\n=== VERIFICATION ===");
    // Verify byte count
    if decoded_data.len() != data_len {
        eprintln!(
            "FAIL: Byte count mismatch. Expected {}, got {}",
            data_len,
            decoded_data.len()
        );
        std::process::exit(1);
    }
    println!("✓ Byte count matches: {} bytes", decoded_data.len());

    // Verify pattern
    let mut mismatches = 0;
    for i in 0..data_len {
        if decoded_data[i] != test_data[i] {
            mismatches += 1;
            if mismatches <= 5 {
                eprintln!(
                    "Mismatch at byte {}: expected {}, got {}",
                    i, test_data[i], decoded_data[i]
                );
            }
        }
    }

    if mismatches > 0 {
        eprintln!("FAIL: {} byte mismatches found", mismatches);
        std::process::exit(1);
    }

    println!("✓ Pattern verified: All {} bytes match perfectly", data_len);

    // Cleanup
    println!("\nCleanup test files...");
    for entry in fs::read_dir(&base_path)? {
        let entry = entry?;
        fs::remove_file(entry.path())?;
    }
    fs::remove_dir(&base_path)?;
    println!("✓ Cleanup complete");

    println!("\n=== SUCCESS ===");
    println!("Phase 2 tiled encoding/decoding round-trip verified!");
    println!("Data split across 3 tiles (2 full + 1 partial) encoded/decoded perfectly.");

    Ok(())
}