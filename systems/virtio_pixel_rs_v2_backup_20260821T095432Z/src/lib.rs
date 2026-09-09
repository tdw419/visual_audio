use anyhow::Result;
use log::{info, warn};
use std::path::{Path, PathBuf};
use sha2::{Digest, Sha256};

pub mod backend;
pub mod wgpu_texture_loader;
pub mod hilbert_compute;
// pub mod hw_decoder;
// pub mod cache_manager;
pub mod cow_journal; // PXC1 COW journal for instant writes
pub use backend::VirtioPixelServer;
use crate::cow_journal::{Coord3D, CowJournal, CompactionStats, JournalStats};

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
    // container directory (has header.json), reads/writes go through a
    // pxc1::Decoder with a bounded per-frame LRU cache instead of a
    // resident whole-container buffer. open() only reads header.json (~5ms,
    // no section decoded), and each read/write faults in only the frames it
    // touches. This replaces both the old ffmpeg/.nut path (per-frame
    // Hilbert decode + BGR/rgb24 pixel-format ambiguity that caused real
    // corruption) and an earlier PXC1 design that eagerly decoded every
    // section into RAM at startup (a 16GB+ resident buffer, briefly doubled
    // to 32GB+ while concatenating sections - the real ceiling on how large
    // a container this backend could open at all).
    pxc1_decoder: Option<pxc1::Decoder>,

    // PXC1 section metadata (name/start_frame/byte_length), kept around
    // (PXC1 mode only) so writeback() can map a write_overlay sector back
    // to the PXC1 frame it belongs to, without re-reading header.json.
    pxc1_sections: Vec<pxc1::Section>,

    // PXC1 COW delta journal for instant (<1ms) persistence
    pub cow_journal: Option<CowJournal>,
    pub base_hash: String,
}

impl SpatialMkvExtractor {
    pub fn new<P: AsRef<Path>>(mkv_path: P, entry_name: &str) -> Result<Self> {
        let mkv_path = mkv_path.as_ref().to_path_buf();

        // PXC1 mode: a container directory has header.json at its root.
        // Load it fully here (once, at startup) instead of going through
        // any frame-cache/Hilbert/ffmpeg path below.
        if mkv_path.is_dir() && mkv_path.join("header.json").exists() {
            let decoder = pxc1::Decoder::open(&mkv_path)
                .map_err(|e| anyhow::anyhow!("PXC1 open failed: {e}"))?;
            let header = decoder.header().clone();

            // decoded_size only depends on section metadata (byte_length),
            // not content, so this is exact without decoding any frames -
            // matches what the old eager path computed after concatenating
            // every section's actual bytes.
            let total_bytes: usize = header.sections.iter().map(|s| s.byte_length).sum();
            let remainder = total_bytes % 512;
            let decoded_size = (if remainder == 0 {
                total_bytes
            } else {
                total_bytes + (512 - remainder)
            }) as u64;
            info!(
                "PXC1: {} sections, {} bytes total disk (lazy frame paging - whole-section sha256 no longer verified eagerly at boot; call journal_stats/compact paths or pxc1-verify for integrity checks)",
                header.sections.len(),
                decoded_size
            );

            // Base container hash (SHA-256 of header.json)
            let header_path = mkv_path.join("header.json");
            let base_hash = if header_path.exists() {
                let h_bytes = std::fs::read(&header_path).unwrap_or_default();
                format!("{:x}", Sha256::digest(&h_bytes))
            } else {
                "unknown".to_string()
            };

            let mut write_overlay = std::collections::HashMap::new();

            // Initialize COW journal
            let journal_path = mkv_path.join(".pxc1_delta.jnl");
            let cow_journal = match CowJournal::open(&journal_path, &base_hash) {
                Ok(jnl) => {
                    let entries = jnl.get_all_entries();
                    if !entries.is_empty() {
                        info!("PXC1 COW: Replaying {} journal entries into write overlay...", entries.len());
                        for (coord, entry) in entries {
                            if let Ok(data) = jnl.decode_entry(&entry) {
                                let global_offset = (coord.y as u64) * (pxc1::BYTES_PER_FRAME as u64) + (coord.x as u64) * 4096;
                                for (i, chunk) in data.chunks(512).enumerate() {
                                    let sector = global_offset / 512 + i as u64;
                                    let mut sector_buf = [0u8; 512];
                                    sector_buf[..chunk.len()].copy_from_slice(chunk);
                                    write_overlay.insert(sector, sector_buf);
                                }
                            }
                        }
                    }
                    Some(jnl)
                }
                Err(e) => {
                    warn!("PXC1 COW: Failed to initialize journal at {}: {}", journal_path.display(), e);
                    None
                }
            };

            info!(
                "PXC1: {} ({} sections, {} bytes total disk, COW journal: {})",
                entry_name,
                header.sections.len(),
                decoded_size,
                if cow_journal.is_some() { "active" } else { "disabled" }
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
                write_overlay,
                pxc1_decoder: Some(decoder),
                pxc1_sections: header.sections.clone(),
                cow_journal,
                base_hash,
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
            pxc1_decoder: None,
            pxc1_sections: Vec::new(),
            cow_journal: None,
            base_hash: "legacy".to_string(),
        })
    }

