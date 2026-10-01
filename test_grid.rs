fn main() {
    let file_data_len: u64 = 16106127360;
    let tile_size = 4096;
    
    let data_pixels = ((file_data_len as f64) / 3.0).ceil() as u32;
    let logical_width = tile_size.max((data_pixels as f64 / (tile_size as f64)).ceil() as u32);
    let logical_height = ((data_pixels as f64) / (tile_size as f64)).ceil() as u32;
    
    println!("data_pixels: {}", data_pixels);
    println!("logical_width: {}", logical_width);
    println!("logical_height: {}", logical_height);
}
