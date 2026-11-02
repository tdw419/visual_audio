//! PXC1 — Pixel Container Format v1
//!
//! Spec: docs/PIXEL_CONTAINER_SPEC_V1.md
//!
//! Core rules:
//! - 4 raw bytes/pixel (RGBA), no offset/splitting
//! - Row-major byte-to-pixel mapping (no Hilbert in v1)
//! - Frame 0 = JSON header with named sections + SHA-256
//! - One PNG per frame (no ffmpeg, no multi-file containers)

use image::{ImageBuffer, ImageError, RgbaImage};
use lru::LruCache;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self};
use std::num::NonZeroUsize;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use thiserror::Error;

pub const FRAME_SIZE: usize = 4096;
pub const BYTES_PER_FRAME: usize = FRAME_SIZE * FRAME_SIZE * 4; // RGBA
pub const FORMAT_VERSION: &str = "PXC1";

/// Default bounded frame-cache capacity for `Decoder`: 16 frames * 64MB =
/// 1GB working set, regardless of container size. This is what makes
/// `Decoder::open()` + lazy reads scale to disks far larger than RAM,
/// instead of `read_section()`'s eager whole-section materialization.
pub const DEFAULT_CACHE_FRAMES: usize = 16;

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
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Section {
    pub name: String,
    pub start_frame: usize,
    pub byte_length: usize,
    pub sha256: String,
    /// Optional per-frame SHA-256 hashes - see spec §6a. Empty/absent means
    /// "not accelerated": readers/writers fall back to whole-section
    /// `sha256` exactly as before. When populated, `frame_hashes[i]` is the
    /// hash of frame `start_frame + i`'s payload and lets a single patched
    /// frame be re-verified/re-hashed in O(1) instead of re-hashing the
    /// entire section.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub frame_hashes: Vec<String>,
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

        // Write data to frames, hashing each frame's contribution as we go
        // (spec §6a) so this section comes out fully accelerated for free.
        let mut offset = 0;
        let mut frame_idx = section.start_frame;
        let mut frame_offset = 0;
        let mut frame_hashes = Vec::new();

        while offset < data.len() {
            let bytes_in_frame = (BYTES_PER_FRAME - frame_offset).min(data.len() - offset);
            let chunk = &data[offset..offset + bytes_in_frame];

            let mut frame_hasher = Sha256::new();
            frame_hasher.update(chunk);
            frame_hashes.push(hex::encode(frame_hasher.finalize()));

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

        self.set_frame_hashes(name, frame_hashes)?;
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
        let mut frame_hashes = Vec::new();

        while total_bytes < section.byte_length {
            let bytes_to_read = (section.byte_length - total_bytes).min(BYTES_PER_FRAME);
            let chunk = &mut buffer[0..bytes_to_read];

            reader.read_exact(chunk).map_err(|e| Pxc1Error::Io(e))?;

            hasher.update(&chunk);
            let mut frame_hasher = Sha256::new();
            frame_hasher.update(&chunk);
            frame_hashes.push(hex::encode(frame_hasher.finalize()));

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

        self.set_frame_hashes(name, frame_hashes)?;
        Ok(())
    }

    fn frame_path(&self, index: usize) -> PathBuf {
        self.dir.join(format!("frame_{:05}.png", index))
    }

    /// Write (or overwrite) a single frame's PNG. Used both by the normal
    /// section-encoding path and by write-back patching, where only a
    /// handful of frames actually changed and re-encoding the whole
    /// container would be wasteful.
    ///
    /// Copy-on-write: a frame file may be a symlink into another
    /// container's frames (e.g. a zero-copy container fork sharing
    /// unmodified frames with its base to avoid duplicating multi-GB
    /// PNGs). `image.save()` opens the destination path directly, which
    /// follows a symlink and truncates the *target* in place - writing
    /// through such a symlink would silently corrupt the shared base (and
    /// every other fork pointing at the same frame). So: if this frame
    /// path is currently a symlink, unlink just the link (not its target)
    /// before writing, so the new PNG lands as a private, independent
    /// file at this path and the shared frame elsewhere is untouched.
    pub fn write_frame(&self, index: usize, data: &[u8]) -> Result<(), Pxc1Error> {
        assert_eq!(data.len(), BYTES_PER_FRAME);

        let path = self.frame_path(index);
        if let Ok(meta) = fs::symlink_metadata(&path) {
            if meta.file_type().is_symlink() {
                fs::remove_file(&path)?;
            }
        }

        // Convert bytes to RgbaImage
        let image: RgbaImage = ImageBuffer::from_raw(FRAME_SIZE as u32, FRAME_SIZE as u32, data.to_vec())
            .ok_or_else(|| Pxc1Error::InvalidHeader("Failed to create image buffer".to_string()))?;

        // Save as PNG
        image.save(&path)?;

        Ok(())
    }

    /// Re-read a section's frames straight from disk (no hash check against
    /// the current, possibly-stale header.json) and update header.json's
    /// sha256 for just that section. Call this after write_frame()'ing any
    /// of a section's frames via write-back patching, so the container's
    /// recorded hash matches what's now actually on disk.
    /// Also backfills `frame_hashes` (spec §6a) as a side effect - this
    /// already reads every frame of the section to compute the whole-section
    /// hash, so per-frame hashes are free to collect along the way. This is
    /// the migration path for accelerating a container written before §6a
    /// existed (see `pxc1-verify --backfill-frame-hashes`): a one-time full
    /// read, after which future single-frame patches no longer need one.
    pub fn refresh_section_hash(&self, name: &str) -> Result<String, Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let mut header: Header = serde_json::from_str(&header_json)?;
        let section = header.get_section(name)?;

        let mut data = vec![0u8; section.byte_length];
        let mut frame_hashes = Vec::new();
        let mut offset = 0;
        let mut frame_idx = section.start_frame;
        while offset < section.byte_length {
            let frame_data = read_frame_data(&self.frame_path(frame_idx))?;
            let n = BYTES_PER_FRAME.min(section.byte_length - offset);
            data[offset..offset + n].copy_from_slice(&frame_data[..n]);

            let mut frame_hasher = Sha256::new();
            frame_hasher.update(&frame_data[..n]);
            frame_hashes.push(hex::encode(frame_hasher.finalize()));

            offset += n;
            frame_idx += 1;
        }

        let mut hasher = Sha256::new();
        hasher.update(&data);
        let new_hash = hex::encode(hasher.finalize());

        for s in header.sections.iter_mut() {
            if s.name == name {
                s.sha256 = new_hash.clone();
                s.frame_hashes = frame_hashes.clone();
            }
        }
        let header_json = serde_json::to_string_pretty(&header)?;
        fs::write(self.dir.join("header.json"), &header_json)?;
        self.write_frame_0(&header)?;

        Ok(new_hash)
    }

    /// Bulk-set a section's `frame_hashes` (spec §6a). Used right after
    /// initially encoding a section, when every frame's hash is already
    /// known from the write loop - no extra disk read needed.
    pub fn set_frame_hashes(&self, name: &str, frame_hashes: Vec<String>) -> Result<(), Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let mut header: Header = serde_json::from_str(&header_json)?;
        let mut found = false;
        for s in header.sections.iter_mut() {
            if s.name == name {
                s.frame_hashes = frame_hashes.clone();
                found = true;
            }
        }
        if !found {
            return Err(Pxc1Error::SectionNotFound(name.to_string()));
        }
        let header_json = serde_json::to_string_pretty(&header)?;
        fs::write(self.dir.join("header.json"), &header_json)?;
        self.write_frame_0(&header)?;
        Ok(())
    }

    /// Update exactly one frame's hash within an already-accelerated
    /// section (spec §6a) - O(1) read-modify-write of header.json, no
    /// section-wide re-read or rehash. Errors if the section has no
    /// `frame_hashes` yet (not accelerated) or the index is out of range;
    /// callers should check `section.frame_hashes.is_empty()` first and
    /// fall back to `refresh_section_hash` for unaccelerated sections,
    /// exactly as documented in §6a's migration note.
    pub fn update_single_frame_hash(
        &self,
        name: &str,
        frame_offset_in_section: usize,
        new_frame_hash: &str,
    ) -> Result<(), Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let mut header: Header = serde_json::from_str(&header_json)?;
        let section = header
            .sections
            .iter_mut()
            .find(|s| s.name == name)
            .ok_or_else(|| Pxc1Error::SectionNotFound(name.to_string()))?;

        if frame_offset_in_section >= section.frame_hashes.len() {
            return Err(Pxc1Error::InvalidHeader(format!(
                "update_single_frame_hash: section '{}' has {} frame_hashes entries, index {} out of range",
                name,
                section.frame_hashes.len(),
                frame_offset_in_section
            )));
        }
        section.frame_hashes[frame_offset_in_section] = new_frame_hash.to_string();

        let header_json = serde_json::to_string_pretty(&header)?;
        fs::write(self.dir.join("header.json"), &header_json)?;
        self.write_frame_0(&header)?;
        Ok(())
    }

    /// Update header.json with a precomputed section hash and rewrite frame 0.
    pub fn update_section_hash(&self, name: &str, new_hash: &str) -> Result<(), Pxc1Error> {
        let header_json = fs::read_to_string(self.dir.join("header.json"))?;
        let mut header: Header = serde_json::from_str(&header_json)?;
        let mut found = false;
        for s in header.sections.iter_mut() {
            if s.name == name {
                s.sha256 = new_hash.to_string();
                found = true;
            }
        }
        if !found {
            return Err(Pxc1Error::SectionNotFound(name.to_string()));
        }
        let header_json = serde_json::to_string_pretty(&header)?;
        fs::write(self.dir.join("header.json"), &header_json)?;
        self.write_frame_0(&header)?;

        Ok(())
    }
}

