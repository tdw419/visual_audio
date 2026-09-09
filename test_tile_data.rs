use std::fs;
fn main() {
    let file_data = fs::read("/home/jericho/projects/zion/projects/visual_audio/ubuntu-desktop-15g.raw").unwrap();
    println!("{:?}", &file_data[0..10]);
}
