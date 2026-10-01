/// V4.1 Tiled PDB — Multi-Frame Tile Management
///
/// Enables encoding large tables (e.g., full rootfs) across multiple PNG frames
/// using a tile grid. Each tile is a standard PDB1 frame; tiles are indexed
/// in a 2D grid (tile_x, tile_y) mapping to individual .pdb.png files.
///
/// Example: 32768×32768 rootfs at 4096×4096 tile size:
///   - 8×8 tile grid (64 frames total)
///   - Frame naming: rootfs.0.0.pdb.png, rootfs.0.1.pdb.png, ..., rootfs.7.7.pdb.png
///   - Single TiledPdbHeader in rootfs.tiles.json tracks all tile metadata

use crate::pdb::{BoundingBox, PdbError, PdbResult, TableMetadata, HEADER_SIZE};
use std::collections::HashMap;
use std::path::PathBuf;

/// Tile coordinates in the 2D grid
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub struct TileCoord {
    pub tile_x: u32,
    pub tile_y: u32,
}

impl TileCoord {
    /// Convert to linear frame index
    pub fn to_index(&self, tiles_per_row: u32) -> usize {
        (self.tile_y * tiles_per_row + self.tile_x) as usize
    }

    /// Convert from linear frame index
    pub fn from_index(index: usize, tiles_per_row: u32) -> Self {
        let idx = index as u32;
        Self {
            tile_x: idx % tiles_per_row,
            tile_y: idx / tiles_per_row,
        }
    }

    /// Convert to local (absolute) pixel coordinates within this tile
    pub fn to_pixel_coord(&self, local_x: u32, local_y: u32, tile_size: u32) -> (u32, u32) {
        let abs_x = self.tile_x * tile_size + local_x;
        let abs_y = self.tile_y * tile_size + local_y;
        (abs_x, abs_y)
    }
}

/// Metadata for a single tile frame
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TileMetadata {
    /// Tile grid coordinates
    pub coord: TileCoord,
    /// Path to this tile's PNG file
    pub file_path: PathBuf,
    /// Bounding box within this tile (usually full tile except edge cases)
    pub bbox: BoundingBox,
    /// Byte offset within the logical table that this tile covers
    pub byte_offset: u64,
    /// Byte count in this tile (last tile may be partial)
    pub byte_count: u64,
}

/// Tile grid configuration
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TileGridConfig {
    /// Size of each tile (must be power of 2)
    pub tile_size: u32,
    /// Total logical width in pixels (may not be power of 2)
    pub logical_width: u32,
    /// Total logical height in pixels (may not be power of 2)
    pub logical_height: u32,
    /// Number of tiles per row
    pub tiles_per_row: u32,
    /// Number of tiles per column
    pub tiles_per_col: u32,
    /// Total number of tiles
    pub total_tiles: u32,
}

impl TileGridConfig {
    /// Create new tile grid configuration
    pub fn new(tile_size: u32, logical_width: u32, logical_height: u32) -> PdbResult<Self> {
        if !tile_size.is_power_of_two() {
            return Err(PdbError::InvalidDimensions);
        }

        let tiles_per_row = (logical_width + tile_size - 1) / tile_size;
        let tiles_per_col = (logical_height + tile_size - 1) / tile_size;
        let total_tiles = tiles_per_row * tiles_per_col;

        Ok(Self {
            tile_size,
            logical_width,
            logical_height,
            tiles_per_row,
            tiles_per_col,
            total_tiles,
        })
    }

    /// Get tile for a given pixel coordinate
    pub fn get_tile_for_pixel(&self, abs_x: u32, abs_y: u32) -> Option<TileCoord> {
        if abs_x >= self.logical_width || abs_y >= self.logical_height {
            return None;
        }

        let tile_x = abs_x / self.tile_size;
        let tile_y = abs_y / self.tile_size;

        if tile_x >= self.tiles_per_row || tile_y >= self.tiles_per_col {
            return None;
        }

        Some(TileCoord { tile_x, tile_y })
    }