    /// Write bytes into the in-memory sector overlay and COW delta journal.
    pub fn write(&mut self, offset: u64, data: &[u8]) -> Result<()> {
        for (i, chunk) in data.chunks(512).enumerate() {
            let sector = offset / 512 + i as u64;
            let mut sector_buf = [0u8; 512];
            sector_buf[..chunk.len()].copy_from_slice(chunk);
            self.write_overlay.insert(sector, sector_buf);
        }

        // Append 4KB blocks to COW delta journal for instant persistence
        if let Some(journal) = self.cow_journal.as_mut() {
            let start_block = offset / 4096;
            let end_block = (offset + data.len() as u64 + 4095) / 4096;
            let section_ranges = self
                .pxc1_decoder
                .is_some()
                .then(|| Self::compute_section_ranges(&self.pxc1_sections));

            for b in start_block..end_block {
                let block_offset = b * 4096;
                let frame_idx = (block_offset / (pxc1::BYTES_PER_FRAME as u64)) as u16;
                let block_in_frame = ((block_offset % (pxc1::BYTES_PER_FRAME as u64)) / 4096) as u16;
                let coord = Coord3D::new(block_in_frame, frame_idx, 2);

                let mut block_data = if let (Some(decoder), Some(ranges)) =
                    (self.pxc1_decoder.as_mut(), section_ranges.as_ref())
                {
                    Self::read_base_pxc1_raw(decoder, ranges, block_offset as usize, 4096)
                        .unwrap_or_else(|_| vec![0u8; 4096])
                } else {
                    vec![0u8; 4096]
                };
                // write_overlay already has this write's own sectors inserted
                // above, so this also captures the just-written bytes on top
                // of the base block read.
                Self::apply_write_overlay(&self.write_overlay, block_offset, &mut block_data);

                let codec = journal.choose_codec_with_dedup(&block_data);
                let _ = journal.write_block(coord, &block_data, codec);
            }
        }

        Ok(())
    }

    /// (name, buffer_start, buffer_end) per section in concatenation order -
    /// maps this struct's flat guest-disk byte offsets (sections
    /// concatenated with no inter-section padding) to a PXC1 section name +
    /// offset-within-section.
    fn compute_section_ranges(sections: &[pxc1::Section]) -> Vec<(String, usize, usize)> {
        let mut ranges = Vec::with_capacity(sections.len());
        let mut cursor = 0usize;
        for s in sections {
            ranges.push((s.name.clone(), cursor, cursor + s.byte_length));
            cursor += s.byte_length;
        }
        ranges
    }

