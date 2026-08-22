/// Pixel Database (PDB) Module
///
/// Spatially-encoded database tables stored as RGBA pixels.
/// Uses Hilbert curve mapping to preserve locality for indexed queries.

pub mod compiler;
pub mod decoder;
pub mod encoder;
pub mod vcc;
#[cfg(feature = "gpu")]
pub mod gpu_query;

pub use compiler::{SqliteCompilerError, SqliteToPdb};
pub use decoder::{PdbDecoder, PdbDecoderError};
pub use encoder::{PdbEncoder, PdbEncoderError};
pub use vcc::{VccError, VccIntegrity};
#[cfg(feature = "gpu")]
pub use gpu_query::{GpuQueryConfig, GpuQueryEngine, QueryResult};

use std::fmt;

/// PDB format magic bytes: "PDB1" in RGB
pub const PDB_MAGIC: [u8; 4] = [0x50, 0x44, 0x42, 0x31]; // P, D, B, 1

/// Current PDB format version
pub const PDB_VERSION: u8 = 0x01;

/// Maximum number of tables per PDB frame
pub const MAX_TABLES: usize = 255;

/// Header region size in pixels (128×128)
pub const HEADER_SIZE: usize = 128;

/// Bounding box for a table within the PDB frame
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BoundingBox {
    pub x_min: u32,
    pub y_min: u32,
    pub x_max: u32,
    pub y_max: u32,
}

impl BoundingBox {
    /// Calculate pixel count (width * height)
    pub fn pixel_count(&self) -> usize {
        let width = (self.x_max - self.x_min + 1) as usize;
        let height = (self.y_max - self.y_min + 1) as usize;
        width * height
    }
}

/// Metadata for a single table
#[derive(Debug, Clone)]
pub struct TableMetadata {
    /// Table name (max 16 bytes, null-terminated UTF-8)
    pub name: [u8; 16],
    /// Bounding box in PDB frame
    pub bbox: BoundingBox,
    /// Number of rows in this table
    pub row_count: u32,
    /// Fixed byte length per row
    pub row_length: u32,
}

impl TableMetadata {
    /// Create new table metadata
    pub fn new(name: &str, bbox: BoundingBox, row_count: u32, row_length: u32) -> Self {
        let mut name_bytes = [0u8; 16];
        let name_utf8 = name.as_bytes();
        let copy_len = name_utf8.len().min(15);
        name_bytes[..copy_len].copy_from_slice(&name_utf8[..copy_len]);

        Self {
            name: name_bytes,
            bbox,
            row_count,
            row_length,
        }
    }
}

/// PDB frame header
#[derive(Debug, Clone)]
pub struct PdbHeader {
    /// Format version
    pub version: u8,
    /// Number of tables in this frame
    pub table_count: u8,
    /// Metadata for each table
    pub tables: Vec<TableMetadata>,
}

impl Default for PdbHeader {
    fn default() -> Self {
        Self {
            version: PDB_VERSION,
            table_count: 0,
            tables: Vec::new(),
        }
    }
}

impl PdbHeader {
    /// Create new PDB header
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a table to the header
    pub fn add_table(&mut self, metadata: TableMetadata) -> Result<(), PdbError> {
        if self.table_count as usize >= MAX_TABLES {
            return Err(PdbError::TooManyTables);
        }
        self.table_count += 1;
        self.tables.push(metadata);
        Ok(())
    }

    /// Calculate total header size in pixels
    pub fn header_pixel_count(&self) -> usize {
        HEADER_SIZE * HEADER_SIZE
    }
}

/// PDB frame configuration
#[derive(Debug, Clone)]
pub struct PdbConfig {
    /// Frame width (must be power of 2)
    pub width: usize,
    /// Frame height (must be power of 2)
    pub height: usize,
}

impl Default for PdbConfig {
    fn default() -> Self {
        Self {
            width: 512,
            height: 512,
        }
    }
}

impl PdbConfig {
    /// Create new configuration
    pub fn new(width: usize, height: usize) -> Result<Self, PdbError> {
        if !width.is_power_of_two() || !height.is_power_of_two() {
            return Err(PdbError::InvalidDimensions);
        }
        Ok(Self { width, height })
    }

    /// Calculate grid size for Hilbert mapping (assumes square)
    pub fn grid_size(&self) -> usize {
        self.width
    }

    /// Calculate total pixel count
    pub fn total_pixels(&self) -> usize {
        self.width * self.height
    }
}

/// PDB error types
#[derive(Debug)]
pub enum PdbError {
    InvalidDimensions,
    TooManyTables,
    BoundingBoxConflict,
    InvalidTableName,
    InvalidRowData,
    EncodingFailed,
    DecodingFailed,
    VccCheckFailed,
    IoError(String),
}

impl fmt::Display for PdbError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PdbError::InvalidDimensions => write!(f, "Dimensions must be power of 2"),
            PdbError::TooManyTables => write!(f, "Maximum table count exceeded"),
            PdbError::BoundingBoxConflict => write!(f, "Bounding boxes cannot overlap"),
            PdbError::InvalidTableName => write!(f, "Invalid table name"),
            PdbError::InvalidRowData => write!(f, "Invalid row data"),
            PdbError::EncodingFailed => write!(f, "Encoding failed"),
            PdbError::DecodingFailed => write!(f, "Decoding failed"),
            PdbError::VccCheckFailed => write!(f, "VCC integrity check failed"),
            PdbError::IoError(msg) => write!(f, "IO error: {}", msg),
        }
    }
}

impl std::error::Error for PdbError {}

/// Result type for PDB operations
pub type PdbResult<T> = Result<T, PdbError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bounding_box_pixel_count() {
        let bbox = BoundingBox {
            x_min: 0,
            y_min: 0,
            x_max: 63,
            y_max: 63,
        };
        assert_eq!(bbox.pixel_count(), 4096); // 64 * 64
    }

    #[test]
    fn test_config_validation() {
        assert!(PdbConfig::new(512, 512).is_ok());
        assert!(PdbConfig::new(100, 100).is_err()); // Not power of 2
    }

    #[test]
    fn test_table_metadata_name_truncation() {
        let metadata = TableMetadata::new(
            "very_long_table_name_that_exceeds_limit",
            BoundingBox {
                x_min: 0,
                y_min: 0,
                x_max: 31,
                y_max: 31,
            },
            10,
            100,
        );
        // Name should be truncated to 15 bytes + null terminator
        assert_eq!(metadata.name[15], 0);
    }

    #[test]
    fn test_header_max_tables() {
        let mut header = PdbHeader::new();
        for _ in 0..MAX_TABLES {
            header
                .add_table(TableMetadata::new(
                    "test",
                    BoundingBox {
                        x_min: 0,
                        y_min: 0,
                        x_max: 0,
                        y_max: 0,
                    },
                    0,
                    0,
                ))
                .unwrap();
        }

        // Should fail on MAX_TABLES + 1
        let result = header.add_table(TableMetadata::new(
            "overflow",
            BoundingBox {
                x_min: 0,
                y_min: 0,
                x_max: 0,
                y_max: 0,
            },
            0,
            0,
        ));
        assert!(matches!(result, Err(PdbError::TooManyTables)));
    }
}