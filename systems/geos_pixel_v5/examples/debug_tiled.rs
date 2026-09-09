// debug_tiled.rs - Debug tiled blob decoding with detailed output

use geos_pixel_v5::pdb::tiled::TiledPdbDecoder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let tiled_rootfs_dir = "/home/jericho/pdb_hydration_scratch/out/rootfs_tiled";

    println!("=== Tiled Blob Debug ===\n");
    println!("Loading from: {}", tiled_rootfs_dir);

    let mut tiled_decoder = TiledPdbDecoder::new(tiled_rootfs_dir)?;

    println!("\nHeader info:");
    let header = &tiled_decoder.manager.header;
    println!("  Magic: {:?}", header.magic);
    println!("  Version: {}", header.version);
    println!("  Table count: {}", header.table_count);

    for table in &header.tables {
        let name_str = std::str::from_utf8(&table.name).unwrap_or("");
        println!("\nTable: '{}'", name_str.trim_end_matches('\0'));
        println!("  Row count: {}", table.row_count);
        println!("  Row length: {}", table.row_length);
        println!("  BBox: ({}, {}) to ({}, {})", table.bbox.x_min, table.bbox.y_min, table.bbox.x_max, table.bbox.y_max);
    }

    let tiles = header.get_tiles("rootfs_blob").ok_or("rootfs_blob not found")?;
    println!("\nTile count for 'rootfs_blob': {}", tiles.len());

    for (i, tile) in tiles.iter().take(3).enumerate() {
        println!("\nTile {}:", i);
        println!("  Coord: ({}, {})", tile.coord.tile_x, tile.coord.tile_y);
        println!("  Byte offset: {}", tile.byte_offset);
        println!("  Byte count: {}", tile.byte_count);
        println!("  BBox: ({}, {}) to ({}, {})", tile.bbox.x_min, tile.bbox.y_min, tile.bbox.x_max, tile.bbox.y_max);
        println!("  File path: {}", tile.file_path.display());
    }

    println!("\n\nAttempting to load first tile...");
    let first_tile = &tiles[0];
    println!("Opening tile: {}", first_tile.file_path.display());

    let mut tile_decoder = tiled_decoder.manager.open_tile("rootfs_blob", first_tile.coord)?;
    println!("✓ Tile PNG loaded");

    let tile_header = tile_decoder.decode_header()?;
    println!("✓ Tile header decoded");

    println!("\nTile header info:");
    println!("  Table count: {}", tile_header.tables.len());
    for table in &tile_header.tables {
        let name_str = std::str::from_utf8(&table.name).unwrap_or("");
        println!("  Table '{}': row_count={}, row_length={}", name_str.trim_end_matches('\0'), table.row_count, table.row_length);
    }

    println!("\nAttempting to decode first table...");
    let tile_data = tile_decoder.decode_first_table()?;
    println!("✓ Decoded {} bytes from first tile", tile_data.len());

    println!("\nFirst 100 bytes:");
    for i in 0..100.min(tile_data.len()) {
        print!("{:02x} ", tile_data[i]);
    }
    println!();

    let ascii = String::from_utf8_lossy(&tile_data[..100.min(tile_data.len())]);
    println!("As ASCII: {}", ascii);

    Ok(())
}