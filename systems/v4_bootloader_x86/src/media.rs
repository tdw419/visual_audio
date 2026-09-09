//! Media reader abstraction for V4 boot disk layout
//!
//! Expects disk layout:
//! [0..8]   Magic "V4BOOT00"
//! [8..16]  Manifest Size (u64 LE)
//! [16..X]  Manifest JSON (optional, production use only)
//! [X..X+8] tiles.json Size (u64 LE)
//! [X+8..Y] tiles.json JSON (optional, production use only)
//! [Y..Z]   PNG tiles / blobs (sequential for bootloader)
//!
//! Bootloader Simplified Format (no JSON parsing needed):
//! After the metadata blocks, PNG tiles are stored sequentially:
//! 1. First PNG: kernel (vmlinuz) - single-tile PDB
//! 2. Second PNG: initramfs - single-tile PDB
//! 3. Remaining PNGs: rootfs tiles - tiled PDB (not loaded by bootloader)
//!
//! Each PNG is identified by PNG magic bytes (89 50 4E 47 0D 0A 1A 0A)
//! The bootloader scans sequentially and decodes the first N tiles it needs.

use uefi::proto::media::block::BlockIO;
use alloc::vec::Vec;
use core::str;
use log::info;

pub trait BlockDevice {
    fn read_block(&mut self, lba: u64, buffer: &mut [u8]) -> Result<(), &'static str>;
    fn write_block(&mut self, lba: u64, buffer: &[u8]) -> Result<(), &'static str>;
    fn block_size(&self) -> u64;
}

pub struct UefiBlockDevice<'a> {
    block_io: &'a mut BlockIO,
}

impl<'a> UefiBlockDevice<'a> {
    pub fn new(block_io: &'a mut BlockIO) -> Self {
        Self { block_io }
    }
}

impl<'a> BlockDevice for UefiBlockDevice<'a> {
    fn read_block(&mut self, lba: u64, buffer: &mut [u8]) -> Result<(), &'static str> {
        let media_id = self.block_io.media().media_id();
        self.block_io.read_blocks(media_id, lba, buffer).map_err(|_| "UEFI read error")
    }

    fn write_block(&mut self, lba: u64, buffer: &[u8]) -> Result<(), &'static str> {
        let media_id = self.block_io.media().media_id();
        self.block_io.write_blocks(media_id, lba, buffer).map_err(|_| "UEFI write error")
    }

    fn block_size(&self) -> u64 {
        self.block_io.media().block_size() as u64
    }
}

pub struct V4DiskReader<B: BlockDevice> {
    device: B,
}

impl<B: BlockDevice> V4DiskReader<B> {
    pub fn new(device: B) -> Self {
        Self { device }
    }

    pub fn read_bytes(&mut self, offset: u64, size: usize) -> Result<Vec<u8>, &'static str> {
        let block_size = self.device.block_size();
        let start_lba = offset / block_size;
        let end_lba = (offset + size as u64 + block_size - 1) / block_size;
        let blocks = end_lba - start_lba;

        let mut buffer = alloc::vec![0u8; (blocks * block_size) as usize];

        // Read all blocks in one operation for performance
        self.device.read_block(start_lba, &mut buffer)?;

