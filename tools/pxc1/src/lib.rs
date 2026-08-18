//! PXC1 — Pixel Container Format v1
//!
//! Spec: docs/PIXEL_CONTAINER_SPEC_V1.md
//!
//! Core rules:
//! - 4 raw bytes/pixel (RGBA), no offset/splitting
//! - Row-major byte-to-pixel mapping (no Hilbert in v1)
//! - Frame 0 = JSON header with named sections + SHA-256
//! - One PNG per frame (no ffmpeg, no multi-file containers)

use image::{ImageBuffer, ImageError, Rgba, RgbaImage};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::BufWriter;
use std::path::{Path, PathBuf};
use thiserror::Error;

pub const FRAME_SIZE: usize = 4096;
pub const BYTES_PER_FRAME: usize = FRAME_SIZE * FRAME_SIZE * 4; // RGBA
pub const FORMAT_VERSION: &str = "PXC1";

#[derive(Error, Debug)]
pub enum Pxc1Error {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Image encoding/decoding error: {0}")]
    Image(#[from] ImageError),

    #[error("Invalid header JSON: {0}")]
    InvalidJson(#[from] serde_json::Error),

    #[error("Header invalid: {0}")]
    InvalidHeader(String),

    #[error("Section not found: {0}")]
    SectionNotFound(String),

    #[error("SHA256 verification failed for section '{0}'")]
    HashMismatch(String),

    #[error("Frame {0} not found")]
    FrameNotFound(usize),
}

/// Section metadata from the header
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Section {
    pub name: String,
    pub start_frame: usize,
    pub byte_length: usize,
    pub sha256: String,
}

/// PXC1 header (frame 0 JSON)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Header {
    pub format: String,
    pub frame_size: usize,
    pub bytes_per_frame: usize,
    pub sections: Vec<Section>,
    pub total_frames: usize,
}

impl Header {
    pub fn validate(&self) -> Result<(), Pxc1Error> {
        if self.format != FORMAT_VERSION {
            return Err(Pxc1Error::InvalidHeader(format!(
                "Expected format '{}', got '{}'",
                FORMAT_VERSION, self.format
            )));
        }

        if self.frame_size != FRAME_SIZE {
            return Err(Pxc1Error::InvalidHeader(format!(
                "Expected frame_size {}, got {}",
                FRAME_SIZE, self.frame_size
            )));
        }

        if self.bytes_per_frame != BYTES_PER_FRAME {
            return Err(Pxc1Error::InvalidHeader(format!(
                "Expected bytes_per_frame {}, got {}",
                BYTES_PER_FRAME, self.bytes_per_frame
            )));
        }

        // Validate sections don't overlap and are in frame order
        let mut used_frames = HashMap::new();
        for section in &self.sections {
            let frames_needed = (section.byte_length + BYTES_PER_FRAME - 1) / BYTES_PER_FRAME;
            let end_frame = section.start_frame + frames_needed - 1; // end_frame is inclusive, so subtract 1
            for frame in section.start_frame..=end_frame {
                if let Some(&existing_section) = used_frames.get(&frame) {
                    return Err(Pxc1Error::InvalidHeader(format!(
                        "Frame {} used by both '{}' and '{}'",
                        frame, existing_section, section.name
                    )));
                }
                used_frames.insert(frame, &section.name);
            }
        }

        Ok(())
    }

    /// Calculate which frame a byte offset falls into (0-indexed)
    fn frame_for_offset(&self, start_frame: usize, byte_offset: usize) -> Result<usize, Pxc1Error> {
        let bytes_from_start = start_frame * self.bytes_per_frame + byte_offset;
        if bytes_from_start == 0 {
            return Ok(0);
        }
        // Frame 0 is metadata, so byte 0 of payload is at frame 1, offset 0
        let payload_bytes = bytes_from_start.saturating_sub(self.bytes_per_frame);
        let frame = 1 + (payload_bytes / self.bytes_per_frame);
        Ok(frame)
    }

