//! Pixel decoder — PNG chunks → DEFLATE → raw bytes
//!
//! Freestanding implementation with no allocator initially, but uses alloc for buffers.

use alloc::vec::Vec;
use miniz_oxide::inflate::decompress_to_vec_zlib;

pub struct PixelDecoder;

impl PixelDecoder {
    pub fn new() -> Self {
        Self
    }

    /// Decode a single frame from raw PNG data
    pub fn decode_frame(&mut self, data: &[u8]) -> Result<(Vec<u8>, usize, usize, usize), &'static str> {
        if data.len() < 8 || &data[0..8] != b"\x89PNG\r\n\x1a\n" {
            return Err("Invalid PNG signature");
        }

        let mut offset = 8;
        let mut idat_data = Vec::new();
        let mut width = 0usize;
        let mut height = 0usize;
        let mut bpp = 0usize;

        while offset + 12 <= data.len() {
            let length = u32::from_be_bytes(data[offset..offset+4].try_into().unwrap()) as usize;
            let chunk_type = &data[offset+4..offset+8];

            if offset + 12 + length > data.len() {
                return Err("PNG chunk length out of bounds");
            }

            let chunk_data = &data[offset+8..offset+8+length];

            if chunk_type == b"IHDR" {
                if chunk_data.len() < 13 { return Err("Invalid IHDR"); }
                width = u32::from_be_bytes(chunk_data[0..4].try_into().unwrap()) as usize;
                height = u32::from_be_bytes(chunk_data[4..8].try_into().unwrap()) as usize;
                let bit_depth = chunk_data[8];
                let color_type = chunk_data[9];

                if bit_depth != 8 { return Err("Only 8-bit depth supported"); }
                bpp = match color_type {
                    2 => 3, // RGB
                    6 => 4, // RGBA
                    _ => return Err("Unsupported color type (need RGB or RGBA)"),
                };
            } else if chunk_type == b"IDAT" {
                idat_data.extend_from_slice(chunk_data);
            } else if chunk_type == b"IEND" {
                break;
            }

            offset += 12 + length;
        }

        if idat_data.is_empty() || width == 0 || height == 0 {
            return Err("Missing IDAT or IHDR chunks");
        }

        // Decompress DEFLATE data
        let decompressed = match decompress_to_vec_zlib(&idat_data) {
            Ok(d) => d,
            Err(e) => { return Err("DEFLATE failed: miniz"); },
        };

        // Unfilter PNG rows
        let row_bytes = width * bpp;
        if decompressed.len() != height * (row_bytes + 1) {
            return Err("Decompressed data size mismatch");
        }

        let mut pixels = alloc::vec![0u8; height * row_bytes];

        for y in 0..height {
            let src_offset = y * (row_bytes + 1);
            let filter_type = decompressed[src_offset];
            let row_src = &decompressed[src_offset + 1 .. src_offset + 1 + row_bytes];
            let dst_offset = y * row_bytes;

            for x in 0..row_bytes {
                let a = if x >= bpp { pixels[dst_offset + x - bpp] } else { 0 };
                let b = if y > 0 { pixels[dst_offset - row_bytes + x] } else { 0 };
                let c = if y > 0 && x >= bpp { pixels[dst_offset - row_bytes + x - bpp] } else { 0 };

                let raw = row_src[x];
                let val = match filter_type {
                    0 => raw,
                    1 => raw.wrapping_add(a),
                    2 => raw.wrapping_add(b),
                    3 => raw.wrapping_add(((a as u16 + b as u16) / 2) as u8),
                    4 => {
                        // Paeth
                        let p = a as i32 + b as i32 - c as i32;
                        let pa = (p - a as i32).abs();
                        let pb = (p - b as i32).abs();
                        let pc = (p - c as i32).abs();
                        let pr = if pa <= pb && pa <= pc { a } else if pb <= pc { b } else { c };
                        raw.wrapping_add(pr)
                    }
                    _ => return Err("Unknown filter type"),
                };
                pixels[dst_offset + x] = val;
            }
        }

        Ok((pixels, width, height, bpp))
    }

    /// Complete decode path: PNG chunks -> DEFLATE -> Unfilter -> True Hilbert decode
    pub fn decode_geos_pixel_container(&mut self, data: &[u8]) -> Result<Vec<u8>, &'static str> {
        let (pixels, width, height, bpp) = self.decode_frame(data)?;

        if width != height || (width & (width - 1)) != 0 {
            return Err("Image must be a square with power-of-2 dimensions for Hilbert mapping");
        }

        let grid_size = width;
        let mut output = alloc::vec![0u8; width * height * 3]; // 3 bytes per pixel

        for (i, chunk) in pixels.chunks(bpp).enumerate() {
            let x = i % width;
            let y = i / width;

            // True Hilbert mapping
            let d = geos_pixel::HilbertCurve::xy2d(grid_size, x, y);

            // Extract RGB (ignore Alpha/bpp differences past the first 3 bytes)
            let out_idx = d * 3;
            if out_idx + 3 <= output.len() && chunk.len() >= 3 {
                output[out_idx] = chunk[0];
                output[out_idx + 1] = chunk[1];
                output[out_idx + 2] = chunk[2];
            }
        }

        Ok(output)
    }
}