    /// Convert absolute pixel to local pixel within tile
    pub fn abs_to_local(&self, abs_x: u32, abs_y: u32, coord: &TileCoord) -> (u32, u32) {
        let local_x = abs_x - coord.tile_x * self.tile_size;
        let local_y = abs_y - coord.tile_y * self.tile_size;
        (local_x, local_y)
    }

    /// Split a binary payload into a list of tiles
    pub fn split_into_tiles(&self, data: &[u8], base_path: &PathBuf, table_name: &str) -> Vec<TileMetadata> {
        let mut tiles = Vec::new();
        // Tile capacity must account for header region (HEADER_SIZE rows at top)
        let data_rows = self.tile_size - HEADER_SIZE as u32;
        let tile_byte_capacity = (data_rows as u64 * self.tile_size as u64) * 3;
        let total_bytes = data.len() as u64;
        
        let mut byte_offset = 0;
        let mut tile_idx = 0;

        while byte_offset < total_bytes {
            let remaining = total_bytes - byte_offset;
            let byte_count = std::cmp::min(remaining, tile_byte_capacity);
            
            let coord = TileCoord::from_index(tile_idx, self.tiles_per_row);
            let filename = format!("{}.{}.{}.pdb.png", table_name, coord.tile_x, coord.tile_y);
            
            // Calculate bbox within this specific tile
            // For v4 blob-table semantics, row_length=1, row_count=byte_count
            // It needs ceil(byte_count / 3) triplets
            let triplets_needed = (byte_count + 2) / 3;
            let bbox_height = if triplets_needed == 0 {
                1
            } else {
                ((triplets_needed as f64) / (self.tile_size as f64)).ceil() as u32
            };
            
            let bbox = BoundingBox {
                x_min: 0,
                y_min: HEADER_SIZE as u32,
                x_max: self.tile_size - 1,
                y_max: HEADER_SIZE as u32 + bbox_height - 1,
            };

            tiles.push(TileMetadata {
                coord,
                file_path: base_path.join(filename),
                bbox,
                byte_offset,
                byte_count,
            });

            byte_offset += byte_count;
            tile_idx += 1;
        }

        tiles
    }
}

/// Tiled PDB header — tracks tiles across multiple frames
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TiledPdbHeader {
    /// Magic bytes for tiled format
    pub magic: [u8; 4],
    /// Format version
    pub version: u8,
    /// Number of tables
    pub table_count: u8,
    /// Tile grid configuration
    pub tile_config: TileGridConfig,
    /// Table metadata (same as PDB1)
    pub tables: Vec<TableMetadata>,
    /// Tile metadata per table (index → Vec<TileMetadata>)
    pub tiles: HashMap<String, Vec<TileMetadata>>,
}

impl TiledPdbHeader {
    /// Create new tiled PDB header
    pub fn new(tile_config: TileGridConfig) -> Self {
        Self {
            magic: *b"TILD",
            version: 0x01,
            table_count: 0,
            tile_config,
            tables: Vec::new(),
            tiles: HashMap::new(),
        }
    }

    /// Add a table to the header
    pub fn add_table(&mut self, metadata: TableMetadata) -> PdbResult<()> {
        if self.table_count as usize >= 255 {
            return Err(PdbError::TooManyTables);
        }
        self.table_count += 1;
        self.tables.push(metadata);
        Ok(())
    }

    /// Add tile metadata for a table
    pub fn add_tile(&mut self, table_name: &str, tile: TileMetadata) {
        self.tiles
            .entry(table_name.to_string())
            .or_insert_with(Vec::new)
            .push(tile);
    }

    /// Get all tiles for a table
    pub fn get_tiles(&self, table_name: &str) -> Option<&[TileMetadata]> {
        self.tiles.get(table_name).map(|v| v.as_slice())
    }
}

/// Multi-frame tile manager — handles opening/closing multiple PDB frames
pub struct TiledPdbManager {
    /// Base path for tile files (e.g., "/tmp/rootfs")
    pub base_path: PathBuf,
    /// Tiled header
    pub header: TiledPdbHeader,
    /// Cached tile decoders (frame_index → PdbDecoder)
    /// STUB: Only store paths, load on demand
    pub cached_frames: HashMap<TileCoord, PathBuf>,
}