        let start_offset_in_block = (offset % block_size) as usize;
        let mut result = alloc::vec![0u8; size];
        result.copy_from_slice(&buffer[start_offset_in_block..start_offset_in_block + size]);
        Ok(result)
    }

    pub fn read_u64(&mut self, offset: u64) -> Result<u64, &'static str> {
        let bytes = self.read_bytes(offset, 8)?;
        let mut array = [0u8; 8];
        array.copy_from_slice(&bytes);
        Ok(u64::from_le_bytes(array))
    }

    pub fn locate_tiles_json(&mut self) -> Result<(u64, Vec<u8>), &'static str> {
        const V4_MAGIC: &[u8; 8] = b"V4BOOT00";
        const SCAN_BLOCK_SIZE: usize = 1024 * 1024; // 1MB chunks
        const MAX_SCAN_MB: u64 = 256;
        const START_OFFSET: u64 = 64 * 1024 * 1024; // Skip ESP (start at 64MB)

        // Scan forward from 64MB (partition 2 start) to find V4BOOT00 magic
        let mut scan_offset = START_OFFSET;
        let max_offset = MAX_SCAN_MB * 1024 * 1024;

        while scan_offset < max_offset {
            let read_size = core::cmp::min(SCAN_BLOCK_SIZE, (max_offset - scan_offset) as usize);

            if let Ok(bytes) = self.read_bytes(scan_offset, read_size) {
                for i in 0..(bytes.len() - 8) {
                    if bytes[i..i+8] == *V4_MAGIC {
                        let header_offset = scan_offset + i as u64;
                        info!("Found V4BOOT00 at offset {}", header_offset);

                        let manifest_size = self.read_u64(header_offset + 8)?;
                        let tiles_offset = header_offset + 16 + manifest_size;

                        let tiles_json_size = self.read_u64(tiles_offset)?;
                        let tiles_json_data = self.read_bytes(tiles_offset + 8, tiles_json_size as usize)?;

                        return Ok((tiles_offset + 8, tiles_json_data));
                    }
                }
            }

            scan_offset += SCAN_BLOCK_SIZE as u64;
        }

        Err("V4BOOT00 magic not found")
    }

    /// Find the start offset of the Nth PNG tile (0-indexed)
    ///
    /// This scans sequentially from the metadata blocks, looking for PNG magic bytes.
    /// In the simplified bootloader format, tiles are stored in a known order:
    /// - Tile 0: kernel (vmlinuz)
    /// - Tile 1: initramfs
    /// - Tile 2+: rootfs (not used by bootloader)
    ///
    /// Returns the offset in bytes from disk start, and the approximate size
    /// (size is estimated by scanning for the next PNG magic or end of disk)
    pub fn find_nth_png_tile(&mut self, tile_index: usize) -> Result<(u64, usize), &'static str> {
        let PNG_MAGIC: &[u8; 8] = b"\x89PNG\r\n\x1a\n";

        // Get the end of tiles.json metadata block
        let (_tiles_offset, tiles_data) = self.locate_tiles_json()?;
        let mut scan_offset = _tiles_offset + tiles_data.len() as u64;

        // Scan for PNG magic bytes
        let mut found_count = 0usize;
        let mut current_tile_start = 0u64;
        let block_size = self.device.block_size();

        // Read in 64KB chunks to avoid excessive memory allocation
        const CHUNK_SIZE: usize = 64 * 1024;
        let mut buffer = alloc::vec![0u8; CHUNK_SIZE];

        while found_count <= tile_index {
            // Read next chunk
            let chunk = match self.read_bytes(scan_offset, CHUNK_SIZE) {
                Ok(c) => c,
                Err(_) => {
                    if found_count == tile_index {
                        // We found the last tile and hit end of disk
                        return Err("Cannot determine tile size at disk end");
                    }
                    return Err("PNG tile not found");
                }
            };

            // Scan for PNG magic in this chunk
            for i in 0..chunk.len().saturating_sub(8) {
                if &chunk[i..i + 8] == PNG_MAGIC {
                    if found_count == tile_index {
                        current_tile_start = scan_offset + i as u64;
                        found_count += 1;
                        break;
                    }
                    found_count += 1;
                }
            }

            // If we found the target tile, scan forward to find its size
            if found_count > tile_index {
                scan_offset = current_tile_start + 8; // Skip PNG magic

                // Scan for next PNG magic or end to determine size
                let mut size = 8usize; // Start with magic bytes
                loop {
                    let next_chunk = match self.read_bytes(current_tile_start + size as u64, CHUNK_SIZE) {
                        Ok(c) => c,
                        Err(_) => break, // Hit end of disk
                    };

                    // Look for next PNG magic
                    let mut found_end = false;
                    for i in 0..next_chunk.len().saturating_sub(8) {
                        if &next_chunk[i..i + 8] == PNG_MAGIC {
                            size += i;
                            found_end = true;
                            break;
                        }
                    }

                    if found_end {
                        break;
                    }

                    // Add chunk size, but limit max scan to avoid excessive reads
                    size += CHUNK_SIZE;
                    if size > 256 * 1024 * 1024 {
                        // Sanity cap: no single tile should exceed 256MB
                        break;
                    }
                }

                return Ok((current_tile_start, size));
            }

            scan_offset += CHUNK_SIZE as u64;
        }

        Err("PNG tile not found")
    }
}