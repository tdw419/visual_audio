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

/// Represents a single /var/lib/dpkg/status entry
#[derive(Debug, Clone, Default)]
struct DpkgEntry {
    package: String,       // max 64
    status: String,        // max 32
    version: String,       // max 64
    architecture: String,  // max 16
    depends: String,       // max 256
    description: String,   // max 256
    maintainer: String,    // max 64
    installed_size: u32,   // 4 bytes
}

impl DpkgEntry {
    /// Parse a block of text separated by blank lines
    fn from_block(block: &str) -> PdbResult<Self> {
        let mut entry = DpkgEntry::default();

        for line in block.lines() {
            if let Some((key, value)) = line.split_once(':') {
                let value = value.trim();
                match key.trim() {
                    "Package" => entry.package = value.to_string(),
                    "Status" => entry.status = value.to_string(),
                    "Version" => entry.version = value.to_string(),
                    "Architecture" => entry.architecture = value.to_string(),
                    "Depends" => entry.depends = value.to_string(),
                    "Description" => entry.description = value.to_string(),
                    "Maintainer" => entry.maintainer = value.to_string(),
                    "Installed-Size" => entry.installed_size = value.parse().unwrap_or(0),
                    _ => {}
                }
            }
        }
        
        if entry.package.is_empty() {
            return Err(PdbError::InvalidRowData);
        }

        Ok(entry)
    }

    /// Encode this entry into a fixed-width row structure
    /// Field layout (offsets in bytes):
    ///   0-63:    package (64 bytes)
    ///   64-95:   status (32 bytes)
    ///   96-159:  version (64 bytes)
    ///   160-175: architecture (16 bytes)
    ///   176-431: depends (256 bytes)
    ///   432-687: description (256 bytes)
    ///   688-751: maintainer (64 bytes)
    ///   752-755: installed_size (u32 LE)
    /// Total row length: 756 bytes
    fn encode(&self) -> Vec<u8> {
        let mut row = vec![0u8; 756];

        fn write_str(row: &mut [u8], offset: usize, s: &str, max_len: usize) {
            let bytes = s.as_bytes();
            let copy_len = bytes.len().min(max_len - 1);
            row[offset..offset + copy_len].copy_from_slice(&bytes[..copy_len]);
        }

        write_str(&mut row, 0, &self.package, 64);
        write_str(&mut row, 64, &self.status, 32);
        write_str(&mut row, 96, &self.version, 64);
        write_str(&mut row, 160, &self.architecture, 16);
        write_str(&mut row, 176, &self.depends, 256);
        write_str(&mut row, 432, &self.description, 256);
        write_str(&mut row, 688, &self.maintainer, 64);
        
        row[752..756].copy_from_slice(&self.installed_size.to_le_bytes());

        row
    }
}

struct DpkgToPdbCompiler {
    disk_image: PathBuf,
    output_path: PathBuf,
    config: PdbConfig,
}

impl DpkgToPdbCompiler {
    fn new(disk_image: &str, output_path: &str, config: PdbConfig) -> Self {
        Self {
            disk_image: PathBuf::from(disk_image),
            output_path: PathBuf::from(output_path),
            config,
        }
    }

    /// Extract /var/lib/dpkg/status content using guestfish
    fn extract_dpkg(&self) -> PdbResult<String> {
        let output = std::process::Command::new("guestfish")
            .args([
                "--ro",
                "-a",
                self.disk_image.to_str().unwrap(),
                "-m",
                "/dev/sda1",
                "cat",
                "/var/lib/dpkg/status",
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
            .map_err(|_| PdbError::IoError("Invalid UTF-8 in /var/lib/dpkg/status".to_string()))
    }

    /// Parse content into structured entries
    fn parse_dpkg(&self, content: &str) -> PdbResult<Vec<DpkgEntry>> {
        let mut entries = Vec::new();
        
        // Split by double newline (blocks)
        let blocks: Vec<&str> = content.split("\n\n").collect();
        
        for (i, block) in blocks.iter().enumerate() {
            let block = block.trim();
            if block.is_empty() {
                continue;
            }

            match DpkgEntry::from_block(block) {
                Ok(entry) => entries.push(entry),
                Err(e) => {
                    eprintln!("Warning: Failed to parse block {}: {:?}", i + 1, e);
                }
            }
        }

        Ok(entries)
    }

    /// Compile parsed entries into PDB format
    fn compile(&self) -> PdbResult<()> {
        println!("Extracting /var/lib/dpkg/status from: {}", self.disk_image.display());
        let dpkg_content = self.extract_dpkg()?;
        println!("Extracted {} bytes", dpkg_content.len());

        println!("Parsing dpkg status blocks...");
        let entries = self.parse_dpkg(&dpkg_content)?;
        println!("Parsed {} entries", entries.len());

        println!("\nSample entries:");
        for (i, entry) in entries.iter().take(3).enumerate() {
            println!("  [{}] {}: version={} arch={}", i + 1, entry.package, entry.version, entry.architecture);
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
            756,
            table_data.len()
        );

        let mut header = PdbHeader::new();
        let row_count = entries.len() as u32;
        let row_length = 756;
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

        header.add_table(TableMetadata::new("dpkg_status", bbox, row_count, row_length))?;

        let mut encoder = PdbEncoder::new(self.config.clone(), header.clone());
        encoder.encode_header()?;
        encoder.encode_table(0, &table_data)?;

        let mut vcc = geos_pixel_v5::pdb::VccIntegrity::new();
        let hash = vcc.compute_table_hash(encoder.canvas(), "dpkg_status", &bbox)?;
        let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();

        println!("\nTable metadata:");
        println!("  Name: dpkg_status");
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
        eprintln!("Usage: dpkg_to_pdb <disk_image> <output.pdb.png>");
        eprintln!("");
        eprintln!("Example:");
        eprintln!("  cargo run --example dpkg_to_pdb -- ubuntu-24.04-server-cloudimg-amd64.raw /tmp/dpkg.pdb.png");
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

    println!("Tier 1 Semantic Table Extractor for /var/lib/dpkg/status");
    println!("==========================================================");
    println!("Source: {}", disk_image);
    println!("Output: {}", output_path);
    println!("Frame size: {}x{}", frame_size, frame_size);
    println!("");

    let compiler = DpkgToPdbCompiler::new(disk_image, output_path, config);

    match compiler.compile() {
        Ok(()) => {
            println!("\nSUCCESS: dpkg status compiled as semantic PDB table");
        }
        Err(e) => {
            eprintln!("\nFAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}