impl TiledPdbManager {
    /// Create new tiled PDB manager for writing
    pub fn new_for_write(base_path: &str, header: TiledPdbHeader) -> Self {
        Self {
            base_path: PathBuf::from(base_path),
            header,
            cached_frames: HashMap::new(),
        }
    }

    /// Create new tiled PDB manager for reading
    pub fn new_for_read(base_path: &str) -> PdbResult<Self> {
        let base_path = PathBuf::from(base_path);
        let header_path = base_path.join("tiles.json");

        let json = std::fs::read_to_string(&header_path)
            .map_err(|e| PdbError::IoError(format!("Failed to read {}: {}", header_path.display(), e)))?;

        let header = serde_json::from_str(&json)
            .map_err(|e| PdbError::IoError(format!("JSON deserialization failed: {}", e)))?;

        println!("Tiled header loaded from: {}", header_path.display());

        Ok(Self {
            base_path,
            header,
            cached_frames: HashMap::new(),
        })
    }

    /// Get path to a tile's PNG file
    pub fn get_tile_path(&self, table_name: &str, coord: TileCoord) -> PathBuf {
        let filename = format!("{}.{}.{}.pdb.png", table_name, coord.tile_x, coord.tile_y);
        self.base_path.join(filename)
    }

    /// Open a tile frame for reading
    pub fn open_tile(&mut self, table_name: &str, coord: TileCoord) -> PdbResult<crate::pdb::PdbDecoder> {
        let path = self.get_tile_path(table_name, coord);
        // STUB: Load PNG and create decoder
        crate::pdb::PdbDecoder::load_png(&path)
    }

    /// Save the tiled header as JSON
    pub fn save_header(&self) -> PdbResult<()> {
        use std::fs::File;
        use std::io::Write;

        let header_path = self.base_path.join("tiles.json");

        let json = serde_json::to_string_pretty(&self.header)
            .map_err(|e| PdbError::IoError(format!("JSON serialization failed: {}", e)))?;

        let mut file =
            File::create(&header_path).map_err(|e| PdbError::IoError(format!("Failed to create {}: {}", header_path.display(), e)))?;

        file.write_all(json.as_bytes())
            .map_err(|e| PdbError::IoError(format!("Failed to write {}: {}", header_path.display(), e)))?;

        println!("Tiled header saved to: {}", header_path.display());
        Ok(())
    }

    /// Load the tiled header from JSON
    pub fn load_header(&mut self) -> PdbResult<()> {
        use std::fs;

        let header_path = self.base_path.join("tiles.json");

        let json = fs::read_to_string(&header_path)
            .map_err(|e| PdbError::IoError(format!("Failed to read {}: {}", header_path.display(), e)))?;

        self.header = serde_json::from_str(&json)
            .map_err(|e| PdbError::IoError(format!("JSON deserialization failed: {}", e)))?;

        println!("Tiled header loaded from: {}", header_path.display());
        Ok(())
    }
}

/// Tiled encoder — writes data across multiple tile frames
pub struct TiledPdbEncoder {
    /// Manager for tile I/O
    pub manager: TiledPdbManager,
    /// Current tile frame being written
    pub current_frame: Option<(TileCoord, crate::pdb::PdbEncoder)>,
}

impl TiledPdbEncoder {
    /// Create new tiled encoder
    pub fn new(base_path: &str, header: TiledPdbHeader) -> PdbResult<Self> {
        Ok(Self {
            manager: TiledPdbManager::new_for_write(base_path, header),
            current_frame: None,
        })
    }