    pub fn get_section(&self, name: &str) -> Result<Section, Pxc1Error> {
        self.sections
            .iter()
            .find(|s| s.name == name)
            .cloned()
            .ok_or_else(|| Pxc1Error::SectionNotFound(name.to_string()))
    }
}

/// Encode data into a PXC1 container
pub struct Encoder {
    dir: PathBuf,
}

impl Encoder {
    pub fn new(dir: impl AsRef<Path>) -> Self {
        Encoder {
            dir: dir.as_ref().to_path_buf(),
        }
    }

    pub fn create(&self, sections: Vec<Section>) -> Result<Header, Pxc1Error> {
        // Calculate total frames needed
        let mut max_frame = 0;
        for section in &sections {
            let end_frame =
                section.start_frame + (section.byte_length + BYTES_PER_FRAME - 1) / BYTES_PER_FRAME;
            max_frame = max_frame.max(end_frame);
        }

        let header = Header {
            format: FORMAT_VERSION.to_string(),
            frame_size: FRAME_SIZE,
            bytes_per_frame: BYTES_PER_FRAME,
            sections,
            total_frames: max_frame,
        };

        header.validate()?;

        // Write header.json
        let header_json = serde_json::to_string_pretty(&header)?;
        fs::write(self.dir.join("header.json"), header_json)?;

        // Write frame_00000.png with header
        self.write_frame_0(&header)?;

        Ok(header)
    }

    fn write_frame_0(&self, header: &Header) -> Result<(), Pxc1Error> {
        let header_json = serde_json::to_vec(header)?;
        let json_len = header_json.len() as u64;

        let mut frame_data = vec![0u8; BYTES_PER_FRAME];
        frame_data[0..8].copy_from_slice(&json_len.to_le_bytes());
        frame_data[8..8 + header_json.len()].copy_from_slice(&header_json);
        // Rest is zero-padded

        self.write_frame(0, &frame_data)?;
        Ok(())
    }

    pub fn write_section(&self, name: &str, data: &[u8]) -> Result<(), Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let header: Header = serde_json::from_str(&header_json)?;

        let section = header.get_section(name)?;

        // Calculate SHA-256
        let mut hasher = Sha256::new();
        hasher.update(data);
        let sha256 = hex::encode(hasher.finalize());

        if section.sha256 != sha256 {
            return Err(Pxc1Error::HashMismatch(format!(
                "Expected {}, got {}",
                section.sha256, sha256
            )));
        }

        if data.len() != section.byte_length {
            return Err(Pxc1Error::InvalidHeader(format!(
                "Section '{}': expected {} bytes, got {}",
                name,
                section.byte_length,
                data.len()
            )));
        }

        // Write data to frames
        let mut offset = 0;
        let mut frame_idx = section.start_frame;
        let mut frame_offset = 0;

        while offset < data.len() {
            let bytes_in_frame = (BYTES_PER_FRAME - frame_offset).min(data.len() - offset);
            let chunk = &data[offset..offset + bytes_in_frame];

            // Read existing frame (or create new)
            let frame_path = self.frame_path(frame_idx);
            let mut frame_data = if frame_path.exists() {
                read_frame_data(&frame_path)?
            } else {
                vec![0u8; BYTES_PER_FRAME]
            };

            // Write chunk at frame_offset
            frame_data[frame_offset..frame_offset + bytes_in_frame].copy_from_slice(chunk);
            self.write_frame(frame_idx, &frame_data)?;

            offset += bytes_in_frame;
            frame_offset = 0;
            frame_idx += 1;
        }

        Ok(())
    }

    pub fn write_section_streaming<R: std::io::Read>(&self, name: &str, mut reader: R) -> Result<(), Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let header: Header = serde_json::from_str(&header_json)?;

        let section = header.get_section(name)?;

        let mut hasher = Sha256::new();
        let mut total_bytes = 0;

        let mut frame_idx = section.start_frame;
        let mut buffer = vec![0u8; BYTES_PER_FRAME];

        while total_bytes < section.byte_length {
            let bytes_to_read = (section.byte_length - total_bytes).min(BYTES_PER_FRAME);
            let chunk = &mut buffer[0..bytes_to_read];
            
            reader.read_exact(chunk).map_err(|e| Pxc1Error::Io(e))?;
            
            hasher.update(&chunk);
            
            // Zero pad the rest of the frame if it's the last one
            for i in bytes_to_read..BYTES_PER_FRAME {
                buffer[i] = 0;
            }

            self.write_frame(frame_idx, &buffer)?;
            
            total_bytes += bytes_to_read;
            frame_idx += 1;
        }

