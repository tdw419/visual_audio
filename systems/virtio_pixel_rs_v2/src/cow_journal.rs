use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use serde::{Deserialize, Serialize};
use anyhow::{Result, Context, anyhow};
use log::info;
use sha2::{Digest, Sha256};

/// COW Journal Record Format
/// [seq(4B) | x(2B) | y(2B) | z(1B) | codec(1B) | compressed_len(4B) | original_len(4B) | crc32(4B) | payload(N)]
const RECORD_HEADER_SIZE: usize = 22; // seq(4) + x(2) + y(2) + z(1) + codec(1) + c_len(4) + o_len(4) + crc32(4)
const JOURNAL_MAGIC: &[u8; 8] = b"PXC1JNL\0";
const CURRENT_VERSION: u32 = 1;

/// Codec types matching PXC1 architecture
#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum BlockCodec {
    RAW = 0,
    ZLIB = 1,
    ZSTD = 2,
    ZERO_FILL = 3,
    DEDUP_REF = 4,
}

/// Spatial coordinate in 3D volume
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Coord3D {
    pub x: u16,
    pub y: u16,
    pub z: u8,
}

impl Coord3D {
    pub fn new(x: u16, y: u16, z: u8) -> Self {
        Self { x, y, z }
    }
}

/// COW Journal entry - represents a single block modification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalEntry {
    pub coord: Coord3D,
    pub seq: u32,
    pub codec: BlockCodec,
    pub compressed_data: Vec<u8>,
    pub original_len: u32,
    pub crc32: u32,
}

/// Journal header with metadata and integrity protection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalHeader {
    pub magic: [u8; 8],
    pub version: u32,
    pub base_container_hash: String, // SHA256 of base .pxc1 container
    pub generation: u64,
    pub entry_count: u32,
    pub header_crc32: u32,
}

/// Copy-on-Write Delta Journal
/// Provides instant (sub-millisecond) block writes via append-only logging
#[derive(Debug)]
pub struct CowJournal {
    path: PathBuf,
    file: File,
    header: JournalHeader,
    in_memory_index: Arc<Mutex<HashMap<Coord3D, JournalEntry>>>, // Fast O(1) lookups
    dedup_cache: Arc<Mutex<HashMap<[u8; 32], Vec<u8>>>>,        // Content-addressed block store (SHA256 -> block data)
    next_seq: u32,
    flushed_count: u32,
    header_offset: u64,
}

