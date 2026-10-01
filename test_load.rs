fn main() {
    let decoder = png::Decoder::new(std::fs::File::open("tmp_tiles/rootfs.0.0.pdb.png").unwrap());
    let mut reader = decoder.read_info().unwrap();
    let mut buf = vec![0; reader.output_buffer_size()];
    let info = reader.next_frame(&mut buf).unwrap();
    println!("Width: {}, Height: {}, Buffer length: {}", info.width, info.height, buf.len());
    let canvas = image::RgbaImage::from_raw(info.width, info.height, buf);
    println!("Canvas created: {}", canvas.is_some());
}
