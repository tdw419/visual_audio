use image::GenericImageView;
fn main() {
    let img = image::open("tmp_tiles/rootfs.0.0.pdb.png").unwrap();
    let p = img.get_pixel(0, 128);
    println!("{:?}", p);
}
