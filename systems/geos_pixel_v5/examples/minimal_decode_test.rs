// minimal_decode_test.rs - Minimal test to debug PDB decoding
//
// Bypasses the tiled layer to test core PDB decoder directly.

use geos_pixel_v5::pdb::PdbDecoder;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Minimal PDB Decoding Test ===\n");

    let path = PathBuf::from("/tmp/pdb_tiled_test/test_data.0.0.pdb.png");
    println!("Loading: {}", path.display());

    let mut decoder = PdbDecoder::load_png(&path)?;
    println!("✓ PNG loaded");

    decoder.decode_header()?;
    println!("✓ Header decoded");

    // Try decode_first_table
    let data = decoder.decode_first_table()?;
    println!("✓ First table decoded: {} bytes", data.len());

    // Verify pattern (first 16 bytes should be 0,1,2,...,15)
    println!("First 16 bytes: {:?}", &data[..16]);

    if data.len() > 0 {
        let first = data[0];
        let second = data[1];
        let last = data[data.len() - 1];

        if first == 0 && second == 1 && last == 255 {
            println!("✓ Pattern looks correct");
        } else {
            println!("✗ Pattern check failed: [0]={}, [1]={}, [last]={}", first, second, last);
        }
    }

    Ok(())
}