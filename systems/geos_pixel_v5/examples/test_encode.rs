use std::fs;
use std::path::PathBuf;
fn main() {
    let file_data = fs::read("/home/jericho/projects/zion/projects/visual_audio/ubuntu-desktop-15g.raw").unwrap();
    println!("Read {} bytes", file_data.len());
    let data = &file_data[0..48758784];
    
    let tile_size = 4096;
    let data_pixels = ((16106127360_f64) / 3.0).ceil() as u32;
    let logical_width = tile_size.max((data_pixels as f64 / (tile_size as f64)).ceil() as u32);
    let logical_height = ((data_pixels as f64) / (tile_size as f64)).ceil() as u32;

    let tile_config = geos_pixel_v5::pdb::TileGridConfig::new(tile_size, logical_width, logical_height).unwrap();
    let mut header = geos_pixel_v5::pdb::TiledPdbHeader::new(tile_config.clone());
    
    let bbox_height = 3968;
    let bbox = geos_pixel_v5::pdb::BoundingBox {
        x_min: 0,
        y_min: 128,
        x_max: 4095,
        y_max: 128 + bbox_height - 1,
    };
    
    let mut tile_header = geos_pixel_v5::pdb::PdbHeader::new();
    tile_header.add_table(geos_pixel_v5::pdb::TableMetadata::new(
        "rootfs",
        bbox,
        48758784,
        1,
    )).unwrap();
    
    let pconfig = geos_pixel_v5::pdb::PdbConfig::new(4096, 4096).unwrap();
    let mut encoder = geos_pixel_v5::pdb::PdbEncoder::new(pconfig, tile_header);
    encoder.encode_header().unwrap();
    encoder.encode_table(0, data).unwrap();
    
    fs::create_dir_all("/tmp/my_tiles").unwrap();
    encoder.save_png("/tmp/my_tiles/rootfs.0.0.pdb.png").unwrap();
    println!("Saved!");
}
