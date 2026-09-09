// file_metadata_to_pdb.rs - Tier 2 File Metadata Semantic Mapping
//
// Extracts complete file metadata from disk images using guestfish
// and compiles it into spatial PDB format.
// This builds the File_Metadata table that enables GPU-native filesystem queries.
//
// Usage:
//   cargo run --example file_metadata_to_pdb -- <disk_image> <output.pdb.png>
//
// Example:
//   cargo run --example file_metadata_to_pdb -- ubuntu-24.04-server-cloudimg-amd64.raw /tmp/file_metadata.pdb.png

use geos_pixel::pdb::{
    BoundingBox, PdbConfig, PdbEncoder, PdbError, PdbHeader, PdbResult, TableMetadata, HEADER_SIZE,
};
use std::path::PathBuf;
use std::io::Write;

/// Represents complete file metadata for GPU queryable indexing
///
/// Field layout (offsets in bytes):
///   0-255:   path (256 bytes, null-padded UTF-8)
///   256-263: offset (u64 LE) - byte offset in tiled rootfs blob
///   264-267: size (u32 LE) - file size in bytes
///   268-269: mode (u16 LE) - file permissions/mode
///   270-273: uid (u32 LE) - owner user ID
///   274-277: gid (u32 LE) - owner group ID
///   278-279: file_type (u16 LE) - file type enum
///   280-283: mtime (u32 LE) - modification time (Unix timestamp)
///   284-287: reserved (u32 LE)
/// Total row length: 288 bytes
#[derive(Debug, Clone)]
struct FileMetadataEntry {
    path: String,
    offset: u64,
    size: u32,
    mode: u16,
    uid: u32,
    gid: u32,
    file_type: u16,
    mtime: u32,
}

#[derive(Debug, Clone, Copy)]
#[repr(u16)]
enum FileType {
    Regular = 0,
    Directory = 1,
    Symlink = 2,
    CharDevice = 3,
    BlockDevice = 4,
    Fifo = 5,
    Socket = 6,
}

impl FileMetadataEntry {
    fn encode(&self) -> Vec<u8> {
        let mut row = vec![0u8; 288];

        fn write_str(row: &mut [u8], offset: usize, s: &str, max_len: usize) {
            let bytes = s.as_bytes();
            let copy_len = bytes.len().min(max_len - 1);
            row[offset..offset + copy_len].copy_from_slice(&bytes[..copy_len]);
        }

        write_str(&mut row, 0, &self.path, 256);
        row[256..264].copy_from_slice(&self.offset.to_le_bytes());
        row[264..268].copy_from_slice(&self.size.to_le_bytes());
        row[268..270].copy_from_slice(&self.mode.to_le_bytes());
        row[270..274].copy_from_slice(&self.uid.to_le_bytes());
        row[274..278].copy_from_slice(&self.gid.to_le_bytes());
        row[278..280].copy_from_slice(&self.file_type.to_le_bytes());
        row[280..284].copy_from_slice(&self.mtime.to_le_bytes());

        row
    }
}

struct FileMetadataToPdbCompiler {
    disk_image: PathBuf,
    output_path: PathBuf,
    config: PdbConfig,
    max_files: Option<usize>,
    mount_device: Option<String>,
}

impl FileMetadataToPdbCompiler {
    fn new(disk_image: &str, output_path: &str, config: PdbConfig) -> Self {
        Self {
            disk_image: PathBuf::from(disk_image),
            output_path: PathBuf::from(output_path),
            config,
            max_files: None,
            mount_device: None,
        }
    }

    fn with_max_files(mut self, max_files: usize) -> Self {
        self.max_files = Some(max_files);
        self
    }

    fn run_guestfish_command(&mut self, commands: &[&str]) -> PdbResult<String> {
        let mut child = std::process::Command::new("guestfish")
            .arg("--ro")
            .arg("-a")
            .arg(self.disk_image.to_str().unwrap())
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| PdbError::IoError(format!("Failed to spawn guestfish: {}", e)))?;

        if let Some(stdin) = child.stdin.as_mut() {
            for cmd in commands {
                let _ = writeln!(stdin, "{}", cmd);
            }
        }