    /// Encode a table across multiple tiles
    pub fn encode_table(&mut self, table_name: &str, data: &[u8]) -> PdbResult<()> {
        let tile_size = self.manager.header.tile_config.tile_size;

        // Split data into tiles
        let tiles = self
            .manager
            .header
            .tile_config
            .split_into_tiles(data, &self.manager.base_path, table_name);

        println!(
            "Encoding table '{}' across {} tiles",
            table_name,
            tiles.len()
        );

        for tile_metadata in &tiles {
            let byte_range_start = tile_metadata.byte_offset as usize;
            let byte_range_end = (tile_metadata.byte_offset + tile_metadata.byte_count) as usize;
            let tile_data = &data[byte_range_start..byte_range_end];

            // Create header for this single tile frame
            let mut tile_header = crate::pdb::PdbHeader::new();
            // For blob-table: 1 row = all bytes, so row_count = byte_count
            // NOTE: This must fit in u32! If tiles exceed 4GB, we need a different encoding strategy.
            let tile_row_count = tile_metadata.byte_count.min(u32::MAX as u64) as u32;
            let tile_row_length = 1; // Blob-table semantics

            // Add table metadata with tile's bbox
            tile_header.add_table(TableMetadata::new(
                table_name,
                tile_metadata.bbox,
                tile_row_count,
                tile_row_length,
            ))?;

            // Create encoder for this tile
            let tile_config = crate::pdb::PdbConfig::new(
                tile_size as usize,
                tile_size as usize,
            )?;
            let mut encoder = crate::pdb::PdbEncoder::new(tile_config, tile_header);
            encoder.encode_header()?;
            encoder.encode_table(0, tile_data)?;

            // Save tile PNG
            encoder.save_png(&tile_metadata.file_path)?;

            println!(
                "  Tile ({}, {}): {} bytes -> {}",
                tile_metadata.coord.tile_x,
                tile_metadata.coord.tile_y,
                tile_metadata.byte_count,
                tile_metadata.file_path.display()
            );

            // Track tile in header
            self.manager
                .header
                .add_tile(table_name, tile_metadata.clone());
        }

        Ok(())
    }

    /// Save the tiled header
    pub fn save_header(&self) -> PdbResult<()> {
        self.manager.save_header()
    }
}

/// Tiled decoder — reads data from multiple tile frames
pub struct TiledPdbDecoder {
    /// Manager for tile I/O
    pub manager: TiledPdbManager,
}

impl TiledPdbDecoder {
    /// Create new tiled decoder
    pub fn new(base_path: &str) -> PdbResult<Self> {
        Ok(Self {
            manager: TiledPdbManager::new_for_read(base_path)?,
        })
    }

