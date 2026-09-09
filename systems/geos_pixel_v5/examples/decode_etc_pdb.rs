// decode_etc_pdb.rs - Decode semantic PDB tables (e.g., /etc/passwd)
//
// Decodes PDB tables created by etc_to_pdb.rs and prints structured data.
// Validates that semantic table encoding is reversible.
//
// Usage:
//   cargo run --example decode_etc_pdb -- <input.pdb.png>
//
// Example:
//   cargo run --example decode_etc_pdb -- /tmp/passwd.pdb.png

use geos_pixel_v5::pdb::{PdbDecoder, PdbError, PdbResult};
use std::path::PathBuf;

/// Represents a single /etc/passwd entry with typed fields
#[derive(Debug, Clone)]
struct PasswdEntry {
    username: String,  // Field 0
    password: String,  // Field 1 (x or hashed)
    uid: u32,          // Field 2
    gid: u32,          // Field 3
    gecos: String,     // Field 4 (real name/comment)
    home: String,      // Field 5
    shell: String,     // Field 6
}

impl PasswdEntry {
    /// Decode a fixed-width row structure back into a PasswdEntry
    /// Field layout (offsets in bytes):
    ///   0-31:   username (32 bytes, null-padded)
    ///   32-63:  password (32 bytes, null-padded)
    ///   64-67:  uid (u32 LE)
    ///   68-71:  gid (u32 LE)
    ///   72-135: gecos (64 bytes, null-padded)
    ///   136-183: home (48 bytes, null-padded)
    ///   184-215: shell (32 bytes, null-padded)
    /// Total row length: 216 bytes
    fn decode(row: &[u8]) -> PdbResult<Self> {
        if row.len() < 216 {
            return Err(PdbError::InvalidRowData);
        }

        // Helper to read null-padded string
        fn read_str(row: &[u8], offset: usize, max_len: usize) -> String {
            let end = (offset..offset + max_len)
                .position(|i| row[i] == 0)
                .map(|p| offset + p)
                .unwrap_or(offset + max_len);
            String::from_utf8_lossy(&row[offset..end]).to_string()
        }

        let username = read_str(row, 0, 32);
        let password = read_str(row, 32, 32);
        let uid = u32::from_le_bytes([row[64], row[65], row[66], row[67]]);
        let gid = u32::from_le_bytes([row[68], row[69], row[70], row[71]]);
        let gecos = read_str(row, 72, 64);
        let home = read_str(row, 136, 48);
        let shell = read_str(row, 184, 32);

        Ok(Self {
            username,
            password,
            uid,
            gid,
            gecos,
            home,
            shell,
        })
    }

    /// Convert back to /etc/passwd line format
    fn to_line(&self) -> String {
        format!(
            "{}:{}:{}:{}:{}:{}:{}",
            self.username, self.password, self.uid, self.gid, self.gecos, self.home, self.shell
        )
    }
}

struct EtcPdbDecoder {
    input_path: PathBuf,
}

impl EtcPdbDecoder {
    fn new(input_path: &str) -> Self {
        Self {
            input_path: PathBuf::from(input_path),
        }
    }

    /// Decode the PDB and print table contents
    fn decode(&self) -> PdbResult<()> {
        println!("Loading PDB: {}", self.input_path.display());

        let mut decoder = PdbDecoder::load_png(&self.input_path)?;
        let header = decoder.decode_header()?;

        println!("\nPDB Header:");
        println!("  Version: 0x{:02x}", header.version);
        println!("  Tables: {}", header.table_count);

        // Clone the tables we need to avoid borrow issues
        let tables = header.tables.clone();

        for (idx, table) in tables.iter().enumerate() {
            let table_name = String::from_utf8_lossy(&table.name)
                .trim_end_matches('\0')
                .to_string();

            println!("\nTable {}: {}", idx, table_name);
            println!("  Rows: {}", table.row_count);
            println!("  Row length: {} bytes", table.row_length);
            println!(
                "  Bounding box: ({}, {}) to ({}, {})",
                table.bbox.x_min, table.bbox.y_min, table.bbox.x_max, table.bbox.y_max
            );

            // Decode table data
            let table_data = decoder.decode_table(&table_name)?;

            // If this is the passwd table, decode structured entries
            if table_name == "passwd" && table.row_length == 216 {
                self.decode_passwd_table(&table_data, table.row_count as usize, &table_name)?;
            } else {
                // Generic blob output
                println!("\n  Raw data (first 256 bytes):");
                let preview_len = table_data.len().min(256);
                for (i, chunk) in table_data[..preview_len].chunks(16).enumerate() {
                    let hex: String = chunk.iter().map(|b| format!("{:02x} ", b)).collect();
                    let ascii: String = chunk
                        .iter()
                        .map(|b| if b.is_ascii_graphic() || *b == b' ' { *b as char } else { '.' })
                        .collect();
                    println!("    {:04x}: {} | {}", i * 16, hex, ascii);
                }
                if table_data.len() > 256 {
                    println!("    ... ({} more bytes)", table_data.len() - 256);
                }
            }
        }

        Ok(())
    }

    fn decode_passwd_table(&self, data: &[u8], expected_rows: usize, table_name: &str) -> PdbResult<()> {
        let row_length = 216;
        let actual_rows = data.len() / row_length;

        println!("\n  Decoding structured entries:");
        println!("    Expected rows: {}", expected_rows);
        println!("    Actual rows: {}", actual_rows);

        if actual_rows != expected_rows {
            eprintln!("    WARNING: Row count mismatch!");
        }

        println!("\n  Entries:");
        for i in 0..actual_rows {
            let offset = i * row_length;
            let row = &data[offset..offset + row_length];

            match PasswdEntry::decode(row) {
                Ok(entry) => {
                    println!("    [{}] {}: ({}) {}", i + 1, entry.username, entry.uid, entry.gecos);

                    // Show sample entries in full
                    if i < 3 || i == actual_rows - 1 {
                        println!("       -> {}", entry.to_line());
                    }
                }
                Err(e) => {
                    eprintln!("    [{}] FAILED to decode: {:?}", i + 1, e);
                }
            }
        }

        Ok(())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 2 {
        eprintln!("Usage: decode_etc_pdb <input.pdb.png>");
        eprintln!("");
        eprintln!("Example:");
        eprintln!("  cargo run --example decode_etc_pdb -- /tmp/passwd.pdb.png");
        std::process::exit(1);
    }

    let input_path = &args[1];

    println!("Semantic PDB Table Decoder");
    println!("===========================");
    println!("Input: {}", input_path);
    println!("");

    let decoder = EtcPdbDecoder::new(input_path);

    match decoder.decode() {
        Ok(()) => {
            println!("\nSUCCESS: PDB decoded successfully");
        }
        Err(e) => {
            eprintln!("\nFAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}