/// Encode a single file (kernel/initramfs) as a PDB frame
///
/// Usage: cargo run --example encode_file_to_pdb --input vmlinuz --output kernel.pdb.png --table-name kernel
///
/// This encodes a file as a blob-table (row_length=1, row_count=file_size)
/// suitable for V4 boot kernel and initramfs components.

use std::env;
use std::path::PathBuf;
use geos_pixel_v5::pdb::{PdbConfig, PdbEncoder, PdbHeader, TableMetadata, BoundingBox, HEADER_SIZE};

fn main() {
    let args: Vec<String> = env::args().collect();
    
    if args.len() < 5 {
        eprintln!("Usage: {} --input <file> --output <pdb.png> --table-name <name>", args[0]);
        eprintln!("Example: {} --input vmlinuz --output kernel.pdb.png --table-name kernel", args[0]);
        std::process::exit(1);
    }
    
    let mut input_path = None;
    let mut output_path = None;
    let mut table_name = None;
    
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--input" => {
                input_path = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--output" => {
                output_path = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--table-name" => {
                table_name = Some(args[i + 1].clone());
                i += 2;
            }
            _ => {
                eprintln!("Unknown argument: {}", args[i]);
                std::process::exit(1);
            }
        }
    }
    
    let input_path = input_path.unwrap();
    let output_path = output_path.unwrap();
    let table_name = table_name.unwrap();
    
    println!("=== Encode File to PDB ===");
    println!("Input:  {}", input_path.display());
    println!("Output: {}", output_path.display());
    println!("Table:  {}", table_name);
    
    // Read input file
    let data = match std::fs::read(&input_path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("✗ Failed to read input: {}", e);
            std::process::exit(1);
        }
    };
    
    println!("Size:   {} bytes", data.len());
    
    // Calculate grid size needed
    let byte_count = data.len();
    let triplets_needed = (byte_count + 2) / 3;
    let mut grid_size = 2u32;
    while ((grid_size * grid_size) as usize) < triplets_needed {
        grid_size *= 2;
    }
    
    // Account for header region
    let height_needed = HEADER_SIZE as u32 + ((triplets_needed as u32 + grid_size - 1) / grid_size);
    if height_needed > grid_size {
        grid_size = 2u32;
        while grid_size < height_needed {
            grid_size *= 2;
        }
    }
    
    println!("Grid:   {}x{}", grid_size, grid_size);
    
    // Create PDB config
    let config = match PdbConfig::new(grid_size as usize, grid_size as usize) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("✗ Invalid config: {:?}", e);
            std::process::exit(1);
        }
    };
    
    // Create header with blob-table semantics
    let mut header = PdbHeader::new();
    let bbox = BoundingBox {
        x_min: 0,
        y_min: HEADER_SIZE as u32,
        x_max: grid_size - 1,
        y_max: grid_size - 1,
    };
    
    let metadata = TableMetadata::new(
        &table_name,
        bbox,
        byte_count as u32,  // row_count = byte_count (blob-table semantics)
        1,                  // row_length = 1 (blob-table semantics)
    );
    
    header.add_table(metadata).expect("Failed to add table");
    
    // Create encoder
    let mut encoder = PdbEncoder::new(config, header);
    
    // Encode header
    match encoder.encode_header() {
        Ok(_) => println!("✓ Header encoded"),
        Err(e) => {
            eprintln!("✗ Failed to encode header: {:?}", e);
            std::process::exit(1);
        }
    }
    
    // Encode table (index 0 for single-table PDB)
    match encoder.encode_table(0, &data) {
        Ok(_) => println!("✓ Data encoded"),
        Err(e) => {
            eprintln!("✗ Failed to encode data: {:?}", e);
            std::process::exit(1);
        }
    }
    
    // Save PNG
    match encoder.save_png(&output_path) {
        Ok(_) => println!("✓ Saved to {}", output_path.display()),
        Err(e) => {
            eprintln!("✗ Failed to save PNG: {:?}", e);
            std::process::exit(1);
        }
    }
    
    println!("\n=== Complete ===");
}