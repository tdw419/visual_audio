fn main() {
    let img = image::open("../tmp_tiles/rootfs.0.0.pdb.png").unwrap().to_rgba8();
    for i in 0..4 {
        println!("{:?}", img.get_pixel(i, 0));
    }
}