    /// Read `length` base (pre-overlay) bytes at guest-disk `offset` through
    /// the decoder's bounded frame cache, splitting at section boundaries as
    /// needed. Bytes past the end of the known sections (e.g. the trailing
    /// sub-512-byte pad) are left zero. Takes `decoder`/`section_ranges` as
    /// explicit parameters (rather than being a `&mut self` method) so
    /// callers can hold it alongside a separate mutable borrow of another
    /// field, e.g. `self.cow_journal`, in the same scope.
    fn read_base_pxc1_raw(
        decoder: &mut pxc1::Decoder,
        section_ranges: &[(String, usize, usize)],
        offset: usize,
        length: usize,
    ) -> Result<Vec<u8>> {
        let mut out = vec![0u8; length];
        let mut cur = offset;
        let mut out_off = 0usize;
        let mut remaining = length;

        while remaining > 0 {
            let Some((name, sec_start, sec_end)) = section_ranges
                .iter()
                .find(|(_, s, e)| cur >= *s && cur < *e)
            else {
                break;
            };
            let sec_off = cur - sec_start;
            let take = (sec_end - cur).min(remaining);
            let chunk = decoder
                .read_range(name, sec_off, take)
                .map_err(|e| anyhow::anyhow!("PXC1 read_range('{name}') failed: {e}"))?;
                
            let total = decoder.hits + decoder.misses;
            if total > 0 && total % 1000 == 0 {
                log::info!("PXC1 Cache Stats: {} hits, {} misses ({:.2}% hit rate)", 
                    decoder.hits, decoder.misses, 
                    (decoder.hits as f64 / total as f64) * 100.0);
            }
            out[out_off..out_off + take].copy_from_slice(&chunk);
            cur += take;
            out_off += take;
            remaining -= take;
        }
        Ok(out)
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

        if self.pxc1_decoder.is_some() {
            let section_ranges = Self::compute_section_ranges(&self.pxc1_sections);
            let decoder = self.pxc1_decoder.as_mut().unwrap();
            let mut result =
                Self::read_base_pxc1_raw(decoder, &section_ranges, offset as usize, bytes_to_read)?;
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

    /// Flush/writeback changes. When COW journal is enabled, this is sub-millisecond (<1ms)
    /// because it only flushes the append-only delta log to disk.
    pub fn writeback(&mut self) -> Result<Vec<String>> {
        if let Some(journal) = self.cow_journal.as_mut() {
            journal.flush()?;
            let count = journal.stats().entry_count;
            return Ok(vec![format!("pxc1_cow_journal:{} entries", count)]);
        }

        // Fallback to legacy frame compaction if journal is not active
        self.compact_internal()
    }

    /// Internal compaction routine: patches dirty frames to disk and updates section hashes
    fn compact_internal(&mut self) -> Result<Vec<String>> {
        if self.write_overlay.is_empty() {
            return Ok(vec![]);
        }
        if self.pxc1_decoder.is_none() {
            return Err(anyhow::anyhow!("writeback() only supported for PXC1 containers"));
        }

        let section_ranges = Self::compute_section_ranges(&self.pxc1_sections);

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
        // Borrows self.pxc1_decoder for the rest of this function; disjoint
        // from self.write_overlay / self.pxc1_sections accessed below, since
        // those are separate fields.
        let decoder = self.pxc1_decoder.as_mut().unwrap();
        let mut touched_sections: std::collections::BTreeSet<String> = Default::default();
        // Spec §6a: only sections WITHOUT frame_hashes yet need the
        // expensive whole-section rehash after this loop. Accelerated
        // sections get their touched frame's hash updated in O(1) inline
        // below and never enter this set.
        let mut sections_needing_full_rehash: std::collections::BTreeSet<String> = Default::default();

        for (section_name, frame_idx) in &dirty_frames {
            let (_, buf_start, _buf_end) = section_ranges
                .iter()
                .find(|(n, _, _)| n == section_name)
                .unwrap();
            let section = self.pxc1_sections.iter().find(|s| &s.name == section_name).unwrap();
            let frame_offset_in_section = (frame_idx - section.start_frame) * pxc1::BYTES_PER_FRAME;
            let frame_buf_start = buf_start + frame_offset_in_section;

            // Base frame bytes, pulled lazily through the decoder's bounded
            // cache (same on-disk frame this container already has) rather
            // than sliced out of a resident whole-section buffer.
            let mut frame_data = (*decoder
                .get_frame(*frame_idx)
                .map_err(|e| anyhow::anyhow!("compact: get_frame({frame_idx}) failed: {e}"))?)
            .clone();
            Self::apply_write_overlay(&self.write_overlay, frame_buf_start as u64, &mut frame_data);

            encoder
                .write_frame(*frame_idx, &frame_data)
                .map_err(|e| anyhow::anyhow!("writeback: write_frame({}) failed: {e}", frame_idx))?;
            info!("writeback: patched frame {} (section '{}')", frame_idx, section_name);
            touched_sections.insert(section_name.clone());

            if section.frame_hashes.is_empty() {
                // Unaccelerated section (predates spec §6a, or never
                // backfilled) - same full-rehash path as before.
                sections_needing_full_rehash.insert(section_name.clone());
            } else {
                // Accelerated: hash just this frame's section payload (not
                // the full zero-padded frame buffer for a partial last
                // frame - must match how frame_hashes[i] was originally
                // computed at write time) and patch that one entry.
                let frame_ordinal = frame_idx - section.start_frame;
                let is_last_frame = frame_ordinal == section.frame_hashes.len().saturating_sub(1);
                let payload_len = if is_last_frame {
                    section.byte_length - frame_ordinal * pxc1::BYTES_PER_FRAME
                } else {
                    pxc1::BYTES_PER_FRAME
                };
                use sha2::{Digest, Sha256};
                let mut frame_hasher = Sha256::new();
                frame_hasher.update(&frame_data[..payload_len]);
                let new_frame_hash = hex::encode(frame_hasher.finalize());
                encoder
                    .update_single_frame_hash(section_name, frame_ordinal, &new_frame_hash)
                    .map_err(|e| anyhow::anyhow!(
                        "writeback: update_single_frame_hash('{}', {}) failed: {e}",
                        section_name, frame_ordinal
                    ))?;
                info!(
                    "writeback: section '{}' frame {} (ordinal {}) hash updated (accelerated, no full rehash)",
                    section_name, frame_idx, frame_ordinal
                );
            }

            // Keep the decoder's cache in sync with what's now actually on
            // disk, so a later read (or the hash pass below) doesn't serve
            // the stale pre-patch bytes that may still be cached.
            decoder.put_frame(*frame_idx, frame_data);
        }

        // Update SHA256 hashes by streaming through each touched section's
        // frames (through the same bounded cache, so just-patched frames are
        // cache-warm) rather than hashing a resident whole-section buffer.
        // Only unaccelerated sections reach this - see loop above.
        for name in &sections_needing_full_rehash {
            let (new_hash, frame_hashes) = decoder
                .hash_section_streaming(name)
                .map_err(|e| anyhow::anyhow!("compact: hash_section_streaming('{name}') failed: {e}"))?;

            encoder
                .update_section_hash(name, &new_hash)
                .map_err(|e| anyhow::anyhow!("writeback: update_section_hash('{}') failed: {e}", name))?;
            encoder
                .set_frame_hashes(name, frame_hashes.clone())
                .map_err(|e| anyhow::anyhow!("writeback: set_frame_hashes('{}') failed: {e}", name))?;
            
            if let Some(s) = self.pxc1_sections.iter_mut().find(|s| &s.name == name) {
                s.sha256 = new_hash.clone();
                s.frame_hashes = frame_hashes;
            }
            info!("writeback: section '{}' sha256 updated to {} (and frame_hashes backfilled)", name, new_hash);
        }

        // No separate "commit to buffer" step needed: patched frames are on
        // disk and cache-warm, and write_overlay (cleared below) is what
        // read() layers on top of the base decoder read - once it's empty,
        // reads fall straight through to the now-current base data.
        self.write_overlay.clear();
        Ok(touched_sections.into_iter().collect())
    }

    /// Compact COW delta journal into base PXC1 container PNG frames and update section SHA-256
    pub fn compact(&mut self) -> Result<CompactionStats> {
        let start = std::time::Instant::now();
        let entries_count = self.cow_journal.as_ref().map(|j| j.stats().entry_count).unwrap_or(self.write_overlay.len());
        let journal_size_before = self.cow_journal.as_ref().map(|j| j.stats().journal_size_bytes).unwrap_or(0);

        if self.write_overlay.is_empty() && entries_count == 0 {
            return Ok(CompactionStats {
                entries_compacted: 0,
                duration_ms: 0,
                journal_size_before,
                journal_size_after: self.cow_journal.as_ref().map(|j| j.stats().journal_size_bytes).unwrap_or(0),
            });
        }

        let touched = self.compact_internal()?;
        info!("Compacted sections: {:?}", touched);

        if let Some(journal) = self.cow_journal.as_mut() {
            journal.reset_journal()?;
        }

        let duration_ms = start.elapsed().as_millis() as u64;
        let journal_size_after = self.cow_journal.as_ref().map(|j| j.stats().journal_size_bytes).unwrap_or(0);
        info!("Compaction complete: {} entries compacted in {}ms", entries_count, duration_ms);

        Ok(CompactionStats {
            entries_compacted: entries_count as u32,
            duration_ms,
            journal_size_before,
            journal_size_after,
        })
    }

    /// Get current COW journal stats if active
    pub fn journal_stats(&self) -> Option<JournalStats> {
        self.cow_journal.as_ref().map(|j| j.stats())
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
        if std::path::Path::new("test.mkv").exists() {
            let extractor = SpatialMkvExtractor::new("test.mkv", "test.pixel").unwrap();
            assert_eq!(extractor.decoded_size, 7 * 1024 * 1024 * 1024);
        }
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
                ..Default::default()
            },
            pxc1::Section {
                name: "b".into(),
                start_frame: 1 + a_frames,
                byte_length: sec_b.len(),
                sha256: hash_of(&sec_b),
                ..Default::default()
            },
        ];

        let encoder = pxc1::Encoder::new(&container_dir);
        encoder.create(sections).unwrap();
        encoder.write_section("a", &sec_a).unwrap();
        encoder.write_section("b", &sec_b).unwrap();

        let mut extractor = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        let total_unpadded = (sec_a.len() + sec_b.len()) as u64;
        let expected_size = (total_unpadded + 511) / 512 * 512;
        assert_eq!(extractor.decoded_size, expected_size);

        // Section 'a' occupies offset 0..sec_a.len(); confirm a read spanning
        // most of it (and crossing into b, since sections are frame-aligned
        // with padding between) comes back byte-identical.
        let got = extractor.extract_bytes(0, sec_a.len()).unwrap();
        assert_eq!(got, sec_a);

        // Section 'b' starts at the next frame boundary (64 MiB) per spec
        // §6, not immediately after 'a'. Confirm a read from partway into
        // 'b' matches the source exactly.
        let b_start = sec_a.len();
        let got_b = extractor.extract_bytes(b_start + 1000, 2000).unwrap();
        assert_eq!(got_b, sec_b[1000..3000]);
    }