    /// Decode a table from multiple tiles
    pub fn decode_table(&mut self, table_name: &str) -> PdbResult<Vec<u8>> {
        // Get all tiles for table_name from header
        let tiles = self
            .manager
            .header
            .get_tiles(table_name)
            .ok_or(PdbError::DecodingFailed)?;

        if tiles.is_empty() {
            return Ok(vec![]);
        }

        println!("Decoding table '{}' from {} tiles", table_name, tiles.len());

        let mut full_data = Vec::new();

        // Sort tiles by byte_offset to ensure correct ordering
        let mut sorted_tiles: Vec<_> = tiles.to_vec();
        sorted_tiles.sort_by_key(|t| t.byte_offset);

        for tile_metadata in &sorted_tiles {
            // Load this tile's PNG
            let mut tile_decoder = self.manager.open_tile(table_name, tile_metadata.coord)?;
            eprintln!("Tile ({}, {}): PNG loaded", tile_metadata.coord.tile_x, tile_metadata.coord.tile_y);
            tile_decoder.decode_header()?;
            eprintln!("Tile ({}, {}): Header decoded", tile_metadata.coord.tile_x, tile_metadata.coord.tile_y);

            // For blob-table tiles, decode the first table (blob-table semantics)
            // Tile encoding uses blob-table semantics: row_length=1, row_count=byte_count
            let tile_data = tile_decoder.decode_first_table()?;

            println!(
                "  Tile ({}, {}): {} bytes decoded",
                tile_metadata.coord.tile_x,
                tile_metadata.coord.tile_y,
                tile_data.len()
            );

            full_data.extend_from_slice(&tile_data);
        }

        // Verify total byte count matches expected
        let expected_bytes: u64 = sorted_tiles.iter().map(|t| t.byte_count).sum();
        if full_data.len() as u64 != expected_bytes {
            return Err(PdbError::DecodingFailed);
        }

        Ok(full_data)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tile_coord_indexing() {
        let coord = TileCoord { tile_x: 2, tile_y: 3 };
        let index = coord.to_index(8);
        assert_eq!(index, 26); // 3 * 8 + 2

        let restored = TileCoord::from_index(index, 8);
        assert_eq!(restored.tile_x, 2);
        assert_eq!(restored.tile_y, 3);
    }

    #[test]
    fn test_tile_grid_config() {
        let config = TileGridConfig::new(4096, 10000, 8000).unwrap();
        assert_eq!(config.tile_size, 4096);
        assert_eq!(config.tiles_per_row, 3); // ceil(10000/4096)
        assert_eq!(config.tiles_per_col, 2); // ceil(8000/4096)
        assert_eq!(config.total_tiles, 6);
    }

    #[test]
    fn test_tile_grid_pixel_to_tile() {
        let config = TileGridConfig::new(4096, 8192, 8192).unwrap();
        let coord = config.get_tile_for_pixel(5000, 3000).unwrap();
        assert_eq!(coord.tile_x, 1);
        assert_eq!(coord.tile_y, 0);
    }

    #[test]
    fn test_tiled_header_creation() {
        let tile_config = TileGridConfig::new(4096, 4096, 4096).unwrap();
        let header = TiledPdbHeader::new(tile_config);
        assert_eq!(header.table_count, 0);
        assert_eq!(header.magic, *b"TILD");
    }

    #[test]
    fn test_tiled_manager_path_generation() {
        let tile_config = TileGridConfig::new(4096, 4096, 4096).unwrap();
        let header = TiledPdbHeader::new(tile_config);
        let manager = TiledPdbManager::new_for_write("/tmp/test", header);
        let path = manager.get_tile_path("rootfs", TileCoord { tile_x: 0, tile_y: 1 });
        assert_eq!(path, PathBuf::from("/tmp/test/rootfs.0.1.pdb.png"));
    }

    #[test]
    fn test_tile_chunking() {
        // Create a config that expects 8x8 tiles of 4096x4096
        let config = TileGridConfig::new(4096, 4096 * 8, 4096 * 8).unwrap();
        
        // Let's create a simulated data length of exactly 2.5 tiles worth
        // 1 tile = 4096 * 4096 * 3 = 50,331,648 bytes
        // 2.5 tiles = 125,829,120 bytes
        let data_len = 125_829_120;
        let dummy_data = vec![0u8; data_len];
        
        let base_path = PathBuf::from("/tmp");
        let tiles = config.split_into_tiles(&dummy_data, &base_path, "test");
        
        // Should create exactly 3 tiles
        assert_eq!(tiles.len(), 3);
        
        // Tile 0: Full capacity
        assert_eq!(tiles[0].byte_offset, 0);
        assert_eq!(tiles[0].byte_count, 48758784); // 4096 * 3968 * 3
        assert_eq!(tiles[0].coord, TileCoord { tile_x: 0, tile_y: 0 });
        assert_eq!(tiles[0].file_path, PathBuf::from("/tmp/test.0.0.pdb.png"));
        assert_eq!(tiles[0].bbox.y_max, 4095); // HEADER_SIZE (128) + full height (3968) - 1
        
        // Tile 1: Full capacity
        assert_eq!(tiles[1].byte_offset, 48758784);
        assert_eq!(tiles[1].byte_count, 48758784);
        assert_eq!(tiles[1].coord, TileCoord { tile_x: 1, tile_y: 0 });
        assert_eq!(tiles[1].file_path, PathBuf::from("/tmp/test.1.0.pdb.png"));
        assert_eq!(tiles[1].bbox.y_max, 4095);
        
        // Tile 2: Partial
        assert_eq!(tiles[2].byte_offset, 97517568);
        assert_eq!(tiles[2].byte_count, 28311552); // Remaining bytes
        assert_eq!(tiles[2].coord, TileCoord { tile_x: 2, tile_y: 0 });
        assert_eq!(tiles[2].file_path, PathBuf::from("/tmp/test.2.0.pdb.png"));
        assert_eq!(tiles[2].bbox.y_max, 2431); // HEADER_SIZE (128) + 2304 - 1

        // Sum of parts equals total
        let total_bytes: u64 = tiles.iter().map(|t| t.byte_count).sum();
        assert_eq!(total_bytes, data_len as u64);
    }
}