        let sha256 = hex::encode(hasher.finalize());
        if section.sha256 != sha256 {
            return Err(Pxc1Error::HashMismatch(format!(
                "Expected {}, got {}",
                section.sha256, sha256
            )));
        }

        Ok(())
    }

    fn frame_path(&self, index: usize) -> PathBuf {
        self.dir.join(format!("frame_{:05}.png", index))
    }

    /// Write (or overwrite) a single frame's PNG. Used both by the normal
    /// section-encoding path and by write-back patching, where only a
    /// handful of frames actually changed and re-encoding the whole
    /// container would be wasteful.
    pub fn write_frame(&self, index: usize, data: &[u8]) -> Result<(), Pxc1Error> {
        assert_eq!(data.len(), BYTES_PER_FRAME);

        // Convert bytes to RgbaImage
        let image: RgbaImage = ImageBuffer::from_raw(FRAME_SIZE as u32, FRAME_SIZE as u32, data.to_vec())
            .ok_or_else(|| Pxc1Error::InvalidHeader("Failed to create image buffer".to_string()))?;

        // Save as PNG
        let path = self.frame_path(index);
        image.save(&path)?;

        Ok(())
    }

    /// Re-read a section's frames straight from disk (no hash check against
    /// the current, possibly-stale header.json) and update header.json's
    /// sha256 for just that section. Call this after write_frame()'ing any
    /// of a section's frames via write-back patching, so the container's
    /// recorded hash matches what's now actually on disk.
    pub fn refresh_section_hash(&self, name: &str) -> Result<String, Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let mut header: Header = serde_json::from_str(&header_json)?;
        let section = header.get_section(name)?;

        let mut data = vec![0u8; section.byte_length];
        let mut offset = 0;
        let mut frame_idx = section.start_frame;
        while offset < section.byte_length {
            let frame_data = read_frame_data(&self.frame_path(frame_idx))?;
            let n = BYTES_PER_FRAME.min(section.byte_length - offset);
            data[offset..offset + n].copy_from_slice(&frame_data[..n]);
            offset += n;
            frame_idx += 1;
        }

        let mut hasher = Sha256::new();
        hasher.update(&data);
        let new_hash = hex::encode(hasher.finalize());

        for s in header.sections.iter_mut() {
            if s.name == name {
                s.sha256 = new_hash.clone();
            }
        }
        let header_json = serde_json::to_string_pretty(&header)?;
        fs::write(self.dir.join("header.json"), &header_json)?;
        self.write_frame_0(&header)?;

        Ok(new_hash)
    }
}

/// Decode data from a PXC1 container
pub struct Decoder {
    dir: PathBuf,
    header: Header,
    frame_cache: Vec<Option<Vec<u8>>>,
}

impl Decoder {
    pub fn open(dir: impl AsRef<Path>) -> Result<Self, Pxc1Error> {
        let dir = dir.as_ref();
        let header_json = fs::read_to_string(dir.join("header.json"))?;
        let header: Header = serde_json::from_str(&header_json)?;
        header.validate()?;

        // Pre-allocate frame cache
        let frame_cache = vec![None; header.total_frames];

        Ok(Decoder {
            dir: dir.to_path_buf(),
            header,
            frame_cache,
        })
    }

    pub fn header(&self) -> &Header {
        &self.header
    }