    #[test]
    fn test_pxc1_cow_journal_instant_writeback_and_compaction() {
        let dir = tempfile::tempdir().unwrap();
        let container_dir = dir.path().join("container");
        std::fs::create_dir_all(&container_dir).unwrap();

        let rootfs_data: Vec<u8> = vec![0xAA; 100_000];

        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(&rootfs_data);
        let rootfs_hash = hex::encode(hasher.finalize());

        let sections = vec![pxc1::Section {
            name: "rootfs".into(),
            start_frame: 1,
            byte_length: rootfs_data.len(),
            sha256: rootfs_hash,
            ..Default::default()
        }];

        let encoder = pxc1::Encoder::new(&container_dir);
        encoder.create(sections).unwrap();
        encoder.write_section("rootfs", &rootfs_data).unwrap();

        // 1. Open extractor with COW journal
        let mut extractor = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        assert!(extractor.cow_journal.is_some());

        // 2. Perform write
        let new_data = vec![0x55; 4096];
        extractor.write(0, &new_data).unwrap();

        // Read in-session should see new data
        let read_val = extractor.extract_bytes(0, 4096).unwrap();
        assert_eq!(read_val, new_data);

        // 3. Fast writeback (<1ms flush)
        let wb_res = extractor.writeback().unwrap();
        assert!(!wb_res.is_empty());
        assert!(wb_res[0].contains("pxc1_cow_journal"));

        let stats = extractor.journal_stats().unwrap();
        assert!(stats.entry_count > 0);

        // 4. Test crash recovery / restart: new extractor instance on same dir
        let mut extractor2 = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        let read_recovered = extractor2.extract_bytes(0, 4096).unwrap();
        assert_eq!(read_recovered, new_data);

        // 5. Test compaction: merge journal deltas to base PNG
        let comp_stats = extractor2.compact().unwrap();
        assert!(comp_stats.entries_compacted > 0);

        // 6. Test third extractor instance: base container PNG has the compacted data
        let mut extractor3 = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        let read_compacted = extractor3.extract_bytes(0, 4096).unwrap();
        assert_eq!(read_compacted, new_data);
    }

