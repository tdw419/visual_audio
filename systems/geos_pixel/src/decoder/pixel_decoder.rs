//! V3 Pixel Decoder — PNG chunks → DEFLATE → raw bytes
//!
//! Freestanding implementation with no std/alloc dependencies initially.
//! Ported from virtio_pixel_rs_v3_shared for V4 boot path compatibility.

use alloc::vec::Vec;

/// Pixel decoder for V4 boot path
///
/// Decodes PNG frames with DEFLATE decompression and PNG unfiltering.
/// Can be used in freestanding (no_std) environments suitable for UEFI bootloaders.
pub struct PixelDecoder;

impl PixelDecoder {
    pub fn new() -> Self {
        Self
    }

    /// Decode a single frame from raw PNG data
    ///
    /// # Arguments
    /// * `data` - Raw PNG bytes
    ///
    /// # Returns
    /// Tuple of (pixels, width, height, bytes_per_pixel) on success
    ///
    /// # Errors
    /// Returns static str error messages for:
    /// - Invalid PNG signature
    /// - Missing/invalid chunks (IHDR, IDAT)
    /// - Unsupported color type/depth
    /// - DEFLATE decompression failure
    /// - PNG unfiltering errors
    pub fn decode_frame(&mut self, data: &[u8]) -> Result<(Vec<u8>, usize, usize, usize), &'static str> {
        // Verify PNG signature
        if data.len() < 8 || &data[0..8] != b"\x89PNG\r\n\x1a\n" {
            return Err("Invalid PNG signature");
        }

        let mut offset = 8;
        let mut idat_data = Vec::new();
        let mut width = 0usize;
        let mut height = 0usize;
        let mut bpp = 0usize;

        // Parse PNG chunks
        while offset + 12 <= data.len() {
            let length = u32::from_be_bytes(
                data[offset..offset+4].try_into().unwrap()
            ) as usize;
            let chunk_type = &data[offset+4..offset+8];

            if offset + 12 + length > data.len() {
                return Err("PNG chunk length out of bounds");
            }

            let chunk_data = &data[offset+8..offset+8+length];

            match chunk_type {
                b"IHDR" => {
                    if chunk_data.len() < 13 {
                        return Err("Invalid IHDR chunk");
                    }
                    width = u32::from_be_bytes(chunk_data[0..4].try_into().unwrap()) as usize;
                    height = u32::from_be_bytes(chunk_data[4..8].try_into().unwrap()) as usize;
                    let bit_depth = chunk_data[8];
                    let color_type = chunk_data[9];

                    if bit_depth != 8 {
                        return Err("Only 8-bit depth supported");
                    }

                    bpp = match color_type {
                        2 => 3, // RGB
                        6 => 4, // RGBA
                        _ => return Err("Unsupported color type (need RGB or RGBA)"),
                    };
                }
                b"IDAT" => {
                    idat_data.extend_from_slice(chunk_data);
                }
                b"IEND" => {
                    break;
                }
                _ => {
                    // Skip unknown chunks
                }
            }

            offset += 12 + length;
        }

        if idat_data.is_empty() || width == 0 || height == 0 {
            return Err("Missing IDAT or IHDR chunks");
        }

        // Decompress DEFLATE data
        let decompressed = match miniz_oxide::inflate::decompress_to_vec_zlib(&idat_data) {
            Ok(d) => d,
            Err(_) => return Err("DEFLATE failed: miniz_oxide"),
        };

        // Unfilter PNG rows
        let row_bytes = width * bpp;
        let expected_size = height * (row_bytes + 1);
        if decompressed.len() != expected_size {
            return Err("Decompressed data size mismatch");
        }

        let mut pixels = alloc::vec![0u8; height * row_bytes];

        for y in 0..height {
            let src_offset = y * (row_bytes + 1);
            let filter_type = decompressed[src_offset];
            let row_src = &decompressed[src_offset + 1 .. src_offset + 1 + row_bytes];
            let dst_offset = y * row_bytes;

            if filter_type == 0 {
                // Fast path for None filter
                pixels[dst_offset..dst_offset + row_bytes].copy_from_slice(row_src);
                continue;
            }

            for x in 0..row_bytes {
                let a = if x >= bpp { pixels[dst_offset + x - bpp] } else { 0 };
                let b = if y > 0 { pixels[dst_offset - row_bytes + x] } else { 0 };
                let c = if y > 0 && x >= bpp { pixels[dst_offset - row_bytes + x - bpp] } else { 0 };

                let raw = row_src[x];
                let val = match filter_type {
                    1 => raw.wrapping_add(a), // Sub
                    2 => raw.wrapping_add(b), // Up
                    3 => raw.wrapping_add(((a as u16 + b as u16) / 2) as u8), // Average
                    4 => { // Paeth
                        let p = a as i32 + b as i32 - c as i32;
                        let pa = (p - a as i32).abs();
                        let pb = (p - b as i32).abs();
                        let pc = (p - c as i32).abs();
                        let pr = if pa <= pb && pa <= pc { a }
                                 else if pb <= pc { b }
                                 else { c };
                        raw.wrapping_add(pr)
                    }
                    _ => return Err("Unknown filter type"),
                };
                pixels[dst_offset + x] = val;
            }
        }

