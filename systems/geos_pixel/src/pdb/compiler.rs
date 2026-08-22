/// SQLite-to-PDB Compiler
///
/// Reads SQLite databases and compiles tables to spatial PDB format.

use rusqlite::Connection;
use crate::pdb::{
    BoundingBox, PdbConfig, PdbError, PdbHeader, PdbResult, PdbEncoder, TableMetadata, HEADER_SIZE,
};

/// Structure holding table introspection metadata
#[derive(Debug, Clone)]
struct TableInfo {
    name: String,
    row_count: u32,
    row_len: u32,
}

/// SQLite-to-PDB compiler
pub struct SqliteToPdb {
    sqlite_path: std::path::PathBuf,
    pdb_path: std::path::PathBuf,
    config: PdbConfig,
}

impl SqliteToPdb {
    /// Create new compiler
    pub fn new<P: AsRef<std::path::Path>>(
        sqlite_path: P,
        pdb_path: P,
        config: PdbConfig,
    ) -> Self {
        Self {
            sqlite_path: sqlite_path.as_ref().to_path_buf(),
            pdb_path: pdb_path.as_ref().to_path_buf(),
            config,
        }
    }

    /// Compile SQLite database to PDB frame
    pub fn compile(&self) -> PdbResult<()> {
        // Step 1: Open SQLite database connection
        let conn = Connection::open(&self.sqlite_path)
            .map_err(|e| SqliteCompilerError::SqliteOpenFailed(e.to_string()))?;

        // Query table names (excluding internal SQLite system tables)
        let mut table_stmt = conn
            .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            .map_err(|e| SqliteCompilerError::SchemaReadFailed(e.to_string()))?;

        let table_names: Vec<String> = table_stmt
            .query_map([], |row| row.get(0))
            .map_err(|e| SqliteCompilerError::SchemaReadFailed(e.to_string()))?
            .collect::<Result<Vec<String>, _>>()
            .map_err(|e| SqliteCompilerError::SchemaReadFailed(e.to_string()))?;

        let mut tables_info = Vec::new();

        for table_name in &table_names {
            // Query schema via PRAGMA table_info(table_name)
            let pragma_sql = format!("PRAGMA table_info(\"{}\")", table_name.replace('"', "\"\""));
            let mut pragma_stmt = conn
                .prepare(&pragma_sql)
                .map_err(|e| SqliteCompilerError::SchemaReadFailed(e.to_string()))?;

            let col_types: Vec<String> = pragma_stmt
                .query_map([], |row| row.get::<_, String>(2))
                .map_err(|e| SqliteCompilerError::SchemaReadFailed(e.to_string()))?
                .collect::<Result<Vec<String>, _>>()
                .map_err(|e| SqliteCompilerError::SchemaReadFailed(e.to_string()))?;

            // Calculate row byte length from schema types
            // INTEGER / REAL -> 8 bytes
            // TEXT / BLOB -> 255 bytes
            let mut row_len: u32 = 0;
            for col_type in &col_types {
                let upper = col_type.to_uppercase();
                let col_bytes = if upper.contains("INT")
                    || upper.contains("REAL")
                    || upper.contains("FLOA")
                    || upper.contains("DOUB")
                {
                    8
                } else {
                    255
                };
                row_len += col_bytes;
            }

            if row_len == 0 {
                row_len = 1;
            }

            // Query row count
            let count_sql = format!("SELECT COUNT(*) FROM \"{}\"", table_name.replace('"', "\"\""));
            let mut count_stmt = conn
                .prepare(&count_sql)
                .map_err(|e| SqliteCompilerError::RowReadFailed(e.to_string()))?;
            let row_count: u32 = count_stmt
                .query_row([], |row| row.get::<_, u32>(0))
                .map_err(|e| SqliteCompilerError::RowReadFailed(e.to_string()))?;

            tables_info.push(TableInfo {
                name: table_name.clone(),
                row_count,
                row_len,
            });
        }

        // Step 2: Bounding Box Allocation
        let mut header = PdbHeader::new();
        let mut current_y = HEADER_SIZE as u32;

        for table in &tables_info {
            let total_bytes = (table.row_count as u64) * (table.row_len as u64);
            let pixels_needed = (total_bytes as f64 / 3.0).ceil() as usize;

            let height_needed = if pixels_needed == 0 {
                1
            } else {
                (pixels_needed as f64 / self.config.width as f64).ceil() as u32
            };

            let y_min = current_y;
            let y_max = y_min + height_needed - 1;

            if y_max >= self.config.height as u32 {
                return Err(SqliteCompilerError::BoundingBoxCalculationFailed.into());
            }

            let bbox = BoundingBox {
                x_min: 0,
                y_min,
                x_max: (self.config.width - 1) as u32,
                y_max,
            };

            header.add_table(TableMetadata::new(
                &table.name,
                bbox,
                table.row_count,
                table.row_len,
            ))?;

            current_y = y_max + 1;
        }

        // Create encoder
        let mut encoder = PdbEncoder::new(self.config.clone(), header.clone());

        // Encode header
        encoder.encode_header()?;

        let mut vcc = crate::pdb::VccIntegrity::new();

        // Encode tables with actual row data
        for (idx, table) in tables_info.iter().enumerate() {
            let select_sql = format!("SELECT * FROM \"{}\"", table.name.replace('"', "\"\""));
            let mut select_stmt = conn.prepare(&select_sql).unwrap();
            
            let mut row_data = Vec::new();
            let mut rows = select_stmt.query([]).unwrap();
            while let Some(row) = rows.next().unwrap() {
                // We know row_len. We just serialize the columns into a fixed size buffer.
                // For a real implementation we'd inspect schema correctly, but here's a naive dump
                // based on column count and expected size.
                let mut row_bytes = vec![0u8; table.row_len as usize];
                let mut offset = 0;
                
                let col_count = row.as_ref().column_count();
                for i in 0..col_count {
                    let val = row.get_ref(i).unwrap();
                    use rusqlite::types::ValueRef;
                    match val {
                        ValueRef::Integer(v) => {
                            let b = v.to_le_bytes();
                            let copy_len = b.len().min(8).min(table.row_len as usize - offset);
                            row_bytes[offset..offset+copy_len].copy_from_slice(&b[..copy_len]);
                            offset += 8;
                        }
                        ValueRef::Real(v) => {
                            let b = v.to_le_bytes();
                            let copy_len = b.len().min(8).min(table.row_len as usize - offset);
                            row_bytes[offset..offset+copy_len].copy_from_slice(&b[..copy_len]);
                            offset += 8;
                        }
                        ValueRef::Text(t) | ValueRef::Blob(t) => {
                            let copy_len = t.len().min(255).min(table.row_len as usize - offset);
                            row_bytes[offset..offset+copy_len].copy_from_slice(&t[..copy_len]);
                            offset += 255;
                        }
                        ValueRef::Null => {
                            offset += 8; // Naive assumption
                        }
                    }
                }
                row_data.extend_from_slice(&row_bytes);
            }

            encoder.encode_table(idx, &row_data)?;

            // Compute VCC hash
            let bbox = header.tables[idx].bbox;
            let hash = vcc.compute_table_hash(encoder.canvas(), &table.name, &bbox)?;
            let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();
            println!("VCC Hash for table '{}': {}", table.name, hex_hash);
        }

        // Save PDB frame
        encoder.save_png(&self.pdb_path)?;

        Ok(())
    }
}

