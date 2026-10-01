// extract_v4_pdb.rs - V4 PDB Blob Extractor
//
// Decodes a table from a PDB frame and writes the raw bytes to disk.
// This proves the round-trip works: file -> PDB -> file (byte-identical).
//
// Usage:
//   cargo run --example extract_v4_pdb -- <input.pdb.png> <table_name> <output_file>
//
// Example:
//   cargo run --example extract_v4_pdb -- /tmp/hello.pdb.png hello /tmp/out.img

use geos_pixel::pdb::{PdbDecoder, PdbError, PdbResult};
use std::fs;
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 4 {
        eprintln!("Usage: extract_v4_pdb <input.pdb.png> <table_name> <output_file>");
        eprintln!("");
        eprintln!("Example:");
        eprintln!("  cargo run --example extract_v4_pdb -- /tmp/hello.pdb.png hello /tmp/out.img");
        eprintln!("");
        eprintln!("Arguments:");
        eprintln!("  input.pdb.png  Input PDB PNG file");
        eprintln!("  table_name     Name of table to extract");
        eprintln!("  output_file    Path to write extracted binary data");
        std::process::exit(1);
    }

    let pdb_path = &args[1];
    let table_name = &args[2];
    let output_path = &args[3];

    println!("V4 PDB Blob Extractor");
    println!("=====================");
    println!("Input: {}", pdb_path);
    println!("Table: {}", table_name);
    println!("Output: {}", output_path);
    println!("");

    // Load PDB frame
    let mut decoder = match PdbDecoder::load_png(pdb_path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("Failed to load PDB: {:?}", e);
            std::process::exit(1);
        }
    };

    // Decode header
    match decoder.decode_header() {
        Ok(header) => {
            println!("PDB Header:");
            println!("  Version: {}", header.version);
            println!("  Table count: {}", header.table_count);
            println!("");

            for table in &header.tables {
                let name = std::str::from_utf8(&table.name)
                    .unwrap_or("")
                    .trim_end_matches('\0');
                let bytes = (table.row_count * table.row_length) as usize;
                println!(
                    "  - '{}': {} bytes ({}, {} to {}, {})",
                    name, bytes, table.bbox.x_min, table.bbox.y_min,
                    table.bbox.x_max, table.bbox.y_max
                );
            }
            println!("");
        }
        Err(e) => {
            eprintln!("Failed to decode header: {:?}", e);
            std::process::exit(1);
        }
    }

    // Decode table data
    let table_data = match decoder.decode_table(table_name) {
        Ok(data) => data,
        Err(e) => {
            eprintln!("Failed to decode table '{}': {:?}", table_name, e);
            std::process::exit(1);
        }
    };

    println!("Extracted {} bytes from table '{}'", table_data.len(), table_name);

    // Write to output file
    if let Err(e) = fs::write(output_path, &table_data) {
        eprintln!("Failed to write output: {}", e);
        std::process::exit(1);
    }

    println!("Wrote: {}", output_path);
    println!("");
    println!("SUCCESS: Table extracted successfully");
}