        Ok((pixels, width, height, bpp))
    }

    /// Complete decode path: PNG chunks -> DEFLATE -> Unfilter -> Hilbert decode
    ///
    /// This is the V3-style decode path that produces a linear byte stream from
    /// Hilbert-ordered pixels. Used in V4 for:
    /// - Decoding single-tile PDB frames
    /// - Boot-time tile reassembly
    ///
    /// # Arguments
    /// * `data` - Raw PNG bytes
    ///
    /// # Returns
    /// Linear byte stream from Hilbert-ordered pixels (3 bytes/pixel: RGB only)
    ///
    /// # Errors
    /// Returns static str error messages for decode failures
    pub fn decode_geos_pixel_container(&mut self, data: &[u8]) -> Result<Vec<u8>, &'static str> {
        let (pixels, width, height, bpp) = self.decode_frame(data)?;

        // Verify square power-of-2 dimensions for Hilbert mapping
        if width != height || (width & (width - 1)) != 0 {
            return Err("Image must be a square with power-of-2 dimensions for Hilbert mapping");
        }

        let grid_size = width;
        let mut output = alloc::vec![0u8; width * height * 3]; // 3 bytes per pixel (RGB only)

        for (i, chunk) in pixels.chunks(bpp).enumerate() {
            let x = i % width;
            let y = i / width;

            // True Hilbert mapping (uses geos_pixel::HilbertCurve::xy2d)
            let d = crate::hilbert::HilbertCurve::xy2d(grid_size, x, y);

            // Extract RGB (ignore Alpha/bpp differences past first 3 bytes)
            let out_idx = d * 3;
            if out_idx + 3 <= output.len() && chunk.len() >= 3 {
                output[out_idx] = chunk[0];
                output[out_idx + 1] = chunk[1];
                output[out_idx + 2] = chunk[2];
            }
        }

        Ok(output)
    }

    pub fn decode_pdb_table(&mut self, data: &[u8], table_index: u8) -> Result<alloc::vec::Vec<u8>, &'static str> {
        let (pixels, width, height, bpp) = self.decode_frame(data)?;

        // Helper to read a single pixel's R channel at (x, 0)
        let get_r = |x: usize| -> u8 {
            pixels[x * bpp]
        };

        // Check magic bytes
        let magic = [get_r(0), get_r(1), get_r(2), get_r(3)];
        if magic != [0x50, 0x44, 0x42, 0x31] {
            return Err("Not a valid PDB frame (magic mismatch)");
        }

        let table_count = get_r(5);
        if table_index >= table_count {
            return Err("Table index out of bounds");
        }

        let mut x_offset = 6 + (table_index as usize * 40);
        x_offset += 16; // Skip name

        let mut read_u32 = || -> u32 {
            let mut buf = [0u8; 4];
            for i in 0..4 {
                buf[i] = get_r(x_offset);
                x_offset += 1;
            }
            u32::from_le_bytes(buf)
        };

        let x_min = read_u32();
        let y_min = read_u32();
        let x_max = read_u32();
        let y_max = read_u32();
        let row_count = read_u32();
        let row_length = read_u32();

        let expected_bytes = (row_count * row_length) as usize;
        let mut output = alloc::vec::Vec::with_capacity(expected_bytes);

        let table_width = x_max - x_min + 1;
        let table_height = y_max - y_min + 1;
        let mut grid_size = table_width.max(table_height).next_power_of_two();
        if grid_size < 2 { grid_size = 2; }

        let mut i = 0;
        while output.len() < expected_bytes {
            let (x, y) = crate::hilbert::HilbertCurve::d2xy(grid_size as usize, i);
            i += 1;

            let abs_x = x_min as usize + x as usize;
            let abs_y = y_min as usize + y as usize;

            if abs_x <= x_max as usize && abs_y <= y_max as usize {
                let pixel_idx = (abs_y * width + abs_x) * bpp;
                output.push(pixels[pixel_idx]);
                if output.len() < expected_bytes {
                    output.push(pixels[pixel_idx + 1]);
                }
                if output.len() < expected_bytes {
                    output.push(pixels[pixel_idx + 2]);
                }
            }
        }

        Ok(output)
    }

}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decoder_construction() {
        let decoder = PixelDecoder::new();
        // Just verify it compiles in no_std context
        let _ = decoder;
    }

    #[test]
    fn test_invalid_png_signature() {
        let mut decoder = PixelDecoder::new();
        let invalid_data = b"not a png\x00\x00\x00\x00";
        let result = decoder.decode_frame(invalid_data);
        assert!(matches!(result, Err("Invalid PNG signature")));
    }

    #[test]
    fn test_truncated_png() {
        let mut decoder = PixelDecoder::new();
        let partial_sig = b"\x89PNG\r\n\x1a";
        let result = decoder.decode_frame(partial_sig);
        assert!(matches!(result, Err(_)));
    
    }
}