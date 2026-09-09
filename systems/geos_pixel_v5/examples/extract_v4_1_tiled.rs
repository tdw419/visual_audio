// extract_v4_1_tiled.rs - V4.1 Tiled PDB Extractor
//
// Usage:
//   cargo run --example extract_v4_1_tiled <input_base> <table_name> <output_file>
//   Example: cargo run --example extract_v4_1_tiled /tmp/rootfs rootfs /tmp/out.raw

use geos_pixel_v5::pdb::TiledPdbDecoder;
use std::path::PathBuf;
use std::fs;
use std::env;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.len() != 4 {
        eprintln!("Usage: {} <input_base> <table_name> <output_file>", args[0]);
        eprintln!("Example: {} /tmp/rootfs rootfs /tmp/out.raw", args[0]);
        std::process::exit(1);
    }

    let input_base = &args[1];
    let table_name = &args[2];
    let output_path = PathBuf::from(&args[3]);

    println!("=== V4.1 Tiled PDB Extractor ===\n");
    println!("Input base: {}", input_base);
    println!("Table name: {}", table_name);
    println!("Output file: {}\n", output_path.display());

    // Create decoder
    println!("Creating decoder...");
    let mut decoder = TiledPdbDecoder::new(input_base)?;

    // Load header
    println!("Loading header...");
    decoder.manager.load_header()?;

    // Decode table
    println!("Decoding table '{}'...\n", table_name);
    let data = decoder.decode_table(table_name)?;

    // Write output
    println!("Writing {} bytes to {}", data.len(), output_path.display());
    fs::write(&output_path, &data)?;

    println!("\n=== COMPLETE ===");

    Ok(())
}