impl CowJournal {
    /// Compute SHA-256 hash of a block for deduplication
    pub fn hash_block(data: &[u8]) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(data);
        let result = hasher.finalize();
        let mut hash = [0u8; 32];
        hash.copy_from_slice(&result);
        hash
    }

    /// Open existing journal or create new one
    pub fn open(path: &Path, base_container_hash: &str) -> Result<Self> {
        let exists = path.exists();
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .open(path)
            .context("Failed to open or create journal file")?;

        let mut journal = Self {
            path: path.to_path_buf(),
            file,
            header: Self::init_header(base_container_hash),
            in_memory_index: Arc::new(Mutex::new(HashMap::new())),
            dedup_cache: Arc::new(Mutex::new(HashMap::new())),
            next_seq: 0,
            flushed_count: 0,
            header_offset: 0,
        };

        if exists && journal.file.metadata()?.len() > 16 {
            match journal.load_from_disk() {
                Ok(()) => {
                    info!(
                        "Loaded {} entries from journal at {} (in_memory_index size after load: {})",
                        journal.flushed_count,
                        path.display(),
                        journal.in_memory_index.lock().unwrap().len()
                    );
                }
                Err(e) => {
                    log::warn!("Could not load existing journal (will reinitialize): {}", e);
                    journal.reset_journal()?;
                }
            }
        } else {
            journal.write_fresh_header()?;
        }

        Ok(journal)
    }

    fn init_header(base_hash: &str) -> JournalHeader {
        let header = JournalHeader {
            magic: *JOURNAL_MAGIC,
            version: CURRENT_VERSION,
            base_container_hash: base_hash.to_string(),
            generation: 1,
            entry_count: 0,
            header_crc32: 0,
        };
        header.compute_crc()
    }

    fn write_fresh_header(&mut self) -> Result<()> {
        let header_bytes = bincode::serialize(&self.header)?;
        let header_len = header_bytes.len() as u32;

        self.file.seek(SeekFrom::Start(0))?;
        self.file.write_all(JOURNAL_MAGIC)?;
        self.file.write_all(&CURRENT_VERSION.to_le_bytes())?;
        self.file.write_all(&header_len.to_le_bytes())?;
        self.file.write_all(&header_bytes)?;
        self.file.flush()?;

        self.header_offset = 16 + header_len as u64;
        self.file.set_len(self.header_offset)?;
        Ok(())
    }

    /// Automatically choose best codec for a block
    pub fn choose_codec(data: &[u8]) -> BlockCodec {
        if data.is_empty() {
            return BlockCodec::RAW;
        }
        let first = data[0];
        if data.iter().all(|&b| b == first) {
            return BlockCodec::ZERO_FILL;
        }
        // Try ZSTD compression (~18% better than ZLIB on filesystem data)
        if let Ok(compressed) = zstd::encode_all(data, 3) {
            if compressed.len() < (data.len() * 85) / 100 {
                return BlockCodec::ZSTD;
            }
        }
        BlockCodec::RAW
    }

    /// Choose best codec taking in-memory dedup cache into account
    pub fn choose_codec_with_dedup(&self, data: &[u8]) -> BlockCodec {
        if data.is_empty() {
            return BlockCodec::RAW;
        }
        let first = data[0];
        if data.iter().all(|&b| b == first) {
            return BlockCodec::ZERO_FILL;
        }
        let hash = Self::hash_block(data);
        if self.dedup_cache.lock().unwrap().contains_key(&hash) {
            return BlockCodec::DEDUP_REF;
        }
        Self::choose_codec(data)
    }

    /// Append a single block write to the journal
    /// Returns immediately (<1ms) - actual flush happens on writeback / compact
    pub fn write_block(&mut self, coord: Coord3D, data: &[u8], mut codec: BlockCodec) -> Result<()> {
        use flate2::write::GzEncoder;
        use flate2::Compression;

        let original_len = data.len() as u32;
        let crc32 = crc32fast::hash(data);
        let block_hash = Self::hash_block(data);

        // Check if this block is eligible for dedup (non-zero fill)
        if codec != BlockCodec::ZERO_FILL {
            let is_dedup = {
                let dedup = self.dedup_cache.lock().unwrap();
                dedup.contains_key(&block_hash)
            };
            if is_dedup {
                codec = BlockCodec::DEDUP_REF;
            }
        }

        // Compress or encode based on codec
        let compressed_data = match codec {
            BlockCodec::DEDUP_REF => {
                // Store 32-byte SHA-256 hash reference
                block_hash.to_vec()
            }
            BlockCodec::ZLIB => {
                let mut encoder = GzEncoder::new(Vec::new(), Compression::fast());
                encoder.write_all(data)?;
                let compressed = encoder.finish()?;
                // Register uncompressed data in dedup cache for future blocks
                self.dedup_cache.lock().unwrap().insert(block_hash, data.to_vec());
                compressed
            }
            BlockCodec::ZSTD => {
                let compressed = zstd::encode_all(data, 3)?; // Level 3: speed/ratio balance
                // Register uncompressed data in dedup cache for future blocks
                self.dedup_cache.lock().unwrap().insert(block_hash, data.to_vec());
                compressed
            }
            BlockCodec::RAW => {
                // Register uncompressed data in dedup cache for future blocks
                self.dedup_cache.lock().unwrap().insert(block_hash, data.to_vec());
                data.to_vec()
            }
            BlockCodec::ZERO_FILL => {
                vec![data.get(0).copied().unwrap_or(0)]
            }
        };

        let entry = JournalEntry {
            coord,
            seq: self.next_seq,
            codec,
            compressed_data,
            original_len,
            crc32,
        };

        // Update in-memory index for instant access
        {
            let mut index = self.in_memory_index.lock().unwrap();
            index.insert(coord, entry.clone());
        }

        // Append to disk file
        self.append_entry_to_disk(&entry)?;

        self.next_seq += 1;
        self.flushed_count += 1;
        self.header.entry_count += 1;

        Ok(())
    }

    fn append_entry_to_disk(&mut self, entry: &JournalEntry) -> Result<()> {
        self.file.seek(SeekFrom::End(0))?;

        // Serialize entry: [seq(4B) | x(2B) | y(2B) | z(1B) | codec(1B) | compressed_len(4B) | original_len(4B) | crc32(4B) | payload(N)]
        let mut record = Vec::with_capacity(RECORD_HEADER_SIZE + entry.compressed_data.len());
        record.extend_from_slice(&entry.seq.to_le_bytes());
        record.extend_from_slice(&entry.coord.x.to_le_bytes());
        record.extend_from_slice(&entry.coord.y.to_le_bytes());
        record.push(entry.coord.z);
        record.push(entry.codec as u8);
        record.extend_from_slice(&(entry.compressed_data.len() as u32).to_le_bytes());
        record.extend_from_slice(&entry.original_len.to_le_bytes());
        record.extend_from_slice(&entry.crc32.to_le_bytes());
        record.extend_from_slice(&entry.compressed_data);

        self.file.write_all(&record)?;
        Ok(())
    }

    /// Flush journal buffer to disk OS buffer
    pub fn flush(&mut self) -> Result<()> {
        self.file.flush()?;
        Ok(())
    }

    /// Read a block, checking journal first then falling back to base container
    pub fn read_block(&self, coord: Coord3D, base_reader: &dyn Fn(Coord3D) -> Result<Option<Vec<u8>>>) -> Result<Option<Vec<u8>>> {
        let index = self.in_memory_index.lock().unwrap();

        if let Some(entry) = index.get(&coord) {
            let data = self.decode_entry(entry)?;
            let computed_crc = crc32fast::hash(&data);
            if computed_crc != entry.crc32 {
                return Err(anyhow!("CRC mismatch for coord ({},{},{}): expected 0x{:08x}, got 0x{:08x}",
                    coord.x, coord.y, coord.z, entry.crc32, computed_crc));
            }
            return Ok(Some(data));
        }

        base_reader(coord)
    }

    /// Decode compressed journal entry to raw byte payload
    pub fn decode_entry(&self, entry: &JournalEntry) -> Result<Vec<u8>> {
        match entry.codec {
            BlockCodec::ZERO_FILL => {
                let fill_byte = entry.compressed_data.get(0).copied().unwrap_or(0);
                Ok(vec![fill_byte; entry.original_len as usize])
            }
            BlockCodec::RAW => Ok(entry.compressed_data.clone()),
            BlockCodec::ZLIB => {
                use flate2::read::GzDecoder;
                let mut decoder = GzDecoder::new(&entry.compressed_data[..]);
                let mut decompressed = Vec::new();
                decoder.read_to_end(&mut decompressed)?;
                Ok(decompressed)
            }
            BlockCodec::ZSTD => {
                Ok(zstd::decode_all(&entry.compressed_data[..])?)
            }
            BlockCodec::DEDUP_REF => {
                if entry.compressed_data.len() != 32 {
                    return Err(anyhow!(
                        "Invalid DEDUP_REF payload size: expected 32 bytes, got {}",
                        entry.compressed_data.len()
                    ));
                }
                let mut hash = [0u8; 32];
                hash.copy_from_slice(&entry.compressed_data);
                let dedup = self.dedup_cache.lock().unwrap();
                match dedup.get(&hash) {
                    Some(data) => Ok(data.clone()),
                    None => {
                        let hex_hash = hex::encode(hash);
                        Err(anyhow!("DEDUP_REF unresolved: hash {} not found in dedup cache", hex_hash))
                    }
                }
            }
        }
    }

    /// Get a snapshot of all active entries in the journal index
    pub fn get_all_entries(&self) -> HashMap<Coord3D, JournalEntry> {
        self.in_memory_index.lock().unwrap().clone()
    }

    /// Compact journal: merge all entries back to base and reset journal
    pub fn compact(&mut self, base_writer: &dyn Fn(Coord3D, &[u8]) -> Result<()>) -> Result<CompactionStats> {
        let start = std::time::Instant::now();
        let entry_count = self.flushed_count;

        info!("Starting COW journal compaction for {} entries...", entry_count);

        self.file.flush()?;

        let entries: Vec<_> = {
            let index = self.in_memory_index.lock().unwrap();
            index.values().cloned().collect()
        };

        for entry in &entries {
            let data = self.decode_entry(entry)?;
            base_writer(entry.coord, &data)?;
        }

        self.reset_journal()?;

        let duration = start.elapsed();
        let stats = CompactionStats {
            entries_compacted: entry_count,
            duration_ms: duration.as_millis() as u64,
            journal_size_before: self.file.metadata()?.len(),
            journal_size_after: self.header_offset,
        };

        info!("Compaction complete: {} entries in {}ms", stats.entries_compacted, stats.duration_ms);

        Ok(stats)
    }

    /// Reset journal file and clear memory index
    pub fn reset_journal(&mut self) -> Result<()> {
        self.write_fresh_header()?;

        {
            let mut index = self.in_memory_index.lock().unwrap();
            index.clear();
        }
        {
            let mut dedup = self.dedup_cache.lock().unwrap();
            dedup.clear();
        }

        self.next_seq = 0;
        self.flushed_count = 0;
        self.header.entry_count = 0;

        Ok(())
    }

    fn load_from_disk(&mut self) -> Result<()> {
        let mut magic_buf = [0u8; 8];
        self.file.seek(SeekFrom::Start(0))?;
        self.file.read_exact(&mut magic_buf)?;

        if &magic_buf != JOURNAL_MAGIC {
            return Err(anyhow!("Invalid journal magic: {:?}", magic_buf));
        }

        let mut ver_buf = [0u8; 4];
        self.file.read_exact(&mut ver_buf)?;
        let version = u32::from_le_bytes(ver_buf);

        let mut len_buf = [0u8; 4];
        self.file.read_exact(&mut len_buf)?;
        let header_len = u32::from_le_bytes(len_buf) as usize;

        let mut header_bytes = vec![0u8; header_len];
        self.file.read_exact(&mut header_bytes)?;

        self.header = bincode::deserialize(&header_bytes)?;
        self.header_offset = 16 + header_len as u64;

        if version != CURRENT_VERSION {
            return Err(anyhow!("Unsupported journal version: {}", version));
        }

        // Load entries
        let file_size = self.file.metadata()?.len();
        let mut offset = self.header_offset;

        while offset + (RECORD_HEADER_SIZE as u64) <= file_size {
            self.file.seek(SeekFrom::Start(offset))?;

            let mut header = [0u8; RECORD_HEADER_SIZE];
            self.file.read_exact(&mut header)?;

            let seq = u32::from_le_bytes([header[0], header[1], header[2], header[3]]);
            let x = u16::from_le_bytes([header[4], header[5]]);
            let y = u16::from_le_bytes([header[6], header[7]]);
            let z = header[8];
            let codec = BlockCodec::from_u8(header[9])?;
            let compressed_len = u32::from_le_bytes([header[10], header[11], header[12], header[13]]);
            let original_len = u32::from_le_bytes([header[14], header[15], header[16], header[17]]);
            let crc32 = u32::from_le_bytes([header[18], header[19], header[20], header[21]]);

            if offset + (RECORD_HEADER_SIZE as u64) + (compressed_len as u64) > file_size {
                log::warn!("Incomplete record at end of journal, stopping replay");
                break;
            }

            let mut compressed_data = vec![0u8; compressed_len as usize];
            self.file.read_exact(&mut compressed_data)?;

            let entry = JournalEntry {
                coord: Coord3D::new(x, y, z),
                seq,
                codec,
                compressed_data,
                original_len,
                crc32,
            };

            // Register uncompressed payload in dedup cache so subsequent DEDUP_REF entries can resolve it
            match entry.codec {
                BlockCodec::RAW => {
                    let hash = Self::hash_block(&entry.compressed_data);
                    self.dedup_cache.lock().unwrap().insert(hash, entry.compressed_data.clone());
                }
                BlockCodec::ZLIB => {
                    use flate2::read::GzDecoder;
                    let mut decoder = GzDecoder::new(&entry.compressed_data[..]);
                    let mut decompressed = Vec::new();
                    if decoder.read_to_end(&mut decompressed).is_ok() {
                        let hash = Self::hash_block(&decompressed);
                        self.dedup_cache.lock().unwrap().insert(hash, decompressed);
                    }
                }
                BlockCodec::ZSTD => {
                    if let Ok(decompressed) = zstd::decode_all(&entry.compressed_data[..]) {
                        let hash = Self::hash_block(&decompressed);
                        self.dedup_cache.lock().unwrap().insert(hash, decompressed);
                    }
                }
                BlockCodec::ZERO_FILL | BlockCodec::DEDUP_REF => {}
            }

            {
                let mut index = self.in_memory_index.lock().unwrap();
                index.insert(entry.coord, entry.clone());
            }

            // Track max sequence number correctly across loads
            self.next_seq = (self.next_seq).max(seq + 1);
            self.flushed_count += 1;
            offset += RECORD_HEADER_SIZE as u64 + compressed_len as u64;
        }

        Ok(())
    }

    /// Get current journal statistics
    pub fn stats(&self) -> JournalStats {
        let index = self.in_memory_index.lock().unwrap();
        let mut raw_count = 0;
        let mut zlib_count = 0;
        let mut zstd_count = 0;
        let mut zero_fill_count = 0;
        let mut dedup_count = 0;

        for e in index.values() {
            match e.codec {
                BlockCodec::RAW => raw_count += 1,
                BlockCodec::ZLIB => zlib_count += 1,
                BlockCodec::ZSTD => zstd_count += 1,
                BlockCodec::ZERO_FILL => zero_fill_count += 1,
                BlockCodec::DEDUP_REF => dedup_count += 1,
            }
        }
        let dedup_cache_size = self.dedup_cache.lock().unwrap().len();
        JournalStats {
            entry_count: index.len(),
            total_entries_flushed: self.flushed_count,
            next_sequence: self.next_seq,
            journal_size_bytes: self.file.metadata().map(|m| m.len()).unwrap_or(0),
            base_container_hash: self.header.base_container_hash.clone(),
            dedup_entries: dedup_count,
            dedup_cache_size,
            raw_entries: raw_count,
            zlib_entries: zlib_count,
            zstd_entries: zstd_count,
            zero_fill_entries: zero_fill_count,
        }
    }
}

