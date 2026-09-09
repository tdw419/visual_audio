use geos_pixel::pdb::{PdbConfig, PdbHeader, PdbEncoder};

fn main() {
    let config = PdbConfig::new(256, 256).unwrap();
    let header = PdbHeader::new();
    let mut encoder = PdbEncoder::new(config, header);
    encoder.encode_header().unwrap();
    encoder.save_png("/tmp/test_encoder.png").unwrap();
}
