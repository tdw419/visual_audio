// etc_to_pdb.rs - Tier 1 Semantic Table Extractor for PDB
//
// Extracts /etc/passwd from Ubuntu disk image and compiles it into
// spatial PDB format using proper semantic table structure (not blob-table).
// This validates that PDB can handle human-readable tabular data directly.
//
// Usage:
//   cargo run --example etc_to_pdb -- <disk_image> <output.pdb.png>
//
// Example:
//   cargo run --example etc_to_pdb -- ubuntu-24.04-server-cloudimg-amd64.raw /tmp/passwd.pdb.png

use geos_pixel_v5::pdb::{
    BoundingBox, PdbConfig, PdbEncoder, PdbError, PdbHeader, PdbResult, TableMetadata, HEADER_SIZE,
};
use std::fs;
use std::path::PathBuf;

/// Represents a single /etc/shadow entry with typed fields
#[derive(Debug, Clone)]
struct ShadowEntry {
    username: String,      // Field 0
    password: String,      // Field 1 (hashed)
    last_changed: i32,     // Field 2 (days since epoch)
    minimum: i32,          // Field 3
    maximum: i32,          // Field 4
    warn: i32,             // Field 5
    inactive: i32,         // Field 6
    expire: i32,           // Field 7
    reserved: u32,         // Field 8
}

impl ShadowEntry {
    /// Parse a line from /etc/shadow
    /// Format: username:password:last_changed:minimum:maximum:warn:inactive:expire:reserved
    fn from_line(line: &str) -> PdbResult<Self> {
        let fields: Vec<&str> = line.split(':').collect();
        
        if fields.len() != 9 {
            return Err(PdbError::InvalidRowData);
        }

        let parse_i32 = |s: &str| -> i32 {
            if s.is_empty() { -1 } else { s.parse().unwrap_or(-1) }
        };

        Ok(Self {
            username: fields[0].to_string(),
            password: fields[1].to_string(),
            last_changed: parse_i32(fields[2]),
            minimum: parse_i32(fields[3]),
            maximum: parse_i32(fields[4]),
            warn: parse_i32(fields[5]),
            inactive: parse_i32(fields[6]),
            expire: parse_i32(fields[7]),
            reserved: if fields[8].is_empty() { 0 } else { fields[8].parse().unwrap_or(0) },
        })
    }

    /// Encode this entry into a fixed-width row structure
    /// Field layout (offsets in bytes):
    ///   0-31:   username (32 bytes, null-padded)
    ///   32-159: password hash (128 bytes, null-padded)
    ///   160-163: last_changed (i32 LE)
    ///   164-167: minimum (i32 LE)
    ///   168-171: maximum (i32 LE)
    ///   172-175: warn (i32 LE)
    ///   176-179: inactive (i32 LE)
    ///   180-183: expire (i32 LE)
    ///   184-187: reserved (u32 LE)
    /// Total row length: 188 bytes
    fn encode(&self) -> Vec<u8> {
        let mut row = vec![0u8; 188];

        fn write_str(row: &mut [u8], offset: usize, s: &str, max_len: usize) {
            let bytes = s.as_bytes();
            let copy_len = bytes.len().min(max_len - 1);
            row[offset..offset + copy_len].copy_from_slice(&bytes[..copy_len]);
        }

        write_str(&mut row, 0, &self.username, 32);
        write_str(&mut row, 32, &self.password, 128);

        row[160..164].copy_from_slice(&self.last_changed.to_le_bytes());
        row[164..168].copy_from_slice(&self.minimum.to_le_bytes());
        row[168..172].copy_from_slice(&self.maximum.to_le_bytes());
        row[172..176].copy_from_slice(&self.warn.to_le_bytes());
        row[176..180].copy_from_slice(&self.inactive.to_le_bytes());
        row[180..184].copy_from_slice(&self.expire.to_le_bytes());
        row[184..188].copy_from_slice(&self.reserved.to_le_bytes());

        row
    }
}

struct ShadowToPdbCompiler {
    disk_image: PathBuf,
    output_path: PathBuf,
    config: PdbConfig,
}

impl ShadowToPdbCompiler {
    fn new(disk_image: &str, output_path: &str, config: PdbConfig) -> Self {
        Self {
            disk_image: PathBuf::from(disk_image),
            output_path: PathBuf::from(output_path),
            config,
        }
    }

    /// Extract /etc/shadow content using guestfish
    fn extract_shadow(&self) -> PdbResult<String> {
        let output = std::process::Command::new("guestfish")
            .args([
                "--ro",
                "-a",
                self.disk_image.to_str().unwrap(),
                "-m",
                "/dev/sda1",
                "cat",
                "/etc/shadow",
            ])
            .output()
            .map_err(|e| PdbError::IoError(format!("Failed to run guestfish: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(PdbError::IoError(format!(
                "guestfish failed: {}",
                stderr
            )));
        }