/// Compiler-specific errors
#[derive(Debug)]
pub enum SqliteCompilerError {
    SqliteOpenFailed(String),
    TableNotFound(String),
    SchemaReadFailed(String),
    RowReadFailed(String),
    BoundingBoxCalculationFailed,
}

impl From<SqliteCompilerError> for PdbError {
    fn from(err: SqliteCompilerError) -> Self {
        match err {
            SqliteCompilerError::SqliteOpenFailed(msg) => PdbError::IoError(msg),
            SqliteCompilerError::TableNotFound(msg) => PdbError::IoError(msg),
            SqliteCompilerError::SchemaReadFailed(msg) => PdbError::IoError(msg),
            SqliteCompilerError::RowReadFailed(msg) => PdbError::IoError(msg),
            SqliteCompilerError::BoundingBoxCalculationFailed => PdbError::EncodingFailed,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compiler_creation() {
        let config = PdbConfig::new(512, 512).unwrap();
        let compiler = SqliteToPdb::new("test.db", "test.pdb.png", config);
        assert_eq!(compiler.sqlite_path, std::path::PathBuf::from("test.db"));
    }

    #[test]
    fn test_compile_sqlite_database() {
        let temp_dir = std::env::temp_dir();
        let db_path = temp_dir.join("test_pdb_compiler.db");
        let png_path = temp_dir.join("test_pdb_compiler.pdb.png");

        // Create SQLite database
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "CREATE TABLE users (id INTEGER, name TEXT, status TEXT);",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO users VALUES (1, 'alice', 'active'), (2, 'bob', 'inactive');",
            [],
        )
        .unwrap();

        conn.execute(
            "CREATE TABLE sessions (id INTEGER, user_id INTEGER, token TEXT);",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO sessions VALUES (1, 1, 'abc123'), (2, 2, 'def456');",
            [],
        )
        .unwrap();

        let config = PdbConfig::new(512, 512).unwrap();
        let compiler = SqliteToPdb::new(&db_path, &png_path, config);
        let result = compiler.compile();
        assert!(result.is_ok(), "Compilation failed: {:?}", result);
        assert!(png_path.exists());

        let _ = std::fs::remove_file(db_path);
        let _ = std::fs::remove_file(png_path);
    }

    #[test]
    fn test_compile_round_trip_content_matches_source() {
        // Regression guard: earlier "verification" only re-hashed the pixels it had just
        // written, which would pass even if encoding scrambled the data. This test decodes
        // the PDB frame and checks the actual field bytes against the original SQLite rows.
        let temp_dir = std::env::temp_dir();
        let db_path = temp_dir.join("test_pdb_roundtrip_content.db");
        let png_path = temp_dir.join("test_pdb_roundtrip_content.pdb.png");
        let _ = std::fs::remove_file(&db_path);
        let _ = std::fs::remove_file(&png_path);

        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "CREATE TABLE users (id INTEGER, name TEXT, status TEXT);",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO users VALUES (1, 'alice', 'active'), (2, 'bob', 'inactive');",
            [],
        )
        .unwrap();
        conn.execute(
            "CREATE TABLE sessions (id INTEGER, user_id INTEGER, token TEXT);",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO sessions VALUES (1, 1, 'tok_abc'), (2, 2, 'tok_def');",
            [],
        )
        .unwrap();

        let config = PdbConfig::new(512, 512).unwrap();
        let compiler = SqliteToPdb::new(&db_path, &png_path, config);
        compiler.compile().expect("compile failed");

        let mut decoder = crate::pdb::PdbDecoder::load_png(&png_path).expect("load failed");
        decoder.decode_header().expect("header decode failed");

        let users_data = decoder.decode_table("users").expect("decode users failed");
        let sessions_data = decoder
            .decode_table("sessions")
            .expect("decode sessions failed");

        let users_text = String::from_utf8_lossy(&users_data);
        for needle in ["alice", "active", "bob", "inactive"] {
            assert!(
                users_text.contains(needle),
                "decoded users table missing expected value {:?}",
                needle
            );
        }

        let sessions_text = String::from_utf8_lossy(&sessions_data);
        for needle in ["tok_abc", "tok_def"] {
            assert!(
                sessions_text.contains(needle),
                "decoded sessions table missing expected value {:?}",
                needle
            );
        }

        let _ = std::fs::remove_file(db_path);
        let _ = std::fs::remove_file(png_path);
    }

    #[test]
    fn test_sqlite_error_handling() {
        let config = PdbConfig::new(512, 512).unwrap();
        let compiler_bad = SqliteToPdb::new(
            "/non_existent_dir_12345/non_existent.db",
            "out.pdb.png",
            config,
        );
        let result_bad = compiler_bad.compile();
        assert!(result_bad.is_err());
    }
}