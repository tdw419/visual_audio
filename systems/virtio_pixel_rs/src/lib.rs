use anyhow::Result;
use log::{info, warn};
use std::path::{Path, PathBuf};

pub mod backend;
pub mod wgpu_texture_loader;
pub mod hilbert_compute;
pub mod hw_decoder;
pub mod cache_manager;
pub use backend::VirtioPixelServer;

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
    pub mkv_path: PathBuf,
    pub entry_name: String,
    pub decoded_size: u64,
    pub pixel_length: u64,
    pub frame_size: u32,
    // LRU frame cache: systemd touches many disk regions rapidly. Re-decoding
    // on every frame switch (cache miss) takes ~200ms and ruins boot times.
    // LRU frame cache with 64 frame capacity (64 * 16MB = ~1GB RAM)
    frame_cache: std::collections::HashMap<usize, Vec<u8>>,
    cache_order: std::collections::VecDeque<usize>,
    
    // Precomputed Hilbert LUT to eliminate CPU bottleneck during decoding
    hilbert_lut: Vec<(u32, u32)>,
    // Writes land here, keyed by 512-byte sector index, rather than being
    // re-encoded back into the source MKV's video frames (a much bigger
    // project). Read-modify-write happens against the source frame data
    // plus any overlay sectors, so writes are session-local, not persisted.
    write_overlay: std::collections::HashMap<u64, [u8; 512]>,
}

impl SpatialMkvExtractor {
    pub fn new<P: AsRef<Path>>(mkv_path: P, entry_name: &str) -> Result<Self> {
        let mkv_path = mkv_path.as_ref().to_path_buf();

        // Try to read meta.json for actual disk size
        let mut decoded_size = 7u64 * 1024 * 1024 * 1024; // Default to 7 GB
        let meta_path = mkv_path.with_extension("mkv.meta.json");
        if meta_path.exists() {
            if let Ok(meta_str) = std::fs::read_to_string(&meta_path) {
                if let Ok(meta_json) = serde_json::from_str::<serde_json::Value>(&meta_str) {
                    // Python encode_ubuntu_spatial.py uses: "frames" and "bytes_per_frame"
                    if let (Some(frames), Some(bytes_per_frame)) = (
                        meta_json["frames"].as_u64().or_else(|| meta_json["num_frames"].as_u64()),
                        meta_json["bytes_per_frame"].as_u64().or_else(|| meta_json["frame_capacity_bytes"].as_u64())
                    ) {
                        decoded_size = frames * bytes_per_frame;
                    }
                    // Fallback: check for disk_size field (alpine_minimal.meta.json)
                    else if let Some(disk_size) = meta_json["disk_size"].as_u64() {
                        decoded_size = disk_size;
                    }
                }
            }
        } else {
            // Also try just .meta.json if it didn't keep the mkv extension
            let meta_path2 = mkv_path.with_extension("meta.json");
            if let Ok(meta_str) = std::fs::read_to_string(&meta_path2) {
                if let Ok(meta_json) = serde_json::from_str::<serde_json::Value>(&meta_str) {
                    // Python encode_ubuntu_spatial.py uses: "frames" and "bytes_per_frame"
                    if let (Some(frames), Some(bytes_per_frame)) = (
                        meta_json["frames"].as_u64().or_else(|| meta_json["num_frames"].as_u64()),
                        meta_json["bytes_per_frame"].as_u64().or_else(|| meta_json["frame_capacity_bytes"].as_u64())
                    ) {
                        decoded_size = frames * bytes_per_frame;
                    }
                    // Fallback: check for disk_size field
                    else if let Some(disk_size) = meta_json["disk_size"].as_u64() {
                        decoded_size = disk_size;
                    }
                }
            }
        }

        let pixel_length = decoded_size; // GRAY8 is 1 byte per pixel

        // Detect actual frame size from MKV by extracting first frame
        let frame_size = Self::detect_frame_size(&mkv_path)?;

        info!(
            "SpatialMKV: {} ({} GB decoded, {} GB pixels, {}×{} frames)",
            entry_name,
            decoded_size / (1024 * 1024 * 1024),
            pixel_length / (1024 * 1024 * 1024),
            frame_size,
            frame_size
        );

        let frame_capacity_pixels = (frame_size as usize) * (frame_size as usize);
        info!("Precomputing Hilbert LUT for frame size {}...", frame_size);
        let mut hilbert_lut = Vec::with_capacity(frame_capacity_pixels);
        for d in 0..frame_capacity_pixels {
            hilbert_lut.push(hilbert_d2xy(frame_size, d as u32));
        }
        info!("LUT precomputed.");

        Ok(Self {
            mkv_path,
            entry_name: entry_name.to_string(),
            decoded_size,
            pixel_length,
            frame_size,
            frame_cache: std::collections::HashMap::new(),
            cache_order: std::collections::VecDeque::new(),
            hilbert_lut,
            write_overlay: std::collections::HashMap::new(),
        })
    }

    /// Write bytes into the in-memory sector overlay. `offset` and `data.len()`
    /// are expected to be 512-byte aligned (true for all virtio-blk requests).
    pub fn write(&mut self, offset: u64, data: &[u8]) -> Result<()> {
        for (i, chunk) in data.chunks(512).enumerate() {
            let sector = offset / 512 + i as u64;
            let mut sector_buf = [0u8; 512];
            sector_buf[..chunk.len()].copy_from_slice(chunk);
            self.write_overlay.insert(sector, sector_buf);
        }
        Ok(())
    }

