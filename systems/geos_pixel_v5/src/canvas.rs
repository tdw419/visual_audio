use crate::hilbert::HilbertCurve;
use image::{RgbaImage, Rgba};
use std::path::Path;

pub struct PixelCanvas {
    pub size: usize,
    pub buffer: RgbaImage,
}

impl PixelCanvas {
    pub fn new(size: usize) -> Self {
        assert!(size.is_power_of_two(), "Canvas size must be a power of 2 for Hilbert mapping");
        Self {
            size,
            buffer: RgbaImage::new(size as u32, size as u32),
        }
    }

    /// Writes linear bytes into the 2D spatial canvas using Hilbert curve routing.
    /// Bytes are packed into the RGB channels (A=255).
    pub fn write_bytes(&mut self, start_distance: usize, data: &[u8]) {
        for (i, chunk) in data.chunks(3).enumerate() {
            let d = start_distance + i;
            if d >= (self.size * self.size) {
                break; // Out of bounds
            }
            
            let (x, y) = HilbertCurve::d2xy(self.size, d);
            
            let r = chunk.get(0).copied().unwrap_or(0);
            let g = chunk.get(1).copied().unwrap_or(0);
            let b = chunk.get(2).copied().unwrap_or(0);
            
            self.buffer.put_pixel(x as u32, y as u32, Rgba([r, g, b, 255]));
        }
    }

    pub fn save_png<P: AsRef<Path>>(&self, path: P) -> image::ImageResult<()> {
        self.buffer.save(path)
    }
}
