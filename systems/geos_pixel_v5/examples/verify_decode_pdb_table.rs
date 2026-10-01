use geos_pixel_v5::decoder::PixelDecoder;
use std::env;
use std::fs;

fn main() {
    let args: Vec<String> = env::args().collect();
    let png_path = &args[1];
    let reference_path = &args[2];

    let png_data = fs::read(png_path).expect("read png");
    let reference = fs::read(reference_path).expect("read reference");

    let mut decoder = PixelDecoder::new();
    let extracted = decoder.decode_pdb_table(&png_data, 0).expect("decode_pdb_table failed");

    println!("Reference size: {} bytes", reference.len());
    println!("Extracted size: {} bytes", extracted.len());

    let truncated = &extracted[..reference.len().min(extracted.len())];
    if truncated == &reference[..truncated.len()] {
        println!("MATCH: first {} bytes identical", truncated.len());
    } else {
        let mismatch = truncated.iter().zip(reference.iter()).position(|(a, b)| a != b);
        println!("MISMATCH at byte {:?}", mismatch);
        if let Some(idx) = mismatch {
            println!("  extracted[{}..{}] = {:02x?}", idx, idx+8, &extracted[idx..(idx+8).min(extracted.len())]);
            println!("  reference[{}..{}] = {:02x?}", idx, idx+8, &reference[idx..(idx+8).min(reference.len())]);
        }
    }
}
