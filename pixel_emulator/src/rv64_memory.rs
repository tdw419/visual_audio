//! RV64 Memory with PixelContainer Backing
//!
//! Maps flat 64-bit memory addresses to pixel coordinates using Hilbert curve.
//! PixelContainer provides the underlying storage abstraction.

use pixel_vm::PixelContainer;
use crate::hilbert::hilbert_d2xy;

/// Memory access error types
#[derive(Debug, Clone)]
pub enum MemoryError {
    AddressOutOfBounds { addr: u64, size: u64 },
    MisalignedAccess { addr: u64, alignment: u64 },
    PageFault { addr: u64, access: String },
}

/// RV64 memory backed by PixelContainer
#[derive(Debug, Clone)]
pub struct RV64Memory {
    container: PixelContainer,
    page_size: u64,
    total_pages: u64,
    memory_size: u64,
    hilbert_order: u32,
    pixels_per_byte: u32,
}

impl RV64Memory {
    /// Create new RV64 memory with given size
    pub fn new(size: u64, page_size: u64) -> Self {
        let total_pages = size / page_size;
        log::info!("Creating RV64Memory: {} bytes, {} pages", size, total_pages);

        // Calculate Hilbert grid dimensions
        // Each byte needs 3 pixels (RGB) in depth=3 container
        let total_pixels_needed = (size as u64) * 3;
        let grid_size = (total_pixels_needed as f64).sqrt().ceil() as u32;

        // Round up to next power of 2 for Hilbert
        let hilbert_order = grid_size.next_power_of_two();
        let pixels_per_byte = 3;

        log::info!(
            "Hilbert grid: {}x{} (order {}), {} pixels/byte",
            hilbert_order, hilbert_order, hilbert_order, pixels_per_byte
        );

        let container = PixelContainer::new(hilbert_order, hilbert_order, pixels_per_byte);

        RV64Memory {
            container,
            page_size,
            total_pages,
            memory_size: size,
            hilbert_order,
            pixels_per_byte,
        }
    }

    /// Map flat memory address to pixel coordinates via Hilbert curve
    fn addr_to_pixel(&self, addr: u64, byte_offset: u32) -> (u32, u32, u32) {
        let linear_idx = (addr * self.pixels_per_byte as u64 + byte_offset as u64) / 3;
        let pixel_idx = (linear_idx % (self.hilbert_order as u64 * self.hilbert_order as u64)) as u32;
        let (x, y) = hilbert_d2xy(self.hilbert_order, pixel_idx as u64);
        let z = ((addr * 3 + byte_offset as u64) % 3) as u32;
        (x, y, z)
    }

    /// Read 8-bit byte from address
    pub fn read_u8(&self, addr: u64) -> Result<u8, MemoryError> {
        self.check_bounds(addr, 1)?;

        // For byte reads, we need to reconstruct from 3 RGB pixels
        let (x, y, _) = self.addr_to_pixel(addr, 0);

        // Read RGB triplet
        match self.container.read_region(x, y, 0, 1, 1, 3) {
            Ok(rgb) if rgb.len() == 3 => {
                // Reconstruct byte from RGB (simple mapping for now)
                // TODO: Determine actual RGB->byte encoding scheme
                Ok(rgb[0]) // Use R channel for now
            }
            Ok(_) => Err(MemoryError::PageFault {
                addr,
                access: "read_u8: insufficient pixels".to_string(),
            }),
            Err(e) => Err(MemoryError::PageFault {
                addr,
                access: format!("read_u8: {}", e),
            }),
        }
    }

    /// Read 16-bit halfword from address
    pub fn read_u16(&self, addr: u64) -> Result<u16, MemoryError> {
        self.check_alignment(addr, 2)?;
        let lo = self.read_u8(addr)? as u16;
        let hi = self.read_u8(addr + 1)? as u16;
        Ok((hi << 8) | lo)
    }

    /// Read 32-bit word from address
    pub fn read_u32(&self, addr: u64) -> Result<u32, MemoryError> {
        self.check_alignment(addr, 4)?;
        let lo = self.read_u16(addr)? as u32;
        let hi = self.read_u16(addr + 2)? as u32;
        Ok((hi << 16) | lo)
    }

    /// Read 64-bit doubleword from address
    pub fn read_u64(&self, addr: u64) -> Result<u64, MemoryError> {
        self.check_alignment(addr, 8)?;
        let lo = self.read_u32(addr)? as u64;
        let hi = self.read_u32(addr + 4)? as u64;
        Ok((hi << 32) | lo)
    }

    /// Write 8-bit byte to address
    pub fn write_u8(&mut self, addr: u64, val: u8) -> Result<(), MemoryError> {
        self.check_bounds(addr, 1)?;

        let (x, y, _) = self.addr_to_pixel(addr, 0);

        // Encode byte into RGB triplet
        let rgb = [val, 0, 0]; // Simple encoding: byte in R, G=0, B=0
        self.container.write_region(x, y, 0, &rgb).map_err(|e| MemoryError::PageFault {
            addr,
            access: format!("write_u8: {}", e),
        })
    }

    /// Write 16-bit halfword to address
    pub fn write_u16(&mut self, addr: u64, val: u16) -> Result<(), MemoryError> {
        self.check_alignment(addr, 2)?;
        self.write_u8(addr, (val & 0xFF) as u8)?;
        self.write_u8(addr + 1, ((val >> 8) & 0xFF) as u8)
    }

