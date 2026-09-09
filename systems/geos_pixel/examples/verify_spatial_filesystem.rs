// verify_spatial_filesystem.rs - End-to-end verification of spatial filesystem
//
// This demonstrates the complete pipeline:
// 1. Decode file_metadata.pdb.png to find offset for a path
// 2. Load tiled rootfs blob tiles (decode entire table)
// 3. Extract bytes from the tiled blob at that offset
// 4. Verify against guestfish-downloaded reference
//
// Usage:
//   cargo run --example verify_spatial_filesystem -- \
//     <metadata_png> <tiled_rootfs_dir> <test_path> <reference_file>

use geos_pixel::pdb::{decoder::PdbDecoder, tiled::TiledPdbDecoder, PdbError, PdbResult};
use std::path::PathBuf;

#[derive(Clone, Debug)]
struct FileMetadataEntry {
    path: String,
    offset: u64,
    size: u32,
    mode: u16,
    file_type: u16,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 5 {
        eprintln!("Usage: verify_spatial_filesystem <metadata_png> <tiled_rootfs_dir> <test_path> <reference_file>");
        eprintln!("\nExample:");
        eprintln!("  cargo run --example verify_spatial_filesystem -- \\");
        eprintln!("    /home/jericho/pdb_hydration_scratch/out/file_metadata.pdb.png \\");
        eprintln!("    /home/jericho/pdb_hydration_scratch/out/rootfs_tiled \\");
        eprintln!("    /etc/passwd \\");
        eprintln!("    /tmp/guestfish_passwd");
        std::process::exit(1);
    }

    let metadata_path = PathBuf::from(&args[1]);
    let tiled_rootfs_dir = PathBuf::from(&args[2]);
    let test_path = &args[3];
    let reference_path = PathBuf::from(&args[4]);

    println!("=== Spatial Filesystem Verification ===\n");
    println!("Metadata table: {}", metadata_path.display());
    println!("Tiled rootfs: {}", tiled_rootfs_dir.display());
    println!("Test path: {}", test_path);
    println!("Reference: {}", reference_path.display());
    println!();

    // Step 1: Decode metadata table and find the target path
    println!("Step 1: Searching metadata table for '{}'...", test_path);

    let mut metadata_decoder = PdbDecoder::load_png(metadata_path.clone())?;
    let metadata_header = metadata_decoder.decode_header()?;

    println!("  Loaded and decoded metadata PNG");

    // Find the file_metadata table and extract row_length
    let row_length = metadata_header
        .tables
        .iter()
        .find(|t| {
            let name_str = std::str::from_utf8(&t.name)
                .unwrap_or("")
                .trim_end_matches('\0');
            name_str == "file_metadata"
        })
        .ok_or_else(|| PdbError::IoError("file_metadata table not found".to_string()))?
        .row_length;

    // Decode the entire table into memory (drops the borrow of metadata_decoder)
    let table_bytes = metadata_decoder.decode_table("file_metadata")?;
    println!("  Read {} bytes of table data", table_bytes.len());

    // Parse rows to find our target path
    let target_entry = find_path_in_table(&table_bytes, test_path, row_length as usize)?;

    let entry = target_entry.ok_or_else(|| {
        eprintln!("  ✗ Path '{}' not found in metadata table", test_path);
        PdbError::IoError(format!("Path '{}' not found", test_path))
    })?;

    println!("  ✓ Found entry:");
    println!("    Offset: {}", entry.offset);
    println!("    Size: {} bytes", entry.size);
    println!("    Mode: 0{:o}", entry.mode);
    println!("    File type: {}", entry.file_type);

    // Step 2: Load tiled rootfs blob and extract at offset
    println!(
        "\nStep 2: Extracting {} bytes from tiled blob at offset {}...",
        entry.size, entry.offset
    );

    let mut tiled_decoder = TiledPdbDecoder::new(tiled_rootfs_dir.to_str().unwrap())?;

    let offset = entry.offset as usize;
    let size = entry.size as usize;

    // Decode entire tiled blob (for verification; in real use we'd want random access)
    println!("  Loading full tiled rootfs blob into memory...");
    let full_blob = tiled_decoder.decode_table("rootfs_blob")?;
    println!("  Loaded {} bytes from tiled blob", full_blob.len());

    // Extract the slice we need
    let end = (offset + size).min(full_blob.len());
    let extracted_data = &full_blob[offset..end];

    println!(
        "  ✓ Extracted {} bytes from tiled blob",
        extracted_data.len()
    );

    // Step 3: Compare with reference
    println!("\nStep 3: Comparing against reference file...");

    let reference_data = std::fs::read(&reference_path)?;

    if extracted_data.len() != reference_data.len() {
        eprintln!(
            "  ✗ Size mismatch: extracted {} vs reference {}",
            extracted_data.len(),
            reference_data.len()
        );
        std::process::exit(1);
    }

    if extracted_data != reference_data.as_slice() {
        eprintln!("  ✗ Content mismatch!");
        eprintln!("  First 100 bytes of extracted:");
        for i in 0..100.min(extracted_data.len()) {
            print!("{:02x} ", extracted_data[i]);
        }
        println!();
        eprintln!("  First 100 bytes of reference:");
        for i in 0..100.min(reference_data.len()) {
            print!("{:02x} ", reference_data[i]);
        }
        println!();
        std::process::exit(1);
    }

    println!("  ✓ Content matches reference byte-for-byte!");

    println!("\n=== SUCCESS ===");
    println!("Spatial filesystem verification passed!");
    println!("The complete pipeline works:");
    println!("  1. Query file_metadata table → offset + size");
    println!("  2. Read from tiled rootfs blob at offset");
    println!("  3. Get byte-identical content back");

    Ok(())
}

fn find_path_in_table(
    table_data: &[u8],
    target_path: &str,
    row_length: usize,
) -> PdbResult<Option<FileMetadataEntry>> {
    let row_count = table_data.len() / row_length;

    for row_idx in 0..row_count {
        let row_start = row_idx * row_length;
        let row_end = row_start + row_length;
        let row = &table_data[row_start..row_end];

        // Extract path (first 256 bytes, NUL-terminated)
        let path_end = row.iter().position(|&b| b == 0).unwrap_or(256);
        let path = String::from_utf8_lossy(&row[..path_end]).to_string();

        if path == target_path {
            // Extract offset (bytes 256-263, little-endian u64)
            let offset = u64::from_le_bytes([
                row[256], row[257], row[258], row[259], row[260], row[261], row[262], row[263],
            ]);

            // Extract size (bytes 264-267, little-endian u32)
            let size = u32::from_le_bytes([row[264], row[265], row[266], row[267]]);

            // Extract mode (bytes 268-269, little-endian u16)
            let mode = u16::from_le_bytes([row[268], row[269]]);

            // Extract file type (bytes 278-279, little-endian u16)
            let file_type = u16::from_le_bytes([row[278], row[279]]);

            return Ok(Some(FileMetadataEntry {
                path,
                offset,
                size,
                mode,
                file_type,
            }));
        }
    }

    Ok(None)
}