/// Encode a large file as tiled PDB format
///
/// Usage: cargo run --release --example tiled_encoder --input rootfs.ext4 --output-dir rootfs_tiles --table-name rootfs_blob --tile-size 4096
///
/// This encodes a file across multiple PNG tiles, suitable for V4 boot rootfs.

use std::env;
use std::path::PathBuf;
use geos_pixel::pdb::{
    PdbEncoder, PdbError, TableMetadata, BoundingBox, HEADER_SIZE, TileGridConfig,
    TiledPdbEncoder, TiledPdbHeader,
};
use std::fs;

fn main() {
    let args: Vec<String> = env::args().collect();
    
    if args.len() < 7 {
        eprintln!("Usage: {} --input <file> --output-dir <dir> --table-name <name> --tile-size <size>", args[0]);
        eprintln!("Example: {} --input rootfs.ext4 --output-dir rootfs_tiles --table-name rootfs_blob --tile-size 4096", args[0]);
        std::process::exit(1);
    }
    
    let mut input_path = None;
    let mut output_dir = None;
    let mut table_name = None;
    let mut tile_size = 4096u32;
    
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--input" => {
                input_path = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--table-name" => {
                table_name = Some(args[i + 1].clone());
                i += 2;
            }
            "--tile-size" => {
                tile_size = match args[i + 1].parse::<u32>() {
                    Ok(s) if s.is_power_of_two() => s,
                    _ => {
                        eprintln!("✗ Tile size must be a power of 2");
                        std::process::exit(1);
                    }
                };
                i += 2;
            }
            _ => {
                eprintln!("Unknown argument: {}", args[i]);
                std::process::exit(1);
            }
        }
    }
    
    let input_path = input_path.unwrap();
    let output_dir = output_dir.unwrap();
    let table_name = table_name.unwrap();
    
    println!("=== Tiled PDB Encoder ===");
    println!("Input:      {}", input_path.display());
    println!("Output dir: {}", output_dir.display());
    println!("Table:      {}", table_name);
    println!("Tile size:  {}x{}", tile_size, tile_size);
    
    // Create output directory
    if let Err(e) = fs::create_dir_all(&output_dir) {
        eprintln!("✗ Failed to create output dir: {}", e);
        std::process::exit(1);
    }
    
    // Read input file
    let data = match fs::read(&input_path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("✗ Failed to read input: {}", e);
            std::process::exit(1);
        }
    };
    
    println!("Data size:  {} bytes", data.len());
    
    // Calculate logical dimensions (assuming square)
    let triplets_needed = (data.len() + 2) / 3;
    let logical_side = (triplets_needed as f64).sqrt().ceil() as u32 + HEADER_SIZE as u32;
    
    // Create tile grid config
    let tile_config = match TileGridConfig::new(tile_size, logical_side, logical_side) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("✗ Invalid tile config: {:?}", e);
            std::process::exit(1);
        }
    };
    
    println!("Tile grid:   {}x{} ({} total tiles)", 
        tile_config.tiles_per_row,
        tile_config.tiles_per_col,
        tile_config.total_tiles);
    
    // Create tiled header
    let mut header = TiledPdbHeader::new(tile_config.clone());
    
    // Add table metadata
    let bbox = BoundingBox {
        x_min: 0,
        y_min: HEADER_SIZE as u32,
        x_max: tile_size - 1,
        y_max: tile_size - 1,
    };
    
    let metadata = TableMetadata::new(
        &table_name,
        bbox,
        data.len() as u32, // row_count for blob-table
        1,                 // row_length for blob-table
    );

    if let Err(e) = header.add_table(metadata) {
        eprintln!("✗ Failed to add table: {:?}", e);
        std::process::exit(1);
    }
    
    // Create encoder
    let mut encoder = match TiledPdbEncoder::new(output_dir.to_str().unwrap(), header) {
        Ok(e) => e,
        Err(e) => {
            eprintln!("✗ Failed to create encoder: {:?}", e);
            std::process::exit(1);
        }
    };
    
    // Encode table across tiles
    println!("Encoding...");
    match encoder.encode_table(&table_name, &data) {
        Ok(_) => println!("✓ Encoded across {} tiles", tile_config.total_tiles),
        Err(e) => {
            eprintln!("✗ Failed to encode: {:?}", e);
            std::process::exit(1);
        }
    }
    
    // Save header (tiles.json)
    match encoder.save_header() {
        Ok(_) => println!("✓ Saved tiles.json"),
        Err(e) => {
            eprintln!("✗ Failed to save header: {:?}", e);
            std::process::exit(1);
        }
    }
    
    println!("\n=== Complete ===");
    println!("Tiles directory: {}", output_dir.display());
    println!("Tiles manifest:  {}", output_dir.join("tiles.json").display());
}