    /// Write 32-bit word to address
    pub fn write_u32(&mut self, addr: u64, val: u32) -> Result<(), MemoryError> {
        self.check_alignment(addr, 4)?;
        self.write_u16(addr, (val & 0xFFFF) as u16)?;
        self.write_u16(addr + 2, ((val >> 16) & 0xFFFF) as u16)
    }

    /// Write 64-bit doubleword to address
    pub fn write_u64(&mut self, addr: u64, val: u64) -> Result<(), MemoryError> {
        self.check_alignment(addr, 8)?;
        self.write_u32(addr, (val & 0xFFFFFFFF) as u32)?;
        self.write_u32(addr + 4, ((val >> 32) & 0xFFFFFFFF) as u32)
    }

    /// Bulk load bytes into memory
    pub fn load_bytes(&mut self, addr: u64, data: &[u8]) -> Result<(), MemoryError> {
        self.check_bounds(addr, data.len() as u64)?;
        for (i, &byte) in data.iter().enumerate() {
            self.write_u8(addr + i as u64, byte)?;
        }
        Ok(())
    }

    /// Get memory size
    pub fn size(&self) -> u64 {
        self.memory_size
    }

    /// Get page size
    pub fn page_size(&self) -> u64 {
        self.page_size
    }

    /// Total number of pages
    pub fn total_pages(&self) -> u64 {
        self.total_pages
    }

    /// Get Hilbert grid order
    pub fn hilbert_order(&self) -> u32 {
        self.hilbert_order
    }

    // Internal helpers

    fn check_bounds(&self, addr: u64, len: u64) -> Result<(), MemoryError> {
        if addr + len > self.memory_size {
            Err(MemoryError::AddressOutOfBounds { addr, size: len })
        } else {
            Ok(())
        }
    }

    fn check_alignment(&self, addr: u64, alignment: u64) -> Result<(), MemoryError> {
        if addr % alignment != 0 {
            Err(MemoryError::MisalignedAccess { addr, alignment })
        } else {
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_creation() {
        let mem = RV64Memory::new(65536, 4096);
        assert_eq!(mem.size(), 65536);
        assert_eq!(mem.page_size(), 4096);
        assert_eq!(mem.total_pages(), 16);
        assert!(mem.hilbert_order() >= 256); // Should be power of 2
    }

    #[test]
    fn test_write_read_byte() {
        let mut mem = RV64Memory::new(4096, 4096);

        // Write and read back
        mem.write_u8(0x100, 0xAB).unwrap();
        let val = mem.read_u8(0x100).unwrap();
        assert_eq!(val, 0xAB);
    }

    #[test]
    fn test_write_read_word() {
        let mut mem = RV64Memory::new(4096, 4096);

        mem.write_u16(0x100, 0x1234).unwrap();
        let val = mem.read_u16(0x100).unwrap();
        assert_eq!(val, 0x1234);
    }

    #[test]
    fn test_write_read_dword() {
        let mut mem = RV64Memory::new(4096, 4096);

        mem.write_u32(0x100, 0xDEADBEEF).unwrap();
        let val = mem.read_u32(0x100).unwrap();
        assert_eq!(val, 0xDEADBEEF);
    }

    #[test]
    fn test_write_read_qword() {
        let mut mem = RV64Memory::new(4096, 4096);

        mem.write_u64(0x100, 0xDEADBEEFCAFEBABE).unwrap();
        let val = mem.read_u64(0x100).unwrap();
        assert_eq!(val, 0xDEADBEEFCAFEBABE);
    }

    #[test]
    fn test_alignment_check() {
        let mem = RV64Memory::new(65536, 4096);
        assert!(mem.check_alignment(0, 4).is_ok());
        assert!(mem.check_alignment(1, 4).is_err());
        assert!(mem.check_alignment(8, 8).is_ok());
        assert!(mem.check_alignment(7, 8).is_err());
    }

    #[test]
    fn test_bounds_check() {
        let mem = RV64Memory::new(4096, 4096);
        assert!(mem.check_bounds(0, 100).is_ok());
        assert!(mem.check_bounds(4000, 96).is_ok());
        assert!(mem.check_bounds(4000, 100).is_err());
    }

    #[test]
    fn test_bulk_load() {
        let mut mem = RV64Memory::new(4096, 4096);

        let data = vec![0xAA, 0xBB, 0xCC, 0xDD];
        mem.load_bytes(0x100, &data).unwrap();

        assert_eq!(mem.read_u8(0x100).unwrap(), 0xAA);
        assert_eq!(mem.read_u8(0x101).unwrap(), 0xBB);
        assert_eq!(mem.read_u8(0x102).unwrap(), 0xCC);
        assert_eq!(mem.read_u8(0x103).unwrap(), 0xDD);
    }

    #[test]
    fn test_hilbert_coherence() {
        let mut mem = RV64Memory::new(4096, 4096);

        // Write a pattern
        for i in 0..256 {
            mem.write_u8(i as u64 * 16, i as u8).unwrap();
        }

        // Read back and verify
        for i in 0..256 {
            let val = mem.read_u8(i as u64 * 16).unwrap();
            assert_eq!(val, i as u8, "Failed at offset {}", i);
        }
    }
}