/// PDB Encoder: Bytes → Spatial Pixels
///
/// Encodes table row data into Hilbert-ordered RGBA pixels.

use crate::pdb::{
    BoundingBox, PdbConfig, PdbError, PdbHeader, PdbResult, HEADER_SIZE, PDB_MAGIC, PDB_VERSION,
};
use crate::hilbert::HilbertCurve;
use image::{RgbaImage, Rgba};

/// PDB encoder
pub struct PdbEncoder {
    config: PdbConfig,
    header: PdbHeader,
    canvas: RgbaImage,
}

impl PdbEncoder {
    /// Create new encoder with specified configuration
    pub fn new(config: PdbConfig, header: PdbHeader) -> Self {
        let canvas = RgbaImage::new(config.width as u32, config.height as u32);

        Self {
            config,
            header,
            canvas,
        }
    }

    /// Encode header into frame (top-left 128×128 region)
    ///
    /// STUB: Currently writes magic bytes and version only
    pub fn encode_header(&mut self) -> PdbResult<()> {
        // Write magic bytes "PDB1" at (0,0)-(3,0)
        for (i, &byte) in PDB_MAGIC.iter().enumerate() {
            self.canvas.put_pixel(i as u32, 0, Rgba([byte, 0, 0, 255]));
        }

        // Write version at (4,0)
        self.canvas
            .put_pixel(4, 0, Rgba([PDB_VERSION, 0, 0, 255]));

        // Write table count at (5,0)
        self.canvas
            .put_pixel(5, 0, Rgba([self.header.table_count, 0, 0, 255]));

        // Table metadata encoding (Phase 1 Step 3)
        let mut x_offset = 6;
        for table in &self.header.tables {
            // Name: 16 bytes
            for i in 0..16 {
                let byte = table.name[i];
                self.canvas.put_pixel(x_offset, 0, Rgba([byte, 0, 0, 255]));
                x_offset += 1;
            }

            // bbox: 4 x u32 LE
            for &val in &[table.bbox.x_min, table.bbox.y_min, table.bbox.x_max, table.bbox.y_max] {
                for byte in val.to_le_bytes() {
                    self.canvas.put_pixel(x_offset, 0, Rgba([byte, 0, 0, 255]));
                    x_offset += 1;
                }
            }

            // row count, row length
            for &val in &[table.row_count, table.row_length] {
                for byte in val.to_le_bytes() {
                    self.canvas.put_pixel(x_offset, 0, Rgba([byte, 0, 0, 255]));
                    x_offset += 1;
                }
            }
        }

        Ok(())
    }

    /// Encode a single table into its bounding box
    ///
    /// # Arguments
    /// * `table_index` - Index in header.tables
    /// * `row_data` - Raw row bytes (concatenated, fixed-length rows)
    pub fn encode_table(&mut self, table_index: usize, row_data: &[u8]) -> PdbResult<()> {
        if table_index >= self.header.tables.len() {
            return Err(PdbError::EncodingFailed);
        }

        let metadata = &self.header.tables[table_index];
        let bbox = metadata.bbox;
        let expected_bytes = (metadata.row_count * metadata.row_length) as usize;
        let actual_data = if row_data.len() > expected_bytes {
            &row_data[..expected_bytes]
        } else {
            row_data
        };

        // Grid size for Hilbert must be power of 2
        let width = bbox.x_max - bbox.x_min + 1;
        let height = bbox.y_max - bbox.y_min + 1;
        let mut grid_size = width.max(height).next_power_of_two();
        if grid_size < 2 { grid_size = 2; }

        let mut i = 0;
        for chunk in actual_data.chunks(3) {
            loop {
                let (x, y) = HilbertCurve::d2xy(grid_size as usize, i);
                i += 1;
                let abs_x = bbox.x_min + x as u32;
                let abs_y = bbox.y_min + y as u32;
                
                if abs_x <= bbox.x_max && abs_y <= bbox.y_max {
                    let r = chunk.get(0).copied().unwrap_or(0);
                    let g = chunk.get(1).copied().unwrap_or(0);
                    let b = chunk.get(2).copied().unwrap_or(0);
                    self.canvas.put_pixel(abs_x, abs_y, Rgba([r, g, b, 255]));
                    break;
                }
            }
        }

        Ok(())
    }

    /// Save encoded frame as PNG
    pub fn save_png<P: AsRef<std::path::Path>>(&self, path: P) -> PdbResult<()> {
        self.canvas
            .save(path.as_ref())
            .map_err(|e| PdbError::IoError(e.to_string()))?;
        Ok(())
    }

    /// Get reference to internal canvas (for VCC hashing)
    pub fn canvas(&self) -> &RgbaImage {
        &self.canvas
    }
}

/// Encoder-specific errors
#[derive(Debug)]
pub enum PdbEncoderError {
    InvalidTableIndex,
    BoundingBoxOverflow,
    RowDataMismatch,
}

impl From<PdbEncoderError> for PdbError {
    fn from(err: PdbEncoderError) -> Self {
        match err {
            PdbEncoderError::InvalidTableIndex => PdbError::EncodingFailed,
            PdbEncoderError::BoundingBoxOverflow => PdbError::EncodingFailed,
            PdbEncoderError::RowDataMismatch => PdbError::InvalidRowData,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encoder_creation() {
        let config = PdbConfig::new(512, 512).unwrap();
        let header = PdbHeader::new();
        let encoder = PdbEncoder::new(config, header);
        assert_eq!(encoder.canvas().width(), 512);
    }

    #[test]
    fn test_magic_bytes_encoding() {
        let config = PdbConfig::new(512, 512).unwrap();
        let header = PdbHeader::new();
        let mut encoder = PdbEncoder::new(config, header);

        encoder.encode_header().unwrap();

        // Check magic bytes at (0,0)-(3,0)
        for (i, &expected) in PDB_MAGIC.iter().enumerate() {
            let pixel = encoder.canvas().get_pixel(i as u32, 0);
            assert_eq!(pixel[0], expected);
        }
    }

    #[test]
    fn test_version_encoding() {
        let config = PdbConfig::new(512, 512).unwrap();
        let header = PdbHeader::new();
        let mut encoder = PdbEncoder::new(config, header);

        encoder.encode_header().unwrap();

        // Check version at (4,0)
        let pixel = encoder.canvas().get_pixel(4, 0);
        assert_eq!(pixel[0], PDB_VERSION);
    }
}