        String::from_utf8(output.stdout)
            .map_err(|_| PdbError::IoError("Invalid UTF-8 in /etc/shadow".to_string()))
    }

    /// Parse /etc/shadow content into structured entries
    fn parse_shadow(&self, content: &str) -> PdbResult<Vec<ShadowEntry>> {
        let mut entries = Vec::new();
        
        for (line_num, line) in content.lines().enumerate() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }

            match ShadowEntry::from_line(line) {
                Ok(entry) => entries.push(entry),
                Err(e) => {
                    eprintln!("Warning: Failed to parse line {}: {}", line_num + 1, line);
                    eprintln!("  Error: {:?}", e);
                }
            }
        }

        Ok(entries)
    }

    /// Compile parsed entries into PDB format
    fn compile(&self) -> PdbResult<()> {
        println!("Extracting /etc/shadow from: {}", self.disk_image.display());
        let shadow_content = self.extract_shadow()?;
        println!("Extracted {} bytes", shadow_content.len());

        println!("Parsing /etc/shadow entries...");
        let entries = self.parse_shadow(&shadow_content)?;
        println!("Parsed {} entries", entries.len());

        println!("\nSample entries:");
        for (i, entry) in entries.iter().take(3).enumerate() {
            let pwd_display = if entry.password.len() > 10 {
                format!("{}...", &entry.password[..10])
            } else {
                entry.password.clone()
            };
            println!("  [{}] {}: pwd={} changed={}", i + 1, entry.username, pwd_display, entry.last_changed);
        }
        if entries.len() > 3 {
            println!("  ... and {} more", entries.len() - 3);
        }

        let mut table_data = Vec::new();
        for entry in &entries {
            table_data.extend_from_slice(&entry.encode());
        }

        println!("\nEncoded {} rows × {} bytes = {} total bytes",
            entries.len(),
            188,
            table_data.len()
        );

        let mut header = PdbHeader::new();
        let row_count = entries.len() as u32;
        let row_length = 188;
        let byte_count = table_data.len();

        let triplets_needed = (byte_count + 2) / 3;
        let height_needed = if triplets_needed == 0 {
            1
        } else {
            (triplets_needed as f64 / self.config.width as f64).ceil() as u32
        };

        let bbox = BoundingBox {
            x_min: 0,
            y_min: HEADER_SIZE as u32,
            x_max: (self.config.width - 1) as u32,
            y_max: HEADER_SIZE as u32 + height_needed - 1,
        };

        header.add_table(TableMetadata::new("shadow", bbox, row_count, row_length))?;

        let mut encoder = PdbEncoder::new(self.config.clone(), header.clone());
        encoder.encode_header()?;
        encoder.encode_table(0, &table_data)?;

        let mut vcc = geos_pixel_v5::pdb::VccIntegrity::new();
        let hash = vcc.compute_table_hash(encoder.canvas(), "shadow", &bbox)?;
        let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();

        println!("\nTable metadata:");
        println!("  Name: shadow");
        println!("  Row count: {}", row_count);
        println!("  Row length: {} bytes", row_length);
        println!("  Total bytes: {}", byte_count);
        println!("  Bounding box: ({}, {}) to ({}, {})",
            bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max);
        println!("  VCC Hash: {}", hex_hash);

        encoder.save_png(&self.output_path)?;
        println!("\nWrote: {}", self.output_path.display());

        Ok(())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 3 {
        eprintln!("Usage: shadow_to_pdb <disk_image> <output.pdb.png>");
        eprintln!("");
        eprintln!("Example:");
        eprintln!("  cargo run --example shadow_to_pdb -- ubuntu-24.04-server-cloudimg-amd64.raw /tmp/shadow.pdb.png");
        eprintln!("");
        eprintln!("Arguments:");
        eprintln!("  disk_image    Path to Ubuntu disk image (.raw)");
        eprintln!("  output.pdb.png Output PDB PNG file");
        std::process::exit(1);
    }

    let disk_image = &args[1];
    let output_path = &args[2];
    let frame_size = 2048;

    let config = match PdbConfig::new(frame_size, frame_size) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("Tier 1 Semantic Table Extractor for /etc/shadow");
    println!("===============================================");
    println!("Source: {}", disk_image);
    println!("Output: {}", output_path);
    println!("Frame size: {}x{}", frame_size, frame_size);
    println!("");

    let compiler = ShadowToPdbCompiler::new(disk_image, output_path, config);

    match compiler.compile() {
        Ok(()) => {
            println!("\nSUCCESS: /etc/shadow compiled as semantic PDB table");
        }
        Err(e) => {
            eprintln!("\nFAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}