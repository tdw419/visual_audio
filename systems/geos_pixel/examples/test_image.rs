use image::GenericImageView;
fn main() {
    let img = image::open("/home/jericho/projects/zion/projects/visual_audio/tmp_tiles/rootfs.0.0.pdb.png").unwrap();
    let p = img.get_pixel(0, 128);
    println!("Pixel at 0, 128 is {:?}", p);
    let p2 = img.get_pixel(9, 171);
    println!("Pixel at 9, 171 is {:?}", p2);
}