impl BlockCodec {
    fn from_u8(value: u8) -> Result<Self> {
        match value {
            0 => Ok(BlockCodec::RAW),
            1 => Ok(BlockCodec::ZLIB),
            2 => Ok(BlockCodec::ZSTD),
            3 => Ok(BlockCodec::ZERO_FILL),
            4 => Ok(BlockCodec::DEDUP_REF),
            _ => Err(anyhow!("Invalid codec byte: {}", value)),
        }
    }
}

impl JournalHeader {
    fn compute_crc(mut self) -> Self {
        let mut hasher = crc32fast::Hasher::new();
        self.header_crc32 = 0;
        let bytes = bincode::serialize(&self).unwrap();
        hasher.update(&bytes);
        self.header_crc32 = hasher.finalize();
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalStats {
    pub entry_count: usize,
    pub total_entries_flushed: u32,
    pub next_sequence: u32,
    pub journal_size_bytes: u64,
    pub base_container_hash: String,
    #[serde(default)]
    pub dedup_entries: usize,
    #[serde(default)]
    pub dedup_cache_size: usize,
    #[serde(default)]
    pub raw_entries: usize,
    #[serde(default)]
    pub zlib_entries: usize,
    #[serde(default)]
    pub zstd_entries: usize,
    #[serde(default)]
    pub zero_fill_entries: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompactionStats {
    pub entries_compacted: u32,
    pub duration_ms: u64,
    pub journal_size_before: u64,
    pub journal_size_after: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn test_journal_write_read() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        let coord = Coord3D::new(100, 200, 2);
        let data = b"test block data that should persist";
        let codec = BlockCodec::RAW;

        journal.write_block(coord, data, codec).unwrap();

        let base_reader = |_| Ok(None);
        let recovered = journal.read_block(coord, &base_reader).unwrap();
        assert_eq!(recovered.unwrap(), data);
    }

    #[test]
    fn test_zlib_compression() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        let coord = Coord3D::new(50, 50, 1);
        let data = b"repeated pattern repeated pattern repeated pattern";
        let codec = BlockCodec::ZLIB;

        journal.write_block(coord, data, codec).unwrap();

        let base_reader = |_| Ok(None);
        let recovered = journal.read_block(coord, &base_reader).unwrap();
        assert_eq!(recovered.unwrap(), data);
    }

    #[test]
    fn test_zstd_compression() {
        let temp_file = NamedTempFile::new().unwrap();
        let file_path = temp_file.path().to_path_buf();
        let coord = Coord3D::new(50, 50, 1);
        let data = b"structured repeated pattern structured repeated pattern for zstd test";

        {
            let mut journal = CowJournal::open(&file_path, "test_hash_zstd").unwrap();
            journal.write_block(coord, data, BlockCodec::ZSTD).unwrap();
            journal.flush().unwrap();
        }

        let reopened = CowJournal::open(&file_path, "test_hash_zstd").unwrap();
        let base_reader = |_| Ok(None);
        let recovered = reopened.read_block(coord, &base_reader).unwrap().unwrap();
        assert_eq!(recovered, data);
    }

    #[test]
    fn test_zero_fill() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        let coord = Coord3D::new(10, 10, 0);
        let data = vec![0u8; 4096];
        let codec = BlockCodec::ZERO_FILL;

        journal.write_block(coord, &data, codec).unwrap();

        let stats = journal.stats();
        assert!(stats.journal_size_bytes < 200);
    }

