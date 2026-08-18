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
///   - r, g, b: RGB pixel values from ffmpeg (after matroska BGR->RGB conversion)
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

    // PXC1 mode (docs/PIXEL_CONTAINER_SPEC_V1.md): when mkv_path is a PXC1
    // container directory (has header.json), every named section is
    // decoded once at startup and concatenated in header order into this
    // buffer, which becomes the guest-visible disk. This replaces the old
    // ffmpeg/.nut path (per-frame Hilbert decode + BGR/rgb24 pixel-format
    // ambiguity that caused real corruption) with a byte-perfect,
    // hash-verified read at load time and a plain slice on every
    // subsequent read - no per-request decode cost.
    pxc1_buffer: Option<Vec<u8>>,

    // PXC1 section metadata (name/start_frame/byte_length), kept around
    // (PXC1 mode only) so writeback() can map a write_overlay sector back
    // to the PXC1 frame it belongs to, without re-reading header.json.
    pxc1_sections: Vec<pxc1::Section>,
}

impl SpatialMkvExtractor {
    pub fn new<P: AsRef<Path>>(mkv_path: P, entry_name: &str) -> Result<Self> {
        let mkv_path = mkv_path.as_ref().to_path_buf();

        // PXC1 mode: a container directory has header.json at its root.
        // Load it fully here (once, at startup) instead of going through
        // any frame-cache/Hilbert/ffmpeg path below.
        if mkv_path.is_dir() && mkv_path.join("header.json").exists() {
            let mut decoder = pxc1::Decoder::open(&mkv_path)
                .map_err(|e| anyhow::anyhow!("PXC1 open failed: {e}"))?;
            let header = decoder.header().clone();
            let mut buffer = Vec::new();
            for section in &header.sections {
                let bytes = decoder
                    .read_section(&section.name)
                    .map_err(|e| anyhow::anyhow!("PXC1 read_section({}) failed: {e}", section.name))?;
                info!(
                    "PXC1: loaded section '{}' ({} bytes, sha256 verified)",
                    section.name,
                    bytes.len()
                );
                buffer.extend_from_slice(&bytes);
            }
            let remainder = buffer.len() % 512;
            if remainder != 0 {
                let padding = 512 - remainder;
                buffer.extend(std::iter::repeat(0).take(padding));
            }
            let decoded_size = buffer.len() as u64;
            info!(
                "PXC1: {} ({} sections, {} bytes total disk)",
                entry_name,
                header.sections.len(),
                decoded_size
            );
            return Ok(Self {
                mkv_path,
                entry_name: entry_name.to_string(),
                decoded_size,
                pixel_length: decoded_size,
                frame_size: header.frame_size as u32,
                frame_cache: std::collections::HashMap::new(),
                cache_order: std::collections::VecDeque::new(),
                hilbert_lut: Vec::new(),
                write_overlay: std::collections::HashMap::new(),
                pxc1_buffer: Some(buffer),
                pxc1_sections: header.sections.clone(),
            });
        }

        // Legacy ffmpeg/.nut path below. Try to read meta.json for actual disk size
        let mut decoded_size = 7u64 * 1024 * 1024 * 1024; // Default to 7 GB
        // encode_spatial_container.py writes "<full filename incl. .nut>.meta.json"
        // (append, not replace) - Path::with_extension() REPLACES the extension,
        // so e.g. "foo.nut".with_extension("meta.json") wrongly yields "foo.meta.json"
        // (drops "nut") and never matches the real file on disk. Build the real
        // filename by string-appending instead.
        let meta_path = {
            let mut s = mkv_path.as_os_str().to_os_string();
            s.push(".meta.json");
            std::path::PathBuf::from(s)
        };
        if meta_path.exists() {
            if let Ok(meta_str) = std::fs::read_to_string(&meta_path) {
                if let Ok(meta_json) = serde_json::from_str::<serde_json::Value>(&meta_str) {
                    // Python encode_ubuntu_spatial.py uses: "frames" and "bytes_per_frame"
                    if let (Some(frames), Some(bytes_per_frame)) = (
                        meta_json["frames"].as_u64().or_else(|| meta_json["num_frames"].as_u64()),
                        meta_json["bytes_per_frame"].as_u64().or_else(|| meta_json["frame_capacity_bytes"].as_u64())
                    ) {
                        // The 'frames' count in meta.json includes the metadata frame 0.
                        // So the number of actual payload data frames is frames - 1.
                        decoded_size = frames.saturating_sub(1) * bytes_per_frame;
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
                        // The 'frames' count in meta.json includes the metadata frame 0.
                        // So the number of actual payload data frames is frames - 1.
                        decoded_size = frames.saturating_sub(1) * bytes_per_frame;
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
            pxc1_buffer: None,
            pxc1_sections: Vec::new(),
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

    /// Get disk capacity in 512-byte sectors
    pub fn get_capacity_sectors(&self) -> u64 {
        self.decoded_size / 512
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

        if let Some(buffer) = &self.pxc1_buffer {
            let start = offset as usize;
            let mut result = buffer[start..start + bytes_to_read].to_vec();
            if !self.write_overlay.is_empty() {
                Self::apply_write_overlay(&self.write_overlay, offset, &mut result);
            }
            return Ok(result);
        }

        // Frame capacity: BGR24 = 3 bytes per pixel
        let frame_capacity = (self.frame_size as u64) * (self.frame_size as u64);

        let mut result = Vec::with_capacity(bytes_to_read);
        let mut bytes_read = 0;

        while bytes_read < bytes_to_read {
            // Map global offset to frame + offset within frame
            let global_byte_pos = offset + bytes_read as u64;
            let frame_index = ((global_byte_pos / frame_capacity) as usize) + 1; // VSP1 has metadata in frame 0
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
            Self::apply_write_overlay(&self.write_overlay, offset, &mut result);
        }

        Ok(result)
    }

    /// Apply any written-since-boot sectors on top of a freshly-read buffer.
    /// Shared by both the PXC1 in-memory-buffer read path and the legacy
    /// per-frame Hilbert decode path, so the overlay math exists once.
    fn apply_write_overlay(
        write_overlay: &std::collections::HashMap<u64, [u8; 512]>,
        offset: u64,
        result: &mut [u8],
    ) {
        let first_sector = offset / 512;
        let last_sector = (offset + result.len() as u64 - 1) / 512;
        for sector in first_sector..=last_sector {
            if let Some(sector_buf) = write_overlay.get(&sector) {
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

    /// Patch every dirty write_overlay sector back into the PXC1 container
    /// on disk, touching only the frames that actually changed (not a full
    /// container re-encode), then clear the overlay. PXC1 mode only.
    ///
    /// Sections are concatenated byte-exact (no inter-section padding) in
    /// pxc1_buffer, in the same order as pxc1_sections, so a buffer offset
    /// maps to a section by simple cumulative byte_length ranges; within a
    /// section, frame_index = section.start_frame + offset_in_section /
    /// BYTES_PER_FRAME, matching how the encoder laid frames out on disk.
    ///
    /// Returns the names of sections that had at least one frame patched.
    pub fn writeback(&mut self) -> Result<Vec<String>> {
        if self.write_overlay.is_empty() {
            return Ok(vec![]);
        }
        let buffer = self
            .pxc1_buffer
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("writeback() only supported for PXC1 containers"))?;

        // (name, buffer_start, buffer_end) per section, in concatenation order.
        let mut section_ranges: Vec<(String, usize, usize)> = Vec::new();
        let mut cursor = 0usize;
        for s in &self.pxc1_sections {
            section_ranges.push((s.name.clone(), cursor, cursor + s.byte_length));
            cursor += s.byte_length;
        }

        // Group dirty sectors by (section, frame_index); BTreeSet for
        // deterministic, sorted patch order (easier to read in logs).
        let mut dirty_frames: std::collections::BTreeSet<(String, usize)> = Default::default();
        for &sector in self.write_overlay.keys() {
            let buf_offset = (sector * 512) as usize;
            let Some((name, buf_start, _)) = section_ranges
                .iter()
                .find(|(_, s, e)| buf_offset >= *s && buf_offset < *e)
            else {
                warn!("writeback: dirty sector {} outside any known section, skipping", sector);
                continue;
            };
            let section = self.pxc1_sections.iter().find(|s| &s.name == name).unwrap();
            let offset_in_section = buf_offset - buf_start;
            let frame_idx = section.start_frame + offset_in_section / pxc1::BYTES_PER_FRAME;
            dirty_frames.insert((name.clone(), frame_idx));
        }

        let encoder = pxc1::Encoder::new(&self.mkv_path);
        let mut touched_sections: std::collections::BTreeSet<String> = Default::default();

        for (section_name, frame_idx) in &dirty_frames {
            let (_, buf_start, buf_end) = section_ranges
                .iter()
                .find(|(n, _, _)| n == section_name)
                .unwrap();
            let section = self.pxc1_sections.iter().find(|s| &s.name == section_name).unwrap();
            let frame_offset_in_section = (frame_idx - section.start_frame) * pxc1::BYTES_PER_FRAME;
            let frame_buf_start = buf_start + frame_offset_in_section;
            let frame_buf_end = (frame_buf_start + pxc1::BYTES_PER_FRAME).min(*buf_end);

            let mut frame_data = vec![0u8; pxc1::BYTES_PER_FRAME];
            let n = frame_buf_end.saturating_sub(frame_buf_start);
            frame_data[..n].copy_from_slice(&buffer[frame_buf_start..frame_buf_end]);
            Self::apply_write_overlay(&self.write_overlay, frame_buf_start as u64, &mut frame_data);

            encoder
                .write_frame(*frame_idx, &frame_data)
                .map_err(|e| anyhow::anyhow!("writeback: write_frame({}) failed: {e}", frame_idx))?;
            info!("writeback: patched frame {} (section '{}')", frame_idx, section_name);
            touched_sections.insert(section_name.clone());
        }

        for name in &touched_sections {
            let new_hash = encoder
                .refresh_section_hash(name)
                .map_err(|e| anyhow::anyhow!("writeback: refresh_section_hash('{}') failed: {e}", name))?;
            info!("writeback: section '{}' sha256 updated to {}", name, new_hash);
        }

        // Commit the overlay into the in-memory buffer that read() serves from.
        // Without this, reads immediately after writeback (no reboot needed)
        // would fall through to the stale pre-write bytes once write_overlay
        // is cleared below, even though the correct data is now on disk.
        if let Some(buffer) = self.pxc1_buffer.as_mut() {
            for (&sector, sector_buf) in &self.write_overlay {
                let start = (sector * 512) as usize;
                let end = (start + 512).min(buffer.len());
                let n = end.saturating_sub(start);
                if n > 0 {
                    buffer[start..end].copy_from_slice(&sector_buf[..n]);
                }
            }
        }

        self.write_overlay.clear();
        Ok(touched_sections.into_iter().collect())
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

                // Bounds check for safety
                if p_idx + 2 >= rgb_bytes.len() {
                    log::warn!("LUT index {} out of RGB bounds {} (x={}, y={}, d={})", p_idx + 2, rgb_bytes.len(), x, y, d);
                    decoded_bytes.push(0);
                    continue;
                }

                let r = rgb_bytes[p_idx];
                let g = rgb_bytes[p_idx + 1];
                let b = rgb_bytes[p_idx + 2];

                let byte = decode_pixel_to_byte(r, g, b).unwrap_or(0);
                decoded_bytes.push(byte);
            }

            self.frame_cache.insert(frame_index, decoded_bytes);
            self.cache_order.push_back(frame_index);
            if self.cache_order.len() > 2 {
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

        if output.stdout.is_empty() {
            return Err(anyhow::anyhow!(
                "ffmpeg returned empty frame for frame_index {}",
                frame_index
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
    fn test_pxc1_extractor_reads_real_sections() {
        let dir = tempfile::tempdir().unwrap();
        let container_dir = dir.path().join("container");
        std::fs::create_dir_all(&container_dir).unwrap();

        let sec_a: Vec<u8> = (0..5000u32).map(|i| (i % 256) as u8).collect();
        let sec_b: Vec<u8> = (0..70_000_000u32).map(|i| ((i * 7) % 256) as u8).collect();

        use sha2::{Digest, Sha256};
        let hash_of = |data: &[u8]| -> String {
            let mut hasher = Sha256::new();
            hasher.update(data);
            hex::encode(hasher.finalize())
        };

        let a_frames = (sec_a.len() + pxc1::BYTES_PER_FRAME - 1) / pxc1::BYTES_PER_FRAME;
        let sections = vec![
            pxc1::Section {
                name: "a".into(),
                start_frame: 1, // frame 0 is reserved for the header
                byte_length: sec_a.len(),
                sha256: hash_of(&sec_a),
            },
            pxc1::Section {
                name: "b".into(),
                start_frame: 1 + a_frames,
                byte_length: sec_b.len(),
                sha256: hash_of(&sec_b),
            },
        ];

        let encoder = pxc1::Encoder::new(&container_dir);
        encoder.create(sections).unwrap();
        encoder.write_section("a", &sec_a).unwrap();
        encoder.write_section("b", &sec_b).unwrap();

        let mut extractor = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        assert_eq!(extractor.decoded_size, (sec_a.len() + sec_b.len()) as u64);

        // Section 'a' occupies offset 0..sec_a.len(); confirm a read spanning
        // most of it (and crossing into b, since sections are frame-aligned
        // with padding between) comes back byte-identical.
        let got = extractor.extract_bytes(0, sec_a.len()).unwrap();
        assert_eq!(got, sec_a);

        // Section 'b' starts at the next frame boundary (64 MiB) per spec
        // §6, not immediately after 'a'. Confirm a read from partway into
        // 'b' matches the source exactly.
        let b_start = extractor.decoded_size as usize - sec_b.len();
        let got_b = extractor.extract_bytes(b_start + 1000, 2000).unwrap();
        assert_eq!(got_b, sec_b[1000..3000]);
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