    /// Reads a section's data, decoding its frames in parallel (each frame's
    /// PNG file is independent, so this scales with available cores instead
    /// of paying ~O(num_frames) sequential PNG-decode latency - the
    /// dominant cost of starting the vhost-user backend on a large
    /// container). A section always starts at frame_offset 0 in its
    /// start_frame (the encoder never leaves a partial frame between
    /// sections), so frames can be decoded independently and concatenated
    /// in order afterward.
    pub fn read_section(&mut self, name: &str) -> Result<Vec<u8>, Pxc1Error> {
        use rayon::prelude::*;
        use std::sync::Mutex;

        let section = self.header.get_section(name)?;
        let mut data = vec![0u8; section.byte_length];
        let start_frame = section.start_frame;
        let dir = self.dir.clone();

        // Decode straight into this frame's slice of the final buffer, in
        // parallel across frames - NOT into an intermediate Vec<Vec<u8>>
        // first. Holding every frame's decoded bytes alongside the final
        // buffer at once would roughly double peak memory (a real OOM risk
        // for multi-GB sections); each thread only ever holds one frame's
        // worth of scratch space at a time this way, same as the old
        // sequential version's footprint, just parallelized.
        let first_err: Mutex<Option<Pxc1Error>> = Mutex::new(None);
        data.par_chunks_mut(BYTES_PER_FRAME)
            .enumerate()
            .for_each(|(i, chunk)| {
                let frame_path = dir.join(format!("frame_{:05}.png", start_frame + i));
                match read_frame_data(&frame_path) {
                    Ok(frame_data) => chunk.copy_from_slice(&frame_data[..chunk.len()]),
                    Err(e) => {
                        let mut slot = first_err.lock().unwrap();
                        if slot.is_none() {
                            *slot = Some(e);
                        }
                    }
                }
            });
        if let Some(e) = first_err.into_inner().unwrap() {
            return Err(e);
        }

        // Verify SHA-256
        let mut hasher = Sha256::new();
        hasher.update(&data);
        let sha256 = hex::encode(hasher.finalize());

        if section.sha256 != sha256 {
            return Err(Pxc1Error::HashMismatch(format!(
                "Expected {}, got {}",
                section.sha256, sha256
            )));
        }

        Ok(data)
    }

    fn get_frame(&mut self, index: usize) -> Result<Vec<u8>, Pxc1Error> {
        if index >= self.header.total_frames {
            return Err(Pxc1Error::FrameNotFound(index));
        }

        // Check cache
        if let Some(ref cached) = self.frame_cache[index] {
            return Ok(cached.clone());
        }

        // Load from disk
        let data = read_frame_data(&self.frame_path(index))?;
        self.frame_cache[index] = Some(data.clone());
        Ok(data)
    }

    fn frame_path(&self, index: usize) -> PathBuf {
        self.dir.join(format!("frame_{:05}.png", index))
    }
}

/// Read frame data from a PNG file
fn read_frame_data(path: &Path) -> Result<Vec<u8>, Pxc1Error> {
    if !path.exists() {
        // Frame hasn't been written yet — return zeros
        return Ok(vec![0u8; BYTES_PER_FRAME]);
    }

    let image: RgbaImage = image::open(path)?.to_rgba8();

    if image.width() != FRAME_SIZE as u32 || image.height() != FRAME_SIZE as u32 {
        return Err(Pxc1Error::InvalidHeader(format!(
            "Expected {}x{}, got {}x{}",
            FRAME_SIZE, FRAME_SIZE, image.width(), image.height()
        )));
    }

    // ImageBuffer's pixels are stored as a flat Vec<u8> in RGBA order
    Ok(image.into_raw())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_round_trip() {
        let test_dir = tempfile::tempdir().unwrap();
        let dir = test_dir.path();

        // Create encoder
        let encoder = Encoder::new(dir);

        // Create sections
        let rootfs_data = b"rootfs test data here".to_vec();
        let rootfs_hash = {
            let mut hasher = Sha256::new();
            hasher.update(&rootfs_data);
            hex::encode(hasher.finalize())
        };

        let sections = vec![Section {
            name: "rootfs".to_string(),
            start_frame: 1,
            byte_length: rootfs_data.len(),
            sha256: rootfs_hash,
        }];

        // Write header
        encoder.create(sections).unwrap();

        // Write section data
        encoder.write_section("rootfs", &rootfs_data).unwrap();

        // Decode and verify
        let mut decoder = Decoder::open(dir).unwrap();
        let decoded = decoder.read_section("rootfs").unwrap();
        assert_eq!(decoded, rootfs_data);
    }

    #[test]
    fn test_header_validation() {
        let mut header = Header {
            format: FORMAT_VERSION.to_string(),
            frame_size: FRAME_SIZE,
            bytes_per_frame: BYTES_PER_FRAME,
            sections: vec![],
            total_frames: 0,
        };

        assert!(header.validate().is_ok());

        // Wrong format
        header.format = "PXC0".to_string();
        assert!(header.validate().is_err());
    }
}