        let output = child
            .wait_with_output()
            .map_err(|e| PdbError::IoError(format!("Failed to get guestfish output: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(PdbError::IoError(format!(
                "Guestfish command failed: {}",
                stderr
            )));
        }

        Ok(String::from_utf8_lossy(&output.stdout.as_slice()).to_string())
    }

    fn find_mount_device(&mut self) -> PdbResult<&str> {
        if self.mount_device.is_some() {
            return Ok(self.mount_device.as_ref().unwrap());
        }

        let output = self.run_guestfish_command(&["run", "list-filesystems"])?;

        let mount_device = output
            .lines()
            .find(|line| {
                line.contains("ext")
                    || line.contains("xfs")
                    || line.contains("btrfs")
                    || line.contains("ext4")
            })
            .and_then(|line| line.split(':').next())
            .ok_or_else(|| PdbError::IoError("No suitable filesystem found".to_string()))?;

        let device = mount_device.trim().to_string();
        println!("Using filesystem: {}", device);
        self.mount_device = Some(device);
        Ok(self.mount_device.as_ref().unwrap())
    }

    fn extract_file_metadata(&mut self) -> PdbResult<Vec<FileMetadataEntry>> {
        println!("Extracting file metadata from: {}", self.disk_image.display());

        let mount_device = self.find_mount_device()?.to_string();

        let stat_cmd = format!("find / -xdev -type f -exec stat -c '%n|%s|%f|%u|%g|%Y' {{}} + > /tmp/stats.txt");
        self.run_guestfish_command(&[
            "run",
            &format!("mount {} /", mount_device),
            &format!("sh \"{}\"", stat_cmd),
            "download /tmp/stats.txt /tmp/local_stats.txt",
        ])?;

        let output = std::fs::read_to_string("/tmp/local_stats.txt")
            .map_err(|e| PdbError::IoError(format!("Failed to read stats: {}", e)))?;

        let mut entries = Vec::new();

        for line in output.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with("libguestfs:") {
                continue;
            }

            let parts: Vec<&str> = line.split('|').collect();
            if parts.len() != 6 {
                continue;
            }

            let path = parts[0].to_string();
            let size = parts[1].parse().unwrap_or(0);
            let mode_hex = parts[2];
            let mode_val = u32::from_str_radix(mode_hex, 16).unwrap_or(0);
            let uid = parts[3].parse().unwrap_or(0);
            let gid = parts[4].parse().unwrap_or(0);
            let mtime = parts[5].parse().unwrap_or(0);

            let mode = (mode_val & 0o7777) as u16;

            let file_type = match mode_val & 0o170000 {
                0o140000 => FileType::Socket,
                0o120000 => FileType::Symlink,
                0o100000 => FileType::Regular,
                0o060000 => FileType::BlockDevice,
                0o020000 => FileType::CharDevice,
                0o010000 => FileType::Fifo,
                0o040000 => FileType::Directory,
                _ => FileType::Regular,
            };

            entries.push(FileMetadataEntry {
                path,
                offset: 0,
                size,
                mode,
                uid,
                gid,
                file_type: file_type as u16,
                mtime,
            });

            if let Some(max) = self.max_files {
                if entries.len() >= max {
                    break;
                }
            }
        }

        println!("Extracted metadata for {} files", entries.len());
        Ok(entries)
    }

    fn compile(&mut self) -> PdbResult<()> {
        let entries = self.extract_file_metadata()?;

        if entries.is_empty() {
            return Err(PdbError::IoError("No file metadata found".to_string()));
        }

        println!("\nSample entries:");
        for (i, entry) in entries.iter().take(5).enumerate() {
            let type_str = match entry.file_type {
                0 => "file",
                1 => "dir",
                2 => "symlink",
                3 => "char",
                4 => "block",
                5 => "fifo",
                6 => "socket",
                _ => "unknown",
            };
            println!(
                "  [{}] {} [{}] size={} mode={:04o} uid={} gid={}",
                i + 1,
                entry.path,
                type_str,
                entry.size,
                entry.mode,
                entry.uid,
                entry.gid
            );
        }
        if entries.len() > 5 {
            println!("  ... and {} more", entries.len() - 5);
        }

        let mut table_data = Vec::new();
        for entry in &entries {
            table_data.extend_from_slice(&entry.encode());
        }

        println!(
            "\nEncoded {} rows × {} bytes = {} total bytes",
            entries.len(),
            288,
            table_data.len()
        );

        let mut header = PdbHeader::new();
        let row_count = entries.len() as u32;
        let row_length = 288;
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

        header.add_table(TableMetadata::new(
            "file_metadata",
            bbox,
            row_count,
            row_length,
        ))?;

        let mut encoder = PdbEncoder::new(self.config.clone(), header.clone());
        encoder.encode_header()?;
        encoder.encode_table(0, &table_data)?;

        let mut vcc = geos_pixel::pdb::VccIntegrity::new();
        let hash = vcc.compute_table_hash(encoder.canvas(), "file_metadata", &bbox)?;
        let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();

        println!("\nTable metadata:");
        println!("  Name: file_metadata");
        println!("  Row count: {}", row_count);
        println!("  Row length: {} bytes", row_length);
        println!("  Total bytes: {}", byte_count);
        println!(
            "  Bounding box: ({}, {}) to ({}, {})",
            bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max
        );
        println!("  VCC Hash: {}", hex_hash);

        encoder.save_png(&self.output_path)?;
        println!("\nWrote: {}", self.output_path.display());

        Ok(())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 3 {
        eprintln!("Usage: file_metadata_to_pdb <disk_image> <output.pdb.png>");
        eprintln!("");
        eprintln!("Example:");
        eprintln!(
            "  cargo run --example file_metadata_to_pdb -- ubuntu-24.04-server-cloudimg-amd64.raw /tmp/file_metadata.pdb.png"
        );
        eprintln!("");
        eprintln!("Arguments:");
        eprintln!("  disk_image    Path to disk image (.raw/.img)");
        eprintln!("  output.pdb.png Output PDB PNG file");
        std::process::exit(1);
    }

    let disk_image = &args[1];
    let output_path = &args[2];

    let frame_size = 4096;

    let config = match PdbConfig::new(frame_size, frame_size) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("Tier 2 File Metadata Semantic Mapping");
    println!("====================================");
    println!("Source: {}", disk_image);
    println!("Output: {}", output_path);
    println!("Frame size: {}x{}", frame_size, frame_size);
    println!();
    println!("This extracts complete file metadata from the disk image and");
    println!("compiles it into a GPU-queryable spatial table.");
    println!();

    let mut compiler =
        FileMetadataToPdbCompiler::new(disk_image, output_path, config);

    match compiler.compile() {
        Ok(()) => {
            println!("\nSUCCESS: File metadata compiled as semantic PDB table");
            println!();
            println!("Next steps:");
            println!("  1. Integrate with tiled rootfs to compute byte offsets");
            println!("  2. Write WGSL shaders for GPU-native filesystem queries");
        }
        Err(e) => {
            eprintln!("\nFAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}