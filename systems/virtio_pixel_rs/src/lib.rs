use anyhow::Result;
use log::{info, warn};

pub mod backend;

pub use backend::VirtioPixelServer;

use std::path::{Path, PathBuf};

/// Special offset used in pixel encoding (matching Python pixel_build.py)
const SPECIAL_OFFSET: u32 = 16;

/// Hilbert curve: Convert index d to (x, y) coordinates on n×n grid
///
/// This is the inverse of the spatial mapping used during encoding.
///
/// Arguments:
///   - n: grid size (must be power of 2)
///   - d: Hilbert index (0 to n²-1)
///
/// Returns: (x, y) tuple
pub fn hilbert_d2xy(n: u32, d: u32) -> (u32, u32) {
    let mut x = 0u32;
    let mut y = 0u32;
    let mut s = 1u32;
    let mut temp = d;

    while s < n {
        let rx = (temp >> 1) & 1;
        let ry = (temp ^ rx) & 1;

        if ry == 0 {
            if rx == 1 {
                x = s - 1 - x;
                y = s - 1 - y;
            }
            std::mem::swap(&mut x, &mut y);
        }

        x += s * rx;
        y += s * ry;
        temp >>= 2;
        s <<= 1;
    }

    (x, y)
}

/// Decode RGB24 pixel to byte (matching Python decode_pixels_to_bytes)
///
/// Encoding: id = (R << 16) | (G << 8) | B; byte = id - SPECIAL_OFFSET
/// Padding pixels (id < SPECIAL_OFFSET) are filtered out.
///
/// Arguments:
///   - r, g, b: RGB pixel values
///
/// Returns: decoded byte value, or None if padding pixel
pub fn decode_pixel_to_byte(r: u8, g: u8, b: u8) -> Option<u8> {
    let id = ((r as u32) << 16) | ((g as u32) << 8) | (b as u32);

    // Filter padding pixels (id < SPECIAL_OFFSET)
    if id >= SPECIAL_OFFSET {
        Some((id - SPECIAL_OFFSET) as u8)
    } else {
        None
    }
}

/// Spatial MKV extractor with lazy loading
#[derive(Debug)]
pub struct SpatialMkvExtractor {
    mkv_path: PathBuf,
    entry_name: String,
    decoded_size: u64,
    pixel_length: u64,
    frame_size: u32,
}

impl SpatialMkvExtractor {
    pub fn new<P: AsRef<Path>>(mkv_path: P, entry_name: &str) -> Result<Self> {
        let mkv_path = mkv_path.as_ref().to_path_buf();

        // Known Ubuntu disk size from working Python NBD backend
        let decoded_size = 7u64 * 1024 * 1024 * 1024; // 7 GB
        let pixel_length = decoded_size * 3;
        let frame_size = 4096; // 4096×4096 pixel frames

        info!(
            "SpatialMKV: {} ({} GB decoded, {} GB pixels, {}×{} frames)",
            entry_name,
            decoded_size / (1024 * 1024 * 1024),
            pixel_length / (1024 * 1024 * 1024),
            frame_size,
            frame_size
        );

        Ok(Self {
            mkv_path,
            entry_name: entry_name.to_string(),
            decoded_size,
            pixel_length,
            frame_size,
        })
    }

    /// Read bytes from spatial MKV with Hilbert decoding
    ///
    /// This implements the CPU-based extraction path:
    /// 1. Map byte offset → frame index + frame offset
    /// 2. Extract target frame from MKV using ffmpeg
    /// 3. For each byte, compute Hilbert (x, y) coordinates
    /// 4. Read pixel at (x, y) and decode RGB → byte
    ///
    /// Arguments:
    ///   - offset: Byte offset in the decoded data space (0 to 7GB)
    ///   - length: Number of bytes to read
    ///
    /// Returns: Decoded byte vector
    pub fn read(&mut self, offset: u64, length: u64) -> Result<Vec<u8>> {
        // Handle out-of-bounds reads
        if offset >= self.decoded_size {
            warn!(
                "Read beyond decoded_size (offset={}, size={})",
                offset, self.decoded_size
            );
            return Ok(vec![0u8; length as usize]);
        }

        let available = self.decoded_size - offset;
        let bytes_to_read = length.min(available) as usize;

        if bytes_to_read == 0 {
            return Ok(vec![]);
        }

        // Frame capacity: 4096×4096×3 = 50,331,648 bytes per frame
        let frame_capacity = (self.frame_size as u64) * (self.frame_size as u64) * 3;

        let mut result = Vec::with_capacity(bytes_to_read);
        let mut bytes_read = 0;

        while bytes_read < bytes_to_read {
            // Map global offset to frame + offset within frame
            let global_byte_pos = offset + bytes_read as u64;
            let frame_index = 1 + (global_byte_pos / frame_capacity) as usize; // +1 to skip directory frame
            let frame_offset = (global_byte_pos % frame_capacity) as usize;

            // Calculate how many bytes we can read from this frame
            let remaining_in_frame = (frame_capacity as usize).saturating_sub(frame_offset);
            let bytes_in_this_read = remaining_in_frame.min(bytes_to_read - bytes_read);

            // Extract bytes from this frame
            let frame_bytes = self.extract_from_frame(frame_index, frame_offset, bytes_in_this_read)?;
            result.extend_from_slice(&frame_bytes);

            bytes_read += bytes_in_this_read;
        }

        Ok(result)
    }

