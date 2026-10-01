// test_single_tile_roundtrip.rs - Test SINGLE tile encode/decode
//
// Bypasses tiled layer entirely - just test one tile's blob-table semantics.

use geos_pixel::pdb::{PdbConfig, PdbEncoder, PdbDecoder, TableMetadata, BoundingBox, PdbHeader};
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Single Tile Blob-Table Roundtrip Test ===\n");

    // Create test data: 1MB of pattern
    let data_size = 1024 * 1024;
    let mut test_data = vec![0u8; data_size];
    for i in 0..data_size {
        test_data[i] = (i % 256) as u8;
    }
    println!("Test data: {} bytes", data_size);

    // Calculate bbox for blob-table
    // blob-table semantics: row_length=1, row_count=byte_count
    // Each row is 1 byte, needs 1 pixel triplet (RGB = 3 bytes)
    // So row_count = byte_count, and we need ceil(byte_count / 3) pixels per row
    let tile_size = 1024u32;
    let byte_count = data_size as u32;
    let pixels_needed = (byte_count as f64 / 3.0).ceil() as u32;
    let bbox_height = (pixels_needed as f64 / tile_size as f64).ceil() as u32;

    println!("Tile size: {}", tile_size);
    println!("Pixels needed: {}", pixels_needed);
    println!("Bbox height: {}", bbox_height);

    // Create blob-table metadata
    let name_bytes = {
        let mut bytes = [0u8; 16];
        bytes[..5].copy_from_slice("blob\0".as_bytes());
        bytes
    };

    let metadata = TableMetadata {
        name: name_bytes,
        bbox: BoundingBox {
            x_min: 0,
            y_min: 1, // Skip row 0 for header
            x_max: tile_size - 1,
            y_max: bbox_height, // Full height from y=1
        },
        row_length: 1,
        row_count: byte_count,
    };

    let mut header = PdbHeader::new();
    header.add_table(metadata)?;

    println!("\n=== ENCODING ===");
    let config = PdbConfig::new(tile_size as usize, tile_size as usize)?;
    let mut encoder = PdbEncoder::new(config, header);
    encoder.encode_header()?;
    encoder.encode_table(0, &test_data)?;
    println!("Data encoded");

    let output_path = PathBuf::from("/tmp/test_single_tile.pdb.png");
    encoder.save_png(&output_path)?;
    println!("Saved to: {}", output_path.display());

    println!("\n=== DECODING ===");
    let mut decoder = PdbDecoder::load_png(&output_path)?;
    println!("PNG loaded");

    decoder.decode_header()?;
    println!("Header decoded");

    let decoded_data = decoder.decode_first_table()?;
    println!("Data decoded: {} bytes", decoded_data.len());

    println!("\n=== VERIFICATION ===");
    if decoded_data.len() != data_size {
        eprintln!("FAIL: Byte count mismatch. Expected {}, got {}", data_size, decoded_data.len());
        std::process::exit(1);
    }
    println!("✓ Byte count matches");

    // Verify pattern
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

    println!("✓ Pattern verified: All {} bytes match", data_size);

    Ok(())
}