/// Decode data from a PXC1 container
#[derive(Debug)]
pub struct Decoder {
    dir: PathBuf,
    header: Header,
    /// Bounded LRU of decoded frames (Arc so a cache hit is a cheap clone,
    /// not a copy of up to 64MB). Capacity is fixed at open() time - see
    /// `DEFAULT_CACHE_FRAMES` / `open_with_cache_frames()`.
    frame_cache: LruCache<usize, Arc<Vec<u8>>>,
    pub hits: usize,
    pub misses: usize,
}

impl Decoder {
    pub fn open(dir: impl AsRef<Path>) -> Result<Self, Pxc1Error> {
        Self::open_with_cache_frames(dir, DEFAULT_CACHE_FRAMES)
    }

    /// Same as `open()`, but with an explicit frame-cache capacity (in
    /// frames, each up to `BYTES_PER_FRAME` bytes). Useful for tests and for
    /// callers with different RAM/locality tradeoffs than the default.
    pub fn open_with_cache_frames(dir: impl AsRef<Path>, cache_frames: usize) -> Result<Self, Pxc1Error> {
        let dir = dir.as_ref();
        let header_json = fs::read_to_string(dir.join("header.json"))?;
        let header: Header = serde_json::from_str(&header_json)?;
        header.validate()?;

        let cache_frames = cache_frames.max(1);
        Ok(Decoder {
            dir: dir.to_path_buf(),
            header,
            frame_cache: LruCache::new(NonZeroUsize::new(cache_frames).unwrap()),
            hits: 0,
            misses: 0,
        })
    }

