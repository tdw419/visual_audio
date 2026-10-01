//! Media reader abstraction — SD card, flash, network
//!
//! Freestanding implementation with no allocator.

use uefi::proto::media::block::BlockIO;

/// Block device interface
pub trait BlockDevice {
    fn read_block(&mut self, lba: u64, buffer: &mut [u8]) -> Result<(), &'static str>;
    fn write_block(&mut self, lba: u64, buffer: &[u8]) -> Result<(), &'static str>;
    fn block_size(&self) -> u64;
}

/// Media source types
pub enum MediaSource {
    SD,
    SPIFlash,
    Network,
}

/// Media reader wrapper
pub struct MediaReader<B: BlockDevice> {
    device: B,
    #[allow(dead_code)]  // TODO: Use for LBA mapping in read_frame() based on media layout
    source: MediaSource,
}

impl<B: BlockDevice> MediaReader<B> {
    pub fn new(device: B, source: MediaSource) -> Self {
        Self { device, source }
    }

    /// Read multiple blocks
    pub fn read_blocks(&mut self, lba: u64, blocks: u64, buffer: &mut [u8]) -> Result<(), &'static str> {
        if buffer.len() as u64 != blocks * self.device.block_size() {
            return Err("buffer size mismatch");
        }

        for i in 0..blocks {
            let offset = (i * self.device.block_size()) as usize;
            self.device.read_block(lba + i, &mut buffer[offset..offset + self.device.block_size() as usize])?;
        }

        Ok(())
    }

    /// Read frames from media (sequential for now)
    pub fn read_frame(&mut self, frame_idx: u64, buffer: &mut [u8]) -> Result<(), &'static str> {
        // TODO: Map frame index to LBA based on media layout
        // STUB: Assume linear mapping, 512-byte blocks
        let lba = frame_idx * (buffer.len() as u64 / 512);
        self.read_blocks(lba, buffer.len() as u64 / 512, buffer)
    }
}

/// Stub implementations

pub struct NullBlockDevice;

impl BlockDevice for NullBlockDevice {
    fn read_block(&mut self, _lba: u64, buffer: &mut [u8]) -> Result<(), &'static str> {
        // STUB: Return zeros — [RETURN_ZERO]
        buffer.fill(0);
        Ok(())
    }

    fn write_block(&mut self, _lba: u64, _buffer: &[u8]) -> Result<(), &'static str> {
        // STUB: No-op — [NO_OP]
        Ok(())
    }

    fn block_size(&self) -> u64 {
        512
    }
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