    #[test]
    fn test_dedup_write_and_read() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        let block_data = b"identical repeated shared library section 4096 bytes long...";
        let coord1 = Coord3D::new(1, 0, 2);
        let coord2 = Coord3D::new(2, 0, 2);

        // First write: RAW / ZLIB
        journal.write_block(coord1, block_data, BlockCodec::RAW).unwrap();
        let entries = journal.get_all_entries();
        assert_eq!(entries.get(&coord1).unwrap().codec, BlockCodec::RAW);

        // Second write with identical content: should be automatically deduped to DEDUP_REF
        journal.write_block(coord2, block_data, BlockCodec::RAW).unwrap();
        let entries = journal.get_all_entries();
        let entry2 = entries.get(&coord2).unwrap();
        assert_eq!(entry2.codec, BlockCodec::DEDUP_REF);
        assert_eq!(entry2.compressed_data.len(), 32); // 32-byte SHA-256 hash

        // Read both blocks back
        let base_reader = |_| Ok(None);
        let recovered1 = journal.read_block(coord1, &base_reader).unwrap().unwrap();
        let recovered2 = journal.read_block(coord2, &base_reader).unwrap().unwrap();
        assert_eq!(recovered1, block_data);
        assert_eq!(recovered2, block_data);

        let stats = journal.stats();
        assert_eq!(stats.dedup_entries, 1);
        assert_eq!(stats.dedup_cache_size, 1);
    }

    #[test]
    fn test_dedup_persistence_and_reload() {
        let temp_file = NamedTempFile::new().unwrap();
        let file_path = temp_file.path().to_path_buf();

        let block_data = b"unique content that gets duplicated across several sectors";
        let coord1 = Coord3D::new(10, 1, 2);
        let coord2 = Coord3D::new(20, 1, 2);
        let coord3 = Coord3D::new(30, 1, 2);

        {
            let mut journal = CowJournal::open(&file_path, "test_hash_persist").unwrap();
            journal.write_block(coord1, block_data, BlockCodec::ZLIB).unwrap();
            journal.write_block(coord2, block_data, BlockCodec::RAW).unwrap(); // Should auto-dedup
            journal.write_block(coord3, block_data, BlockCodec::DEDUP_REF).unwrap();
            journal.flush().unwrap();
        }

        // Reopen journal from disk
        let reopened = CowJournal::open(&file_path, "test_hash_persist").unwrap();
        let stats = reopened.stats();
        assert_eq!(stats.entry_count, 3);
        assert_eq!(stats.dedup_entries, 2);

        let base_reader = |_| Ok(None);
        for coord in &[coord1, coord2, coord3] {
            let recovered = reopened.read_block(*coord, &base_reader).unwrap().unwrap();
            assert_eq!(recovered, block_data);
        }
    }

    #[test]
    fn test_dedup_compression_ratio() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        // 4KB pseudo-random block (uncompressible by zlib)
        let mut data = vec![0u8; 4096];
        for (i, byte) in data.iter_mut().enumerate() {
            *byte = ((i * 37 + 13) % 256) as u8;
        }

        // Write 10 duplicate 4KB blocks
        for i in 0..10 {
            let coord = Coord3D::new(i, 5, 2);
            journal.write_block(coord, &data, BlockCodec::RAW).unwrap();
        }

        let stats = journal.stats();
        assert_eq!(stats.entry_count, 10);
        assert_eq!(stats.dedup_entries, 9);

        // 1st entry: 22 header + 4096 payload = 4118 bytes
        // 9 dedup entries: 9 * (22 header + 32 hash) = 9 * 54 = 486 bytes
        // Header + 10 records ≈ < 5KB instead of 41KB!
        assert!(stats.journal_size_bytes < 6000);
    }

    #[test]
    fn test_compaction() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        for i in 0..10 {
            let coord = Coord3D::new(i, 0, 0);
            let data = format!("block_{}", i).into_bytes();
            journal.write_block(coord, &data, BlockCodec::RAW).unwrap();
        }

        // Also add 5 dedup entries
        let shared_data = b"shared dedup data across multiple blocks";
        for i in 10..15 {
            let coord = Coord3D::new(i, 0, 0);
            journal.write_block(coord, shared_data, BlockCodec::RAW).unwrap();
        }

        let written_blocks: Mutex<Vec<(Coord3D, Vec<u8>)>> = Mutex::new(Vec::new());
        let base_writer = |coord: Coord3D, data: &[u8]| {
            written_blocks.lock().unwrap().push((coord, data.to_vec()));
            Ok(())
        };

        let stats = journal.compact(&base_writer).unwrap();

        assert_eq!(stats.entries_compacted, 15);
        assert_eq!(written_blocks.lock().unwrap().len(), 15);
        assert!(stats.duration_ms < 100);
    }
}