    /// Read bytes from spatial MKV with Hilbert decoding (legacy method, kept for compatibility)
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

        // Frame capacity: Ubuntu disk uses 1 byte per pixel (R channel only)
        let frame_capacity = (self.frame_size as u64) * (self.frame_size as u64);

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
            let frame_bytes =
                self.extract_from_frame(frame_index, frame_offset, bytes_in_this_read)?;
            result.extend_from_slice(&frame_bytes);

            bytes_read += bytes_in_this_read;
        }

        // Overlay any sectors that have been written since boot.
        if !self.write_overlay.is_empty() {
            let first_sector = offset / 512;
            let last_sector = (offset + result.len() as u64 - 1) / 512;
            for sector in first_sector..=last_sector {
                if let Some(sector_buf) = self.write_overlay.get(&sector) {
                    let sector_start = sector * 512;
                    let src_start = sector_start.saturating_sub(offset) as usize;
                    let copy_start = offset.saturating_sub(sector_start) as usize;
                    let copy_len = (512 - copy_start).min(result.len().saturating_sub(src_start));
                    if copy_len > 0 {
                        result[src_start..src_start + copy_len]
                            .copy_from_slice(&sector_buf[copy_start..copy_start + copy_len]);
                    }
                }
            }
        }

        Ok(result)
    }

    /// Extract bytes from spatial MKV with Hilbert decoding (usize version for VirtIO integration)
    ///
    /// This is a convenience wrapper around read() that uses usize offsets/lengths
    /// for easier integration with the VirtIO backend.
    pub fn extract_bytes(&mut self, offset: usize, length: usize) -> Result<Vec<u8>> {
        self.read(offset as u64, length as u64)
    }

    /// Extract bytes from a specific MKV frame using Hilbert decoding
    fn extract_from_frame(
        &mut self,
        frame_index: usize,
        frame_offset: usize,
        length: usize,
    ) -> Result<Vec<u8>> {
        let frame_size = self.frame_size as usize;
        let frame_capacity = frame_size * frame_size; // 1 byte per pixel

        if frame_offset + length > frame_capacity {
            return Err(anyhow::anyhow!(
                "Frame read exceeds capacity: offset={}, length={}, capacity={}",
                frame_offset, length, frame_capacity
            ));
        }

        // LRU frame cache with 64 frame capacity (64 * 16MB = ~1GB RAM)
        if !self.frame_cache.contains_key(&frame_index) {
            let rgb_bytes = self.extract_frame_pixels(frame_index)?;
            
            // Fully decode the frame upfront using the LUT
            let mut decoded_bytes = Vec::with_capacity(frame_capacity);
            for d in 0..frame_capacity {
                let (x, y) = self.hilbert_lut[d];
                let p_idx = (y as usize * frame_size + x as usize) * 3;
                let r = rgb_bytes[p_idx];
                let g = rgb_bytes[p_idx + 1];
                let b = rgb_bytes[p_idx + 2];
                
                let byte = decode_pixel_to_byte(r, g, b).unwrap_or(0);
                decoded_bytes.push(byte);
            }

            self.frame_cache.insert(frame_index, decoded_bytes);
            self.cache_order.push_back(frame_index);
            if self.cache_order.len() > 64 {
                if let Some(oldest) = self.cache_order.pop_front() {
                    self.frame_cache.remove(&oldest);
                }
            }
        }
        
        let decoded_bytes = self.frame_cache.get(&frame_index).unwrap();
        
        // Fast path: just copy the pre-decoded bytes!
        let mut result = Vec::with_capacity(length);
        result.extend_from_slice(&decoded_bytes[frame_offset..frame_offset + length]);
        
        Ok(result)
    }

    /// Extract a single frame from the container directly into raw RGB bytes in memory
    fn extract_frame_pixels(&self, frame_index: usize) -> Result<Vec<u8>> {
        let output = std::process::Command::new("ffmpeg")
            .args([
                "-y",
                "-loglevel", "error",
                "-ss", &frame_index.to_string(),
                "-i", self.mkv_path.to_str().unwrap(),
                "-vframes", "1",
                "-f", "image2pipe",
                "-vcodec", "rawvideo",
                "-pix_fmt", "rgb24",
                "-",
            ])
            .output()?;

        if !output.status.success() {
            return Err(anyhow::anyhow!(
                "ffmpeg extraction failed for frame {}: {}",
                frame_index,
                String::from_utf8_lossy(&output.stderr)
            ));
        }

        Ok(output.stdout)
    }

    /// Detect actual frame size from MKV by extracting first frame
    fn detect_frame_size(mkv_path: &Path) -> Result<u32> {
        use tempfile::NamedTempFile;

        let tmp_file = NamedTempFile::with_suffix(".png")?;
        let tmp_path = tmp_file.path().to_path_buf();

        // Extract frame 0 (directory frame) to detect size using fast seek
        let output = std::process::Command::new("ffmpeg")
            .args([
                "-y",
                "-loglevel", "error",
                "-ss", "0",
                "-i", mkv_path.to_str().unwrap(),
                "-vframes", "1",
                "-pix_fmt", "rgb24",
                tmp_path.to_str().unwrap(),
            ])
            .output()?;

        if !output.status.success() {
            return Err(anyhow::anyhow!(
                "ffmpeg extraction failed: {}",
                String::from_utf8_lossy(&output.stderr)
            ));
        }

        // Load image to get dimensions
        let img = image::open(&tmp_path)?;
        let width = img.width();

        Ok(width)
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