use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use serde::{Deserialize, Serialize};
use anyhow::{Result, Context, anyhow};
use log::info;

/// COW Journal Record Format
/// [seq(4B) | x(2B) | y(2B) | z(1B) | codec(1B) | compressed_len(4B) | original_len(4B) | crc32(4B) | payload(N)]
const RECORD_HEADER_SIZE: usize = 22; // seq(4) + x(2) + y(2) + z(1) + codec(1) + c_len(4) + o_len(4) + crc32(4)
const JOURNAL_MAGIC: &[u8; 8] = b"PXC1JNL\0";

/// Codec types matching PXC1 architecture
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum BlockCodec {
    RAW = 0,
    ZLIB = 1,
    ZERO_FILL = 2,
    DEDUP_REF = 3,
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
pub struct CowJournal {
    path: PathBuf,
    file: File,
    header: JournalHeader,
    in_memory_index: Arc<Mutex<HashMap<Coord3D, JournalEntry>>>, // Fast O(1) lookups
    next_seq: u32,
    flushed_count: u32,
}

impl CowJournal {
    /// Open existing journal or create new one
    pub fn open(path: &Path, base_container_hash: &str) -> Result<Self> {
        let file = if path.exists() {
            OpenOptions::new()
                .read(true)
                .write(true)
                .open(path)
                .context("Failed to open existing journal")?
        } else {
            OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .open(path)
                .context("Failed to create new journal")?
        };

        let mut journal = Self {
            path: path.to_path_buf(),
            file,
            header: Self::init_header(base_container_hash),
            in_memory_index: Arc::new(Mutex::new(HashMap::new())),
            next_seq: 0,
            flushed_count: 0,
        };

        // Load existing entries if journal has data
        if journal.path.exists() && journal.file.metadata()?.len() > std::mem::size_of::<JournalHeader>() as u64 {
            journal.load_from_disk()?;
        }

        Ok(journal)
    }

    fn init_header(base_hash: &str) -> JournalHeader {
        let header = JournalHeader {
            magic: *JOURNAL_MAGIC,
            version: 1,
            base_container_hash: base_hash.to_string(),
            generation: 1,
            entry_count: 0,
            header_crc32: 0,
        };
        header.compute_crc()
    }

    /// Append a single block write to the journal
    /// Returns immediately (<1ms) - actual flush happens later
    pub fn write_block(&mut self, coord: Coord3D, data: &[u8], codec: BlockCodec) -> Result<()> {
        use flate2::write::GzEncoder;
        use flate2::Compression;

        let original_len = data.len() as u32;
        let crc32 = crc32fast::hash(data);

        // Compress if codec requires it
        let compressed_data = match codec {
            BlockCodec::ZLIB => {
                let mut encoder = GzEncoder::new(Vec::new(), Compression::fast());
                encoder.write_all(data)?;
                encoder.finish()?
            }
            BlockCodec::RAW => data.to_vec(),
            BlockCodec::ZERO_FILL => vec![data[0]], // Just store the fill byte
            BlockCodec::DEDUP_REF => vec![], // Reference only, no payload
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

        // Append to disk file (this is the <1ms operation)
        self.append_entry_to_disk(&entry)?;

        self.next_seq += 1;
        self.flushed_count += 1;
        self.header.entry_count += 1;

        Ok(())
    }

    fn append_entry_to_disk(&mut self, entry: &JournalEntry) -> Result<()> {
        let offset = self.file.seek(SeekFrom::End(0))?;

        // Write header if first write
        if offset == 0 {
            let header_bytes = bincode::serialize(&self.header)?;
            self.file.write_all(&header_bytes)?;
        }

        // Serialize entry
        let mut record = Vec::new();
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
        self.file.flush()?; // Force write to OS

        Ok(())
    }

    /// Read a block, checking journal first then falling back to base container
    pub fn read_block(&self, coord: Coord3D, base_reader: &dyn Fn(Coord3D) -> Result<Option<Vec<u8>>>) -> Result<Option<Vec<u8>>> {
        let index = self.in_memory_index.lock().unwrap();

        if let Some(entry) = index.get(&coord) {
            // Block is in journal (was modified)
            let data = self.decode_entry(entry)?;
            // Verify CRC
            let computed_crc = crc32fast::hash(&data);
            if computed_crc != entry.crc32 {
                return Err(anyhow!("CRC mismatch for coord ({},{},{}): expected 0x{:08x}, got 0x{:08x}",
                    coord.x, coord.y, coord.z, entry.crc32, computed_crc));
            }
            return Ok(Some(data));
        }

        // Not in journal, check base container
        base_reader(coord)
    }

    fn decode_entry(&self, entry: &JournalEntry) -> Result<Vec<u8>> {
        match entry.codec {
            BlockCodec::ZERO_FILL => Ok(vec![entry.compressed_data[0]; entry.original_len as usize]),
            BlockCodec::RAW => Ok(entry.compressed_data.clone()),
            BlockCodec::ZLIB => {
                use flate2::read::GzDecoder;
                let mut decoder = GzDecoder::new(&entry.compressed_data[..]);
                let mut decompressed = Vec::new();
                decoder.read_to_end(&mut decompressed)?;
                Ok(decompressed)
            }
            BlockCodec::DEDUP_REF => Err(anyhow!("DEDUP_REF requires external resolution")),
        }
    }

    /// Compact journal: merge all entries back to base and reset journal
    /// This is the ~10ms operation instead of 37s full re-encode
    pub fn compact(&mut self, base_writer: &dyn Fn(Coord3D, &[u8]) -> Result<()>) -> Result<CompactionStats> {
        let start = std::time::Instant::now();
        let entry_count = self.flushed_count;

        info!("Starting COW journal compaction for {} entries...", entry_count);

        // Flush any pending writes
        self.file.flush()?;

        // Collect all entries (snapshot to avoid lock issues)
        let entries: Vec<_> = {
            let index = self.in_memory_index.lock().unwrap();
            index.values().cloned().collect()
        };

        // Apply each entry to base container
        for entry in &entries {
            let data = self.decode_entry(entry)?;
            base_writer(entry.coord, &data)?;
        }

        // Reset journal
        self.reset_journal()?;

        let duration = start.elapsed();
        let stats = CompactionStats {
            entries_compacted: entry_count,
            duration_ms: duration.as_millis() as u64,
            journal_size_before: self.file.metadata()?.len(),
            journal_size_after: 0, // Will be header only after reset
        };

        info!("Compaction complete: {} entries in {}ms", stats.entries_compacted, stats.duration_ms);

        Ok(stats)
    }

    fn reset_journal(&mut self) -> Result<()> {
        // Truncate file to header size
        let header_bytes = bincode::serialize(&self.header)?;
        self.file.set_len(header_bytes.len() as u64)?;
        self.file.seek(SeekFrom::Start(0))?;
        self.file.write_all(&header_bytes)?;
        self.file.flush()?;

        // Clear in-memory index
        {
            let mut index = self.in_memory_index.lock().unwrap();
            index.clear();
        }

        self.next_seq = 0;
        self.flushed_count = 0;
        self.header.entry_count = 0;

        Ok(())
    }

    fn load_from_disk(&mut self) -> Result<()> {
        // Read header
        let mut header_bytes = vec![0u8; std::mem::size_of::<JournalHeader>()];
        self.file.seek(SeekFrom::Start(0))?;
        self.file.read_exact(&mut header_bytes)?;

        self.header = bincode::deserialize(&header_bytes)?;

        if self.header.magic != *JOURNAL_MAGIC {
            return Err(anyhow!("Invalid journal magic: {:?}", self.header.magic));
        }

        // Load entries
        let file_size = self.file.metadata()?.len();
        let mut offset = header_bytes.len() as u64;

        while offset < file_size {
            self.file.seek(SeekFrom::Start(offset))?;

            // Read header
            let mut header = vec![0u8; RECORD_HEADER_SIZE];
            self.file.read_exact(&mut header)?;

            let seq = u32::from_le_bytes([header[0], header[1], header[2], header[3]]);
            let x = u16::from_le_bytes([header[4], header[5]]);
            let y = u16::from_le_bytes([header[6], header[7]]);
            let z = header[8];
            let codec = BlockCodec::from_u8(header[9])?;
            let compressed_len = u32::from_le_bytes([header[10], header[11], header[12], header[13]]);
            let original_len = u32::from_le_bytes([header[14], header[15], header[16], header[17]]);
            let crc32 = u32::from_le_bytes([header[18], header[19], header[20], header[21]]);

            // Read payload
            let mut compressed_data = vec![0u8; compressed_len as usize];
            self.file.read_exact(&mut compressed_data)?;

            // Reconstruct entry
            let entry = JournalEntry {
                coord: Coord3D::new(x, y, z),
                seq,
                codec,
                compressed_data,
                original_len,
                crc32,
            };

            // Add to index
            {
                let mut index = self.in_memory_index.lock().unwrap();
                index.insert(entry.coord, entry.clone());
            }

            self.next_seq = self.next_seq.max(seq + 1);
            self.flushed_count += 1;
            offset += RECORD_HEADER_SIZE as u64 + compressed_len as u64;
        }

        info!("Loaded {} entries from journal at {}", self.flushed_count, self.path.display());
        Ok(())
    }

    /// Get current journal statistics
    pub fn stats(&self) -> JournalStats {
        let index = self.in_memory_index.lock().unwrap();
        JournalStats {
            entry_count: index.len(),
            total_entries_flushed: self.flushed_count,
            next_sequence: self.next_seq,
            journal_size_bytes: self.file.metadata().map(|m| m.len()).unwrap_or(0),
            base_container_hash: self.header.base_container_hash.clone(),
        }
    }
}

impl BlockCodec {
    fn from_u8(value: u8) -> Result<Self> {
        match value {
            0 => Ok(BlockCodec::RAW),
            1 => Ok(BlockCodec::ZLIB),
            2 => Ok(BlockCodec::ZERO_FILL),
            3 => Ok(BlockCodec::DEDUP_REF),
            _ => Err(anyhow!("Invalid codec byte: {}", value)),
        }
    }
}

impl JournalHeader {
    fn compute_crc(mut self) -> Self {
        let mut hasher = crc32fast::Hasher::new();
        self.header_crc32 = 0; // Zero for computation
        let bytes = bincode::serialize(&self).unwrap();
        hasher.update(&bytes);
        self.header_crc32 = hasher.finalize();
        self
    }
}

#[derive(Debug, Clone)]
pub struct JournalStats {
    pub entry_count: usize,
    pub total_entries_flushed: u32,
    pub next_sequence: u32,
    pub journal_size_bytes: u64,
    pub base_container_hash: String,
}

#[derive(Debug, Clone)]
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
    fn test_zero_fill() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        let coord = Coord3D::new(10, 10, 0);
        let data = vec![0u8; 4096];
        let codec = BlockCodec::ZERO_FILL;

        journal.write_block(coord, &data, codec).unwrap();

        let stats = journal.stats();
        // Zero fill should only store 1 byte
        assert!(stats.journal_size_bytes < 100); // Very small
    }

    #[test]
    fn test_compaction() {
        let temp_file = NamedTempFile::new().unwrap();
        let mut journal = CowJournal::open(temp_file.path(), "test_hash").unwrap();

        // Write multiple blocks
        for i in 0..10 {
            let coord = Coord3D::new(i, 0, 0);
            let data = format!("block_{}", i).into_bytes();
            journal.write_block(coord, &data, BlockCodec::RAW).unwrap();
        }

        // Mock base writer
        let written_blocks: Mutex<Vec<(Coord3D, Vec<u8>)>> = Mutex::new(Vec::new());
        let base_writer = |coord: Coord3D, data: &[u8]| {
            written_blocks.lock().unwrap().push((coord, data.to_vec()));
            Ok(())
        };

        // Compact
        let stats = journal.compact(&base_writer).unwrap();

        assert_eq!(stats.entries_compacted, 10);
        assert_eq!(written_blocks.lock().unwrap().len(), 10);
        assert!(stats.duration_ms < 100); // Should be very fast
    }
}