// compile_v4_1_tiled.rs - V4.1 Tiled PDB Compiler
//
// Usage:
//   cargo run --example compile_v4_1_tiled <output_base> <tile_size> <name> <file_path>
//   Example: cargo run --example compile_v4_1_tiled /tmp/rootfs 4096 rootfs /path/to/rootfs.raw

use geos_pixel_v5::pdb::{TiledPdbEncoder, TiledPdbHeader, TileGridConfig};
use std::path::PathBuf;
use std::fs;
use std::env;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.len() != 5 {
        eprintln!("Usage: {} <output_base> <tile_size> <name> <file_path>", args[0]);
        eprintln!("Example: {} /tmp/rootfs 4096 rootfs /path/to/rootfs.raw", args[0]);
        std::process::exit(1);
    }

    let output_base = &args[1];
    let tile_size: u32 = args[2].parse()?;
    let table_name = &args[3];
    let file_path = PathBuf::from(&args[4]);

    println!("=== V4.1 Tiled PDB Compiler ===\n");
    println!("Output base: {}", output_base);
    println!("Tile size: {}x{}", tile_size, tile_size);
    println!("Table name: {}", table_name);
    println!("Input file: {}\n", file_path.display());

    // Read input file
    let file_data = fs::read(&file_path)?;
    println!("File size: {} bytes ({} MB)", file_data.len(), file_data.len() / 1024 / 1024);

    // Create output directory
    let base_path = PathBuf::from(output_base);
    fs::create_dir_all(&base_path)?;

    // Calculate tile grid
    // For blob-table semantics: each byte becomes a pixel triplet
    // We need ceil(byte_count / 3) pixels
    let data_pixels = ((file_data.len() as f64) / 3.0).ceil() as u32;
    let logical_width = tile_size.max((data_pixels as f64 / (tile_size as f64)).ceil() as u32);
    let logical_height = ((data_pixels as f64) / (tile_size as f64)).ceil() as u32;

    let tile_config = TileGridConfig::new(tile_size, logical_width, logical_height)?;
    println!("Tile grid: {}x{} tiles ({} total)", tile_config.tiles_per_row, tile_config.tiles_per_col, tile_config.total_tiles);

    // Create tiled header
    let header = TiledPdbHeader::new(tile_config.clone());

    // Encode
    println!("\n=== ENCODING ===");
    let mut encoder = TiledPdbEncoder::new(&base_path.to_string_lossy(), header)?;
    encoder.encode_table(table_name, &file_data)?;
    encoder.save_header()?;

    println!("\n=== COMPLETE ===");
    println!("Header saved to: {}/tiles.json", output_base);
    println!("Tiles saved to: {}/*.{{tile_x}}.{{tile_y}}.pdb.png", output_base);

    Ok(())
}