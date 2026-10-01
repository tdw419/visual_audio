use geos_pixel_v5::pdb::{TileGridConfig, TiledPdbDecoder, TiledPdbEncoder, TiledPdbHeader};
use std::fs;
use std::path::PathBuf;
use sha2::{Digest, Sha256};

fn compute_hash(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    format!("{:x}", hasher.finalize())
}

#[test]
fn test_tiled_e2e_roundtrip() {
    let output_base = "/tmp/tiled_e2e_test";
    let _ = fs::remove_dir_all(output_base); // clean up from previous runs
    fs::create_dir_all(output_base).unwrap();

    let table_name = "test_table";
    // 20MB of synthetic data
    let data_len = 20 * 1024 * 1024;
    let mut data = vec![0u8; data_len];
    for i in 0..data_len {
        data[i] = (i % 251) as u8;
    }

    let original_hash = compute_hash(&data);
    println!("Original data hash: {}", original_hash);

    // We use a small tile size to force multiple tiles
    let tile_size = 512;
    // 512 * 512 * 3 = 786,432 bytes per tile
    // 20MB / 786KB = ~26.6 tiles

    let data_pixels = ((data.len() as f64) / 3.0).ceil() as u32;
    let logical_width = tile_size.max((data_pixels as f64 / (tile_size as f64)).ceil() as u32);
    let logical_height = ((data_pixels as f64) / (tile_size as f64)).ceil() as u32;

    let tile_config = TileGridConfig::new(tile_size, logical_width, logical_height).unwrap();
    let header = TiledPdbHeader::new(tile_config);

    // Encode
    let mut encoder = TiledPdbEncoder::new(output_base, header).unwrap();
    encoder.encode_table(table_name, &data).unwrap();
    encoder.save_header().unwrap();

    // Verify files were created
    let tiles_json = PathBuf::from(format!("{}/tiles.json", output_base));
    assert!(tiles_json.exists());
    
    // Decode
    let mut decoder = TiledPdbDecoder::new(output_base).unwrap();
    let decoded_data = decoder.decode_table(table_name).unwrap();

    assert_eq!(data.len(), decoded_data.len(), "Decoded length mismatch");

    let decoded_hash = compute_hash(&decoded_data);
    println!("Decoded data hash: {}", decoded_hash);

    assert_eq!(original_hash, decoded_hash, "Hash mismatch after round trip");
}
