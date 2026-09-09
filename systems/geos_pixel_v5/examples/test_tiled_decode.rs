// test_tiled_decode.rs - Quick test of tiled blob decoding

use geos_pixel_v5::pdb::tiled::TiledPdbDecoder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let tiled_rootfs_dir = "/home/jericho/pdb_hydration_scratch/out/rootfs_tiled";

    println!("Testing tiled blob decoding...");
    println!("Loading from: {}", tiled_rootfs_dir);

    let mut tiled_decoder = TiledPdbDecoder::new(tiled_rootfs_dir)?;

    println!("Loading full tiled rootfs blob into memory...");
    let full_blob = tiled_decoder.decode_table("rootfs_blob")?;

    println!("SUCCESS: Loaded {} bytes from tiled blob", full_blob.len());

    // Check if we have /etc/passwd at offset 602372
    let offset = 602372usize;
    if full_blob.len() > offset {
        println!("\nFirst 50 bytes at offset 602372:");
        for i in 0..50.min(full_blob.len() - offset) {
            print!("{:02x} ", full_blob[offset + i]);
        }
        println!();

        // Try to find the passwd string
        let ascii = String::from_utf8_lossy(&full_blob[offset..offset + 100]);
        println!("\nFirst 100 bytes as ASCII:");
        println!("{}", ascii);
    }

    Ok(())
}