    #[test]
    fn test_compaction_uses_fast_per_frame_hash_path_when_accelerated() {
        // Companion to the test above, but for a section that already has
        // frame_hashes populated (spec §6a). Proves compact_internal() takes
        // the O(1) per-frame path instead of the O(section size) full
        // rehash: header.json's whole-section sha256 must stay exactly as
        // it was (untouched, by design - see §6a), while the touched
        // frame's frame_hashes entry must change to reflect the new bytes,
        // and reads must still return the correct, patched data.
        let dir = tempfile::tempdir().unwrap();
        let container_dir = dir.path().join("container");
        std::fs::create_dir_all(&container_dir).unwrap();

        let rootfs_data: Vec<u8> = vec![0xAA; 100_000];
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(&rootfs_data);
        let rootfs_hash = hex::encode(hasher.finalize());

        let sections = vec![pxc1::Section {
            name: "rootfs".into(),
            start_frame: 1,
            byte_length: rootfs_data.len(),
            sha256: rootfs_hash,
            ..Default::default()
        }];

        let encoder = pxc1::Encoder::new(&container_dir);
        encoder.create(sections).unwrap();
        // write_section (unlike the constructor above) auto-populates
        // frame_hashes - this is what makes the section "accelerated".
        encoder.write_section("rootfs", &rootfs_data).unwrap();

        let read_header = |dir: &std::path::Path| -> pxc1::Header {
            let json = std::fs::read_to_string(dir.join("header.json")).unwrap();
            serde_json::from_str(&json).unwrap()
        };
        let before = read_header(&container_dir);
        let section_before = before.get_section("rootfs").unwrap();
        assert!(!section_before.frame_hashes.is_empty(), "section should be accelerated");
        let sha256_before = section_before.sha256.clone();
        let frame_hash_before = section_before.frame_hashes[0].clone();

        let mut extractor = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        let new_data = vec![0x77; 4096];
        extractor.write(0, &new_data).unwrap();
        extractor.writeback().unwrap();

        let mut extractor2 = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        let comp_stats = extractor2.compact().unwrap();
        assert!(comp_stats.entries_compacted > 0);

        let after = read_header(&container_dir);
        let section_after = after.get_section("rootfs").unwrap();

        // Fast path proof: whole-section sha256 is untouched...
        assert_eq!(section_after.sha256, sha256_before, "sha256 must stay stale (fast path), not be recomputed");
        // ...but the touched frame's own hash changed to match the new bytes.
        assert_ne!(section_after.frame_hashes[0], frame_hash_before);

        // Correctness: a fresh extractor instance reads back the patched data.
        let mut extractor3 = SpatialMkvExtractor::new(&container_dir, "test").unwrap();
        let read_compacted = extractor3.extract_bytes(0, 4096).unwrap();
        assert_eq!(read_compacted, new_data);
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