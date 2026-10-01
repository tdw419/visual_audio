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
    /// Parse a line from /etc/passwd
    /// Format: username:password:uid:gid:gecos:home:shell
    fn from_line(line: &str) -> PdbResult<Self> {
        let fields: Vec<&str> = line.split(':').collect();
        
        if fields.len() != 7 {
            return Err(PdbError::InvalidRowData);
        }

        let username = fields[0].to_string();
        let password = fields[1].to_string();
        let uid = fields[2]
            .parse::<u32>()
            .map_err(|_| PdbError::InvalidRowData)?;
        let gid = fields[3]
            .parse::<u32>()
            .map_err(|_| PdbError::InvalidRowData)?;
        let gecos = fields[4].to_string();
        let home = fields[5].to_string();
        let shell = fields[6].trim().to_string();

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

    /// Encode this entry into a fixed-width row structure
    /// Field layout (offsets in bytes):
    ///   0-31:   username (32 bytes, null-padded)
    ///   32-63:  password (32 bytes, null-padded)
    ///   64-67:  uid (u32 LE)
    ///   68-71:  gid (u32 LE)
    ///   72-135: gecos (64 bytes, null-padded)
    ///   136-183: home (48 bytes, null-padded)
    ///   184-215: shell (32 bytes, null-padded)
    /// Total row length: 216 bytes
    fn encode(&self) -> Vec<u8> {
        let mut row = vec![0u8; 216];

        // Helper to write null-padded string
        fn write_str(row: &mut [u8], offset: usize, s: &str, max_len: usize) {
            let bytes = s.as_bytes();
            let copy_len = bytes.len().min(max_len - 1); // Leave room for null terminator
            row[offset..offset + copy_len].copy_from_slice(&bytes[..copy_len]);
            // Rest is already zero-initialized (null padding)
        }

        write_str(&mut row, 0, &self.username, 32);
        write_str(&mut row, 32, &self.password, 32);

        // uid (u32 LE)
        row[64..68].copy_from_slice(&self.uid.to_le_bytes());
        // gid (u32 LE)
        row[68..72].copy_from_slice(&self.gid.to_le_bytes());

        write_str(&mut row, 72, &self.gecos, 64);
        write_str(&mut row, 136, &self.home, 48);
        write_str(&mut row, 184, &self.shell, 32);

        row
    }
}

struct EtcToPdbCompiler {
    disk_image: PathBuf,
    output_path: PathBuf,
    config: PdbConfig,
}

impl EtcToPdbCompiler {
    fn new(disk_image: &str, output_path: &str, config: PdbConfig) -> Self {
        Self {
            disk_image: PathBuf::from(disk_image),
            output_path: PathBuf::from(output_path),
            config,
        }
    }

    /// Extract /etc/passwd content using guestfish
    fn extract_passwd(&self) -> PdbResult<String> {
        // Use guestfish to read /etc/passwd read-only from the disk image
        let output = std::process::Command::new("guestfish")
            .args([
                "--ro",
                "-a",
                self.disk_image.to_str().unwrap(),
                "-m",
                "/dev/sda1",
                "cat",
                "/etc/passwd",
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
            .map_err(|_| PdbError::IoError("Invalid UTF-8 in /etc/passwd".to_string()))
    }

    /// Parse /etc/passwd content into structured entries
    fn parse_passwd(&self, content: &str) -> PdbResult<Vec<PasswdEntry>> {
        let mut entries = Vec::new();
        
        for (line_num, line) in content.lines().enumerate() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }

            match PasswdEntry::from_line(line) {
                Ok(entry) => entries.push(entry),
                Err(e) => {
                    eprintln!("Warning: Failed to parse line {}: {}", line_num + 1, line);
                    eprintln!("  Error: {:?}", e);
                    // Continue parsing other lines
                }
            }
        }

        Ok(entries)
    }

    /// Compile parsed entries into PDB format
    fn compile(&self) -> PdbResult<()> {
        println!("Extracting /etc/passwd from: {}", self.disk_image.display());
        let passwd_content = self.extract_passwd()?;
        println!("Extracted {} bytes", passwd_content.len());

        println!("Parsing /etc/passwd entries...");
        let entries = self.parse_passwd(&passwd_content)?;
        println!("Parsed {} entries", entries.len());

        // Print sample entries for verification
        println!("\nSample entries:");
        for (i, entry) in entries.iter().take(3).enumerate() {
            println!("  [{}] {}: ({}) {}", i + 1, entry.username, entry.uid, entry.gecos);
        }
        if entries.len() > 3 {
            println!("  ... and {} more", entries.len() - 3);
        }

        // Encode all entries as fixed-width rows
        let mut table_data = Vec::new();
        for entry in &entries {
            table_data.extend_from_slice(&entry.encode());
        }

        println!("\nEncoded {} rows × {} bytes = {} total bytes",
            entries.len(),
            216,
            table_data.len()
        );

        // Create PDB header with proper semantic table structure
        let mut header = PdbHeader::new();
        let row_count = entries.len() as u32;
        let row_length = 216; // Fixed row length from PasswdEntry::encode()
        let byte_count = table_data.len();

        // Calculate bounding box height needed
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

        header.add_table(TableMetadata::new("passwd", bbox, row_count, row_length))?;

        // Create encoder and encode header
        let mut encoder = PdbEncoder::new(self.config.clone(), header.clone());
        encoder.encode_header()?;

        // Encode table
        encoder.encode_table(0, &table_data)?;

        // Compute and print VCC hash
        let mut vcc = geos_pixel_v5::pdb::VccIntegrity::new();
        let hash = vcc.compute_table_hash(encoder.canvas(), "passwd", &bbox)?;
        let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();

        println!("\nTable metadata:");
        println!("  Name: passwd");
        println!("  Row count: {}", row_count);
        println!("  Row length: {} bytes", row_length);
        println!("  Total bytes: {}", byte_count);
        println!("  Bounding box: ({}, {}) to ({}, {})",
            bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max);
        println!("  VCC Hash: {}", hex_hash);

        // Save PDB frame
        encoder.save_png(&self.output_path)?;
        println!("\nWrote: {}", self.output_path.display());

        Ok(())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 3 {
        eprintln!("Usage: etc_to_pdb <disk_image> <output.pdb.png>");
        eprintln!("");
        eprintln!("Example:");
        eprintln!("  cargo run --example etc_to_pdb -- ubuntu-24.04-server-cloudimg-amd64.raw /tmp/passwd.pdb.png");
        eprintln!("");
        eprintln!("Arguments:");
        eprintln!("  disk_image    Path to Ubuntu disk image (.raw)");
        eprintln!("  output.pdb.png Output PDB PNG file");
        std::process::exit(1);
    }

    let disk_image = &args[1];
    let output_path = &args[2];
    let frame_size = 2048; // More than enough for 33 rows × 216 bytes

    let config = match PdbConfig::new(frame_size, frame_size) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("Tier 1 Semantic Table Extractor for PDB");
    println!("=========================================");
    println!("Source: {}", disk_image);
    println!("Output: {}", output_path);
    println!("Frame size: {}x{}", frame_size, frame_size);
    println!("");

    let compiler = EtcToPdbCompiler::new(disk_image, output_path, config);

    match compiler.compile() {
        Ok(()) => {
            println!("\nSUCCESS: /etc/passwd compiled as semantic PDB table");
        }
        Err(e) => {
            eprintln!("\nFAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}