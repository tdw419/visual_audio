/// PDB Decoder: Spatial Pixels → Bytes
///
/// Decodes Hilbert-ordered RGBA pixels back into table row data.

use crate::pdb::{
    BoundingBox, PdbConfig, PdbError, PdbHeader, PdbResult, HEADER_SIZE, PDB_MAGIC, PDB_VERSION,
};

/// PDB decoder
pub struct PdbDecoder {
    config: PdbConfig,
    canvas: image::RgbaImage,
    header: Option<PdbHeader>,
}

impl PdbDecoder {
    /// Load PDB frame from PNG file
    pub fn load_png<P: AsRef<std::path::Path>>(path: P) -> PdbResult<Self> {
        let canvas = image::open(path.as_ref())
            .map_err(|e| PdbError::IoError(e.to_string()))?
            .to_rgba8();

        let width = canvas.width() as usize;
        let height = canvas.height() as usize;

        if !width.is_power_of_two() || !height.is_power_of_two() {
            return Err(PdbError::InvalidDimensions);
        }

        let config = PdbConfig::new(width, height)?;

        Ok(Self {
            config,
            canvas,
            header: None,
        })
    }

    /// Decode header from frame
    ///
    /// STUB: Currently verifies magic bytes and version only
    pub fn decode_header(&mut self) -> PdbResult<&PdbHeader> {
        // Verify magic bytes at (0,0)-(3,0)
        for (i, &expected) in PDB_MAGIC.iter().enumerate() {
            let pixel = self.canvas.get_pixel(i as u32, 0);
            if pixel[0] != expected {
                return Err(PdbError::DecodingFailed);
            }
        }

        // Verify version at (4,0)
        let version_pixel = self.canvas.get_pixel(4, 0);
        if version_pixel[0] != PDB_VERSION {
            return Err(PdbError::DecodingFailed);
        }

        // Read table count at (5,0)
        let table_count = self.canvas.get_pixel(5, 0)[0];

        // Parse table metadata (Phase 1 Step 4)
        let mut tables = Vec::new();
        let mut x_offset = 6;
        for _ in 0..table_count {
            let mut name_bytes = [0u8; 16];
            for i in 0..16 {
                name_bytes[i] = self.canvas.get_pixel(x_offset, 0)[0];
                x_offset += 1;
            }

            let mut read_u32 = || -> u32 {
                let mut buf = [0u8; 4];
                for i in 0..4 {
                    buf[i] = self.canvas.get_pixel(x_offset, 0)[0];
                    x_offset += 1;
                }
                u32::from_le_bytes(buf)
            };

            let bbox = BoundingBox {
                x_min: read_u32(),
                y_min: read_u32(),
                x_max: read_u32(),
                y_max: read_u32(),
            };

            let row_count = read_u32();
            let row_length = read_u32();

            tables.push(crate::pdb::TableMetadata {
                name: name_bytes,
                bbox,
                row_count,
                row_length,
            });
        }

        let header = PdbHeader {
            version: PDB_VERSION,
            table_count,
            tables,
        };

        self.header = Some(header);
        Ok(self.header.as_ref().unwrap())
    }

    /// Decode a single table from its bounding box
    ///
    /// # Arguments
    /// * `table_name` - Name of table to decode
    ///
    /// # Returns
    /// Raw row bytes (concatenated, fixed-length rows)
    pub fn decode_table(&self, table_name: &str) -> PdbResult<Vec<u8>> {
        if self.header.is_none() {
            return Err(PdbError::DecodingFailed);
        }

        let header = self.header.as_ref().unwrap();

        // Find table by name
        let metadata = header
            .tables
            .iter()
            .find(|t| {
                let name_str = std::str::from_utf8(&t.name)
                    .unwrap_or("")
                    .trim_end_matches('\0');
                name_str == table_name
            })
            .ok_or(PdbError::DecodingFailed)?;

        let bbox = metadata.bbox;
        let expected_bytes = (metadata.row_count * metadata.row_length) as usize;
        let expected_triplets = (expected_bytes + 2) / 3;

        let width = bbox.x_max - bbox.x_min + 1;
        let height = bbox.y_max - bbox.y_min + 1;
        let mut grid_size = width.max(height).next_power_of_two();
        if grid_size < 2 { grid_size = 2; }

        let mut out = Vec::with_capacity(expected_bytes);

        let mut i = 0;
        let mut triplets_found = 0;
        while triplets_found < expected_triplets {
            let (x, y) = crate::hilbert::HilbertCurve::d2xy(grid_size as usize, i);
            i += 1;
            let abs_x = bbox.x_min + x as u32;
            let abs_y = bbox.y_min + y as u32;

            if abs_x <= bbox.x_max && abs_y <= bbox.y_max {
                let pixel = self.canvas.get_pixel(abs_x, abs_y);
                out.push(pixel[0]);
                out.push(pixel[1]);
                out.push(pixel[2]);
                triplets_found += 1;
            }
        }

        out.truncate(expected_bytes);
        Ok(out)
    }

    /// Get reference to internal canvas (for VCC hashing)
    pub fn canvas(&self) -> &image::RgbaImage {
        &self.canvas
    }
}

/// Decoder-specific errors
#[derive(Debug)]
pub enum PdbDecoderError {
    InvalidMagic,
    UnsupportedVersion,
    TableNotFound,
    BoundingBoxCorrupt,
    RowDataCorrupt,
}

impl From<PdbDecoderError> for PdbError {
    fn from(err: PdbDecoderError) -> Self {
        match err {
            PdbDecoderError::InvalidMagic => PdbError::DecodingFailed,
            PdbDecoderError::UnsupportedVersion => PdbError::DecodingFailed,
            PdbDecoderError::TableNotFound => PdbError::DecodingFailed,
            PdbDecoderError::BoundingBoxCorrupt => PdbError::DecodingFailed,
            PdbDecoderError::RowDataCorrupt => PdbError::InvalidRowData,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decoder_load_requires_valid_png() {
        // STUB: Requires a valid test PDB file
        // Will be implemented in Phase 1 Step 5
    }

    #[test]
    fn test_magic_bytes_verification() {
        // STUB: Requires encoded test frame
        // Will be implemented in Phase 1 Step 5
    }

    #[test]
    fn test_table_not_found() {
        // STUB: Requires encoded test frame
        // Will be implemented in Phase 1 Step 5
    }
}