    pub fn header(&self) -> &Header {
        &self.header
    }

    /// Get (and cache) a single decoded frame. This is the unit of lazy
    /// paging: a cache hit is ~0ms, a miss decodes exactly one PNG
    /// (BYTES_PER_FRAME) and evicts the LRU frame if the cache is full.
    pub fn get_frame(&mut self, index: usize) -> Result<Arc<Vec<u8>>, Pxc1Error> {
        if index >= self.header.total_frames {
            return Err(Pxc1Error::FrameNotFound(index));
        }
        if let Some(cached) = self.frame_cache.get(&index) {
            self.hits += 1;
            return Ok(Arc::clone(cached));
        }
        self.misses += 1;
        let data = Arc::new(read_frame_data(&self.frame_path(index))?);
        self.frame_cache.put(index, Arc::clone(&data));
        Ok(data)
    }

    /// Seed (or overwrite) the cache entry for a frame with already-known
    /// bytes, without touching disk. Callers that just wrote a fresh PNG for
    /// this frame (e.g. compaction) should call this afterward so a later
    /// `get_frame()`/`read_range()` doesn't serve the stale pre-write bytes
    /// that may still be cached.
    pub fn put_frame(&mut self, index: usize, data: Vec<u8>) {
        self.frame_cache.put(index, Arc::new(data));
    }