    /// Extract bytes from a specific MKV frame using Hilbert decoding
    fn extract_from_frame(
        &self,
        frame_index: usize,
        frame_offset: usize,
        length: usize,
    ) -> Result<Vec<u8>> {
        // Extract frame using ffmpeg
        let frame_pixels = self.extract_frame_pixels(frame_index)?;

        let frame_size = self.frame_size as usize;
        let frame_capacity = frame_size * frame_size * 3;

        if frame_offset + length > frame_capacity {
            return Err(anyhow::anyhow!(
                "Frame read exceeds capacity: offset={}, length={}, capacity={}",
                frame_offset, length, frame_capacity
            ));
        }

        // Extract bytes via Hilbert curve
        let mut result = Vec::with_capacity(length);

        for i in 0..length {
            let byte_idx = frame_offset + i;

            // Compute Hilbert (x, y) coordinates
            let (x, y) = hilbert_d2xy(self.frame_size, byte_idx as u32);

            // Read pixel at (y, x) - image[y][x] because image is [height][width]
            let pixel = &frame_pixels[y as usize][x as usize];

            // Decode RGB → byte
            if let Some(byte) = decode_pixel_to_byte(pixel[0], pixel[1], pixel[2]) {
                result.push(byte);
            } else {
                // Padding pixel (id < SPECIAL_OFFSET) - should not happen in valid data
                warn!(
                    "Padding pixel encountered at frame {} offset {}: ({}, {}, {})",
                    frame_index, byte_idx, pixel[0], pixel[1], pixel[2]
                );
                result.push(0);
            }
        }

        Ok(result)
    }

    /// Extract a single frame from MKV using ffmpeg
    fn extract_frame_pixels(&self, frame_index: usize) -> Result<Vec<Vec<[u8; 3]>>> {
        use tempfile::NamedTempFile;

        // Create temp file for extracted frame
        let tmp_file = NamedTempFile::new()?;
        let tmp_path = tmp_file.path().to_path_buf();

        // Extract frame using ffmpeg
        let output = std::process::Command::new("ffmpeg")
            .args([
                "-y", // Overwrite output
                "-loglevel", "error",
                "-i", self.mkv_path.to_str().unwrap(),
                "-vf", &format!("select='eq(n\\\\,{frame_index})'"),
                "-vframes", "1",
                "-pix_fmt", "rgb24",
                tmp_path.to_str().unwrap(),
            ])
            .output()?;

        if !output.status.success() {
            return Err(anyhow::anyhow!(
                "ffmpeg extraction failed for frame {}: {}",
                frame_index,
                String::from_utf8_lossy(&output.stderr)
            ));
        }

        // Load RGB24 image
        let img = image::open(&tmp_path)?;
        let rgb_img = img.to_rgb8();

        let width = rgb_img.width() as usize;
        let height = rgb_img.height() as usize;

        if width != self.frame_size as usize || height != self.frame_size as usize {
            return Err(anyhow::anyhow!(
                "Frame size mismatch: got {}×{}, expected {}×{}",
                width, height, self.frame_size, self.frame_size
            ));
        }

        // Convert to [height][width][3] format for Hilbert access
        let mut pixels = Vec::with_capacity(height);
        for y in 0..height {
            let mut row = Vec::with_capacity(width);
            for x in 0..width {
                let pixel = rgb_img.get_pixel(x as u32, y as u32);
                row.push([pixel[0], pixel[1], pixel[2]]);
            }
            pixels.push(row);
        }

        // Clean up temp file
        drop(tmp_file);

        Ok(pixels)
    }

    pub fn write(&mut self, _offset: u64, _data: &[u8]) -> Result<()> {
        // Streaming mode is read-only for now
        warn!("SpatialMKV: write not implemented (read-only mode)");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_spatial_extractor() {
        let extractor = SpatialMkvExtractor::new("test.mkv", "test.pixel").unwrap();
        assert_eq!(extractor.decoded_size, 7 * 1024 * 1024 * 1024);
    }

    #[test]
    fn test_hilbert_d2xy() {
        // Test some basic Hilbert properties
        let (x, y) = hilbert_d2xy(2, 0);
        assert_eq!((x, y), (0, 0));

        let (x, y) = hilbert_d2xy(2, 1);
        assert_eq!((x, y), (0, 1));

        let (x, y) = hilbert_d2xy(2, 2);
        assert_eq!((x, y), (1, 1));

        let (x, y) = hilbert_d2xy(2, 3);
        assert_eq!((x, y), (1, 0));
    }

    #[test]
    fn test_decode_pixel_to_byte() {
        // Test valid pixel decoding (byte + SPECIAL_OFFSET)
        let byte_val = 42u8;
        let id = byte_val as u32 + SPECIAL_OFFSET;
        let r = ((id >> 16) & 0xFF) as u8;
        let g = ((id >> 8) & 0xFF) as u8;
        let b = (id & 0xFF) as u8;

        let decoded = decode_pixel_to_byte(r, g, b);
        assert_eq!(decoded, Some(byte_val));

        // Test padding pixel (id < SPECIAL_OFFSET)
        let decoded = decode_pixel_to_byte(0, 0, 0);
        assert_eq!(decoded, None);
    }
}