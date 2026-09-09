fn main() {
    let mut decoder = geos_pixel::pdb::decoder::PdbDecoder::load_png("tmp_tiles/rootfs.0.0.pdb.png").unwrap();
    println!("{:?}", decoder.header);
}