    /// Read `length` bytes starting at `section_offset` within a named
    /// section, decoding only the frames the range actually touches (through
    /// the bounded frame cache) rather than materializing the whole section.
    /// This is the lazy counterpart to `read_section()`.
    pub fn read_range(&mut self, name: &str, section_offset: usize, length: usize) -> Result<Vec<u8>, Pxc1Error> {
        let section = self.header.get_section(name)?;
        let mut out = Vec::with_capacity(length);
        let mut remaining = length;
        let mut cur = section_offset;

        while remaining > 0 {
            let frame_idx = section.start_frame + cur / BYTES_PER_FRAME;
            let offset_in_frame = cur % BYTES_PER_FRAME;
            let take = (BYTES_PER_FRAME - offset_in_frame).min(remaining);

            let frame = self.get_frame(frame_idx)?;
            out.extend_from_slice(&frame[offset_in_frame..offset_in_frame + take]);

            cur += take;
            remaining -= take;
        }
        Ok(out)
    }

    /// Compute a section's SHA-256 by streaming through its frames (through
    /// the bounded cache) instead of hashing a fully-materialized in-memory
    /// copy. Used by lazy-paging callers after compaction, where the old
    /// path of hashing a resident whole-section RAM buffer no longer applies
    /// - this trades that for re-reading (I/O, not RAM) whatever frames
    /// aren't already cache-warm from just having been patched.
    pub fn hash_section_streaming(&mut self, name: &str) -> Result<(String, Vec<String>), Pxc1Error> {
        let section = self.header.get_section(name)?;
        let frames_needed = (section.byte_length + BYTES_PER_FRAME - 1) / BYTES_PER_FRAME;
        let mut hasher = Sha256::new();
        let mut frame_hashes = Vec::with_capacity(frames_needed);
        let mut remaining = section.byte_length;

        for i in 0..frames_needed {
            let frame_idx = section.start_frame + i;
            let take = remaining.min(BYTES_PER_FRAME);
            let frame = self.get_frame(frame_idx)?;
            hasher.update(&frame[..take]);
            
            let mut frame_hasher = Sha256::new();
            frame_hasher.update(&frame[..take]);
            frame_hashes.push(hex::encode(frame_hasher.finalize()));
            
            remaining -= take;
        }
        Ok((hex::encode(hasher.finalize()), frame_hashes))
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

        // Spec §6a: an accelerated section (non-empty frame_hashes) is
        // verified per-frame as each frame is decoded, instead of hashing
        // the whole reassembled buffer afterward - same parallel pass,
        // just checked against a different (cheaper-to-keep-current)
        // target. Unaccelerated sections (frame_hashes empty - the case
        // for every container written before §6a existed) fall back to
        // exactly the original whole-section hash check below, unchanged.
        let use_frame_hashes = !section.frame_hashes.is_empty();
        let frame_hashes = &section.frame_hashes;
        let name_owned = name.to_string();

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
                    Ok(frame_data) => {
                        chunk.copy_from_slice(&frame_data[..chunk.len()]);
                        if use_frame_hashes {
                            let mut frame_hasher = Sha256::new();
                            frame_hasher.update(&*chunk);
                            let got = hex::encode(frame_hasher.finalize());
                            if frame_hashes.get(i).map(|h| h.as_str()) != Some(got.as_str()) {
                                let mut slot = first_err.lock().unwrap();
                                if slot.is_none() {
                                    *slot = Some(Pxc1Error::HashMismatch(format!(
                                        "section '{}' frame {} (index {} of frame_hashes): got {}",
                                        name_owned, start_frame + i, i, got
                                    )));
                                }
                            }
                        }
                    }
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

        if use_frame_hashes {
            // Already verified per-frame above; section.sha256 is not
            // required to be current for an accelerated section (§6a).
            return Ok(data);
        }

        // Legacy path: whole-section hash (unaccelerated container).
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
            ..Default::default()
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
    fn test_read_range_matches_read_section() {
        let test_dir = tempfile::tempdir().unwrap();
        let dir = test_dir.path();

        // Multi-frame section so read_range has to cross a frame boundary.
        let data: Vec<u8> = (0..(BYTES_PER_FRAME * 2 + 12345))
            .map(|i| (i % 251) as u8)
            .collect();
        let hash = {
            let mut hasher = Sha256::new();
            hasher.update(&data);
            hex::encode(hasher.finalize())
        };

        let encoder = Encoder::new(dir);
        encoder
            .create(vec![Section {
                name: "big".to_string(),
                start_frame: 1,
                byte_length: data.len(),
                sha256: hash,
                ..Default::default()
            }])
            .unwrap();
        encoder.write_section("big", &data).unwrap();

        // Small cache (2 frames) so this also exercises eviction across the
        // section's 3 frames.
        let mut decoder = Decoder::open_with_cache_frames(dir, 2).unwrap();

        // Whole-range read via the lazy path matches the eager one.
        let lazy = decoder.read_range("big", 0, data.len()).unwrap();
        assert_eq!(lazy, data);

        // A read that starts mid-frame and crosses into the next frame.
        let start = BYTES_PER_FRAME - 100;
        let len = 5000;
        let slice = decoder.read_range("big", start, len).unwrap();
        assert_eq!(slice, data[start..start + len]);

        // Streamed hash matches the section's recorded SHA-256.
        let (streamed_hash, _) = decoder.hash_section_streaming("big").unwrap();
        let decoder2 = Decoder::open(dir).unwrap();
        assert_eq!(streamed_hash, decoder2.header().get_section("big").unwrap().sha256);
    }

    #[test]
    fn test_frame_cache_is_bounded() {
        let test_dir = tempfile::tempdir().unwrap();
        let dir = test_dir.path();

        let data = vec![7u8; BYTES_PER_FRAME * 4];
        let hash = {
            let mut hasher = Sha256::new();
            hasher.update(&data);
            hex::encode(hasher.finalize())
        };
        let encoder = Encoder::new(dir);
        encoder
            .create(vec![Section {
                name: "s".to_string(),
                start_frame: 1,
                byte_length: data.len(),
                sha256: hash,
                ..Default::default()
            }])
            .unwrap();
        encoder.write_section("s", &data).unwrap();

        let mut decoder = Decoder::open_with_cache_frames(dir, 2).unwrap();
        // Touch all 4 frames of the section - cache capacity is 2, so this
        // must evict rather than grow unboundedly.
        for i in 0..4 {
            let frame_idx = 1 + i;
            decoder.get_frame(frame_idx).unwrap();
        }
        assert!(decoder.frame_cache.len() <= 2);
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

    #[test]
    fn test_write_frame_breaks_symlink_instead_of_following_it() {
        // Simulates a zero-copy container fork: child's frame_00001.png is a
        // symlink into a shared base container. Patching that frame in the
        // child (as compact_internal() does) must not follow the symlink and
        // mutate the base's file - it must land on a private file instead.
        let base_dir = tempfile::tempdir().unwrap();
        let child_dir = tempfile::tempdir().unwrap();

        let base_encoder = Encoder::new(base_dir.path());
        let original = vec![0xAAu8; BYTES_PER_FRAME];
        base_encoder.write_frame(1, &original).unwrap();

        let base_frame_path = base_dir.path().join("frame_00001.png");
        let child_frame_path = child_dir.path().join("frame_00001.png");
        std::os::unix::fs::symlink(&base_frame_path, &child_frame_path).unwrap();
        assert!(fs::symlink_metadata(&child_frame_path).unwrap().file_type().is_symlink());

        // Patch the frame through the child container.
        let child_encoder = Encoder::new(child_dir.path());
        let patched = vec![0xBBu8; BYTES_PER_FRAME];
        child_encoder.write_frame(1, &patched).unwrap();

        // The child's frame path is now a private regular file with the new data...
        assert!(!fs::symlink_metadata(&child_frame_path).unwrap().file_type().is_symlink());
        let child_bytes = read_frame_data(&child_frame_path).unwrap();
        assert_eq!(child_bytes, patched);

        // ...and the shared base file is untouched.
        let base_bytes = read_frame_data(&base_frame_path).unwrap();
        assert_eq!(base_bytes, original);
    }

    #[test]
    fn test_frame_hashes_accelerated_verify_and_patch() {
        // Spec §6a: writing a section should auto-populate frame_hashes,
        // read_section() should verify per-frame using it, patching one
        // frame via write_frame + update_single_frame_hash should keep
        // verification passing without touching any other frame, and a
        // corrupted frame that's NOT reflected in frame_hashes must still
        // be caught (this isn't a weaker check, just a cheaper one).
        let test_dir = tempfile::tempdir().unwrap();
        let dir = test_dir.path();

        let data: Vec<u8> = (0..(BYTES_PER_FRAME * 3 + 555))
            .map(|i| (i % 253) as u8)
            .collect();
        let hash = {
            let mut hasher = Sha256::new();
            hasher.update(&data);
            hex::encode(hasher.finalize())
        };

        let encoder = Encoder::new(dir);
        encoder
            .create(vec![Section {
                name: "acc".to_string(),
                start_frame: 1,
                byte_length: data.len(),
                sha256: hash,
                ..Default::default()
            }])
            .unwrap();
        encoder.write_section("acc", &data).unwrap();

        // frame_hashes should now be populated: 4 frames (3 full + 1 partial).
        let header_json = fs::read_to_string(dir.join("header.json")).unwrap();
        let header: Header = serde_json::from_str(&header_json).unwrap();
        let section = header.get_section("acc").unwrap();
        assert_eq!(section.frame_hashes.len(), 4);

        // Per-frame-verified read succeeds and returns the right bytes.
        let mut decoder = Decoder::open(dir).unwrap();
        let read_back = decoder.read_section("acc").unwrap();
        assert_eq!(read_back, data);

        // Patch frame index 1 (within the section) via the fast path: write
        // new bytes, hash them in memory, update just that one entry - no
        // section-wide rehash.
        let mut patched_frame = vec![0u8; BYTES_PER_FRAME];
        patched_frame[0..4].copy_from_slice(b"PXC1");
        let mut fh = Sha256::new();
        fh.update(&patched_frame);
        let new_frame_hash = hex::encode(fh.finalize());

        encoder.write_frame(section.start_frame + 1, &patched_frame).unwrap();
        encoder.update_single_frame_hash("acc", 1, &new_frame_hash).unwrap();

        // header.json's sha256 (whole-section) is now stale - by design,
        // per §6a - but per-frame verified reads must still succeed and
        // reflect the patched bytes.
        let mut decoder2 = Decoder::open(dir).unwrap();
        let read_back2 = decoder2.read_section("acc").unwrap();
        assert_eq!(&read_back2[BYTES_PER_FRAME..BYTES_PER_FRAME + 4], b"PXC1");

        // Now corrupt frame index 2's on-disk bytes WITHOUT updating its
        // recorded frame_hashes entry - this must be caught as a mismatch,
        // proving the accelerated path is still a real integrity check.
        let mut corrupted = vec![9u8; BYTES_PER_FRAME];
        corrupted[0] = 1; // different from whatever was there
        encoder.write_frame(section.start_frame + 2, &corrupted).unwrap();
        // (deliberately NOT calling update_single_frame_hash for this one)

        let mut decoder3 = Decoder::open(dir).unwrap();
        let result = decoder3.read_section("acc");
        assert!(matches!(result, Err(Pxc1Error::HashMismatch(_))));
    }
}