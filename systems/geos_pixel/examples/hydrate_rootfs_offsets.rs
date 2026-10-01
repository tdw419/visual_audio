// hydrate_rootfs_offsets.rs - Path A: Offset Hydration for File Metadata
//
// Extracts file contents from a disk image, creates a tiled rootfs blob,
// and hydrates the File_Metadata table with real byte offsets.
//
// Usage:
//   cargo run --example hydrate_rootfs_offsets -- <disk_image> <output_base>

use geos_pixel::pdb::{
    BoundingBox, PdbConfig, PdbEncoder, PdbError, PdbResult, PdbHeader, TableMetadata, HEADER_SIZE,
    tiled::{TileGridConfig, TiledPdbEncoder, TiledPdbHeader},
};
use std::path::PathBuf;
use std::io::Write;

/// Represents complete file metadata for GPU queryable indexing
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

/// Parse a NUL-padded tar header string field.
fn parse_tar_cstr(field: &[u8]) -> String {
    let end = field.iter().position(|&b| b == 0).unwrap_or(field.len());
    String::from_utf8_lossy(&field[..end]).to_string()
}

/// Parse a NUL/space-padded octal numeric tar header field.
fn parse_tar_octal(field: &[u8]) -> u64 {
    let s: String = field
        .iter()
        .take_while(|&&b| b != 0)
        .map(|&b| b as char)
        .collect();
    u64::from_str_radix(s.trim(), 8).unwrap_or(0)
}

struct RootfsHydrator {
    disk_image: PathBuf,
    output_base: PathBuf,
    /// Scratch directory for large intermediate downloads (tar, filelist).
    /// Must NOT be on a near-full root filesystem -- a full rootfs tar can
    /// be several GB.
    scratch_dir: PathBuf,
    config: PdbConfig,
    tile_config: TileGridConfig,
    mount_device: Option<String>,
}

impl RootfsHydrator {
    fn new(
        disk_image: &str,
        output_base: &str,
        scratch_dir: &str,
        config: PdbConfig,
        tile_config: TileGridConfig,
    ) -> Self {
        Self {
            disk_image: PathBuf::from(disk_image),
            output_base: PathBuf::from(output_base),
            scratch_dir: PathBuf::from(scratch_dir),
            config,
            tile_config,
            mount_device: None,
        }
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

    /// Stream the entire mounted rootfs to a local tar via libguestfs's native
    /// `tar-out`, then parse the USTAR stream directly into file metadata +
    /// a contiguous content blob with real byte offsets.
    ///
    /// This replaces two earlier, broken approaches:
    ///   1. One guestfish process spawn (+ remount) per file to download
    ///      content individually -- ~2 days for 69k files.
    ///   2. Building the tar *inside* the guest via `sh "tar ..."` then
    ///      downloading it -- fails outright, because the guestfish
    ///      appliance's writable overlay (used for any write the guest makes
    ///      to its own /tmp) has nowhere near enough room for a multi-GB tar
    ///      ("tar: Wrote only 4096 of 10240 bytes"). It also self-polluted
    ///      the file list, since a `> /tmp/stats.txt` redirection creates
    ///      that file before `find` finishes scanning, so `find` sees its
    ///      own output file mid-write.
    ///
    /// `tar-out` sidesteps both: it streams file data over the libguestfs
    /// protocol straight to a host-side file with no write to the guest disk
    /// at all, so it works under `--ro` and isn't bounded by overlay size.
    /// It also hands us mode/uid/gid/mtime/size for free via tar headers, so
    /// there's no separate `find | stat` pass to keep in sync.
    fn tar_out_and_parse(&mut self) -> PdbResult<(Vec<FileMetadataEntry>, Vec<u8>)> {
        let mount_device = self.find_mount_device()?.to_string();
        let local_tar = self.scratch_dir.join("rootfs.tar");

        println!(
            "Streaming full rootfs via tar-out to {} (single pass, no guest-side write)...",
            local_tar.display()
        );

        self.run_guestfish_command(&[
            "run",
            &format!("mount {} /", mount_device),
            &format!(
                "tar-out / {} numericowner:true",
                local_tar.to_str().unwrap()
            ),
        ])?;

        let tar_bytes = std::fs::read(&local_tar)
            .map_err(|e| PdbError::IoError(format!("Failed to read downloaded tar: {}", e)))?;

        println!(
            "Downloaded tar: {} bytes, parsing USTAR entries and building blob...",
            tar_bytes.len()
        );

        let mut entries = Vec::new();
        let mut rootfs_blob = Vec::new();
        let mut running_offset: u64 = 0;

        let mut pos = 0usize;
        while pos + 512 <= tar_bytes.len() {
            let header = &tar_bytes[pos..pos + 512];

            // Two consecutive all-zero blocks mark end-of-archive.
            if header.iter().all(|&b| b == 0) {
                break;
            }

            let name = parse_tar_cstr(&header[0..100]);
            let mode_val = parse_tar_octal(&header[100..108]);
            let uid = parse_tar_octal(&header[108..116]) as u32;
            let gid = parse_tar_octal(&header[116..124]) as u32;
            let size = parse_tar_octal(&header[124..136]);
            let mtime = parse_tar_octal(&header[136..148]) as u32;
            let typeflag = header[156];

            let data_start = pos + 512;
            let data_end = data_start + size as usize;
            if data_end > tar_bytes.len() {
                break; // truncated archive
            }

            let file_type = match typeflag {
                b'0' | 0 => Some(0u16), // regular file
                b'2' => Some(2),        // symlink
                b'5' => Some(1),        // directory
                b'3' => Some(3),        // char device
                b'4' => Some(4),        // block device
                b'6' => Some(5),        // fifo
                _ => None,              // hard link ('1'), etc: not modeled
            };

            if let Some(file_type) = file_type {
                let offset = if file_type == 0 {
                    let off = running_offset;
                    let data = &tar_bytes[data_start..data_end];
                    rootfs_blob.extend_from_slice(data);
                    running_offset += data.len() as u64;
                    off
                } else {
                    0
                };

                // tar-out names members "./foo", "./bar/baz", and "." for the
                // root itself -- normalize to clean absolute paths ("/foo",
                // "/bar/baz", "/") matching the convention used by the other
                // Tier 1 extractors (etc_to_pdb, dpkg_to_pdb).
                let clean = name.trim_start_matches("./").trim_end_matches('/');
                let path = if clean.is_empty() {
                    "/".to_string()
                } else {
                    format!("/{}", clean)
                };

                entries.push(FileMetadataEntry {
                    path,
                    offset,
                    size: size as u32,
                    mode: (mode_val & 0o7777) as u16,
                    uid,
                    gid,
                    file_type,
                    mtime,
                });
            }

            // Advance past this member's data, padded up to a 512 boundary.
            let padded_size = (size as usize + 511) / 512 * 512;
            pos = data_start + padded_size;
        }

        println!(
            "Parsed {} entries; rootfs blob complete: {} bytes (~{} MB)",
            entries.len(),
            rootfs_blob.len(),
            rootfs_blob.len() / 1_000_000
        );

        // Sort by path for a deterministic, reproducible metadata table.
        // Offsets already point into `rootfs_blob` and are unaffected by
        // reordering the metadata rows.
        entries.sort_by(|a, b| a.path.cmp(&b.path));

        Ok((entries, rootfs_blob))
    }

    /// Compile tiled rootfs blob and metadata table
    fn compile(&mut self) -> PdbResult<()> {
        let (entries, rootfs_blob) = self.tar_out_and_parse()?;

        if entries.is_empty() {
            return Err(PdbError::IoError("No file metadata found".to_string()));
        }

        // Verify offset hydration worked
        let total_blob_size = rootfs_blob.len() as u64;
        println!("\nOffset hydration verification:");
        println!("  Total blob size: {} bytes", total_blob_size);
        let last_entry = entries.last().unwrap();
        println!(
            "  Last file offset: {} + {} = {}",
            last_entry.offset,
            last_entry.size,
            last_entry.offset + last_entry.size as u64
        );
        if last_entry.offset + last_entry.size as u64 <= total_blob_size {
            println!("  ✓ All offsets within blob bounds");
        } else {
            return Err(PdbError::IoError("Offset overflow detected!".to_string()));
        }

        // Encode tiled rootfs blob
        println!("\n=== Encoding Tiled Rootfs Blob ===");
        let rootfs_base = self.output_base.join("rootfs_tiled");
        std::fs::create_dir_all(&rootfs_base)
            .map_err(|e| PdbError::IoError(format!("Failed to create output dir: {}", e)))?;

        let mut tiled_header = TiledPdbHeader::new(self.tile_config.clone());
        tiled_header.add_table(TableMetadata::new(
            "rootfs_blob",
            BoundingBox {
                x_min: 0,
                y_min: 0,
                x_max: self.tile_config.logical_width - 1,
                y_max: self.tile_config.logical_height - 1,
            },
            rootfs_blob.len() as u32,
            1,
        ))?;

        let mut tiled_encoder = TiledPdbEncoder::new(rootfs_base.to_str().unwrap(), tiled_header)?;
        tiled_encoder.encode_table("rootfs_blob", &rootfs_blob)?;
        tiled_encoder.save_header()?;

        println!("✓ Tiled rootfs blob encoded");

        // Encode metadata table
        println!("\n=== Encoding File Metadata Table ===");
        let metadata_path = self.output_base.join("file_metadata.pdb.png");

        let mut table_data = Vec::new();
        for entry in &entries {
            table_data.extend_from_slice(&entry.encode());
        }

        println!(
            "Encoded {} rows × {} bytes = {} total bytes",
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

        println!("\nFile Metadata Table:");
        println!("  Row count: {}", row_count);
        println!("  Row length: {} bytes", row_length);
        println!("  Total bytes: {}", byte_count);
        println!(
            "  Bounding box: ({}, {}) to ({}, {})",
            bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max
        );
        println!("  VCC Hash: {}", hex_hash);

        encoder.save_png(&metadata_path)?;
        println!("✓ Wrote: {}", metadata_path.display());

        // Spot-check a few files
        println!("\n=== Spot-Check Verification ===");
        for entry in entries.iter().take(3) {
            println!("  {}:", entry.path);
            println!("    Offset: {}", entry.offset);
            println!("    Size: {}", entry.size);
            let file_end = entry.offset + entry.size as u64;
            if file_end <= total_blob_size as u64 {
                println!("    ✓ Within bounds");
            } else {
                println!("    ✗ OVERFLOW!");
            }
        }

        println!("\n=== SUCCESS ===");
        println!("Output artifacts:");
        println!("  Rootfs tiles: {}", rootfs_base.display());
        println!("  Metadata table: {}", metadata_path.display());
        println!("\nNext steps:");
        println!("  1. Write WGSL shader to query file_metadata table");
        println!("  2. Use shader to find offset for /path/to/file");
        println!("  3. Read bytes from tiled rootfs at that offset");

        Ok(())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 3 && args.len() != 4 {
        eprintln!("Usage: hydrate_rootfs_offsets <disk_image> <output_base> [scratch_dir]");
        eprintln!("");
        eprintln!("Example:");
        eprintln!(
            "  cargo run --example hydrate_rootfs_offsets -- ubuntu-24.04-server-cloudimg-amd64.raw /home/jericho/pdb_hydration_scratch/out /home/jericho/pdb_hydration_scratch"
        );
        eprintln!("");
        eprintln!("Arguments:");
        eprintln!("  disk_image  Path to disk image (.raw/.img)");
        eprintln!("  output_base Base directory for output files (final PDB/tile artifacts)");
        eprintln!(
            "  scratch_dir Directory for large intermediates (tar of full rootfs) -- \
            defaults to output_base. MUST have room for a full rootfs's worth of bytes; \
            do not point this at a near-full root filesystem."
        );
        std::process::exit(1);
    }

    let disk_image = &args[1];
    let output_base = &args[2];
    let scratch_dir = if args.len() == 4 { &args[3] } else { output_base };

    let frame_size = 4096;

    let config = match PdbConfig::new(frame_size, frame_size) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    let tile_config = match TileGridConfig::new(4096, 32768, 32768) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid tile configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("Path A: Offset Hydration for File Metadata");
    println!("=========================================");
    println!("Source: {}", disk_image);
    println!("Output base: {}", output_base);
    println!("Frame size: {}x{}", frame_size, frame_size);
    println!(
        "Tile config: {}x{} tiles, logical {}x{}",
        tile_config.tiles_per_row,
        tile_config.tiles_per_col,
        tile_config.logical_width,
        tile_config.logical_height
    );
    println!();
    println!("This will:");
    println!("  1. Extract file metadata from disk image");
    println!("  2. Build contiguous rootfs blob with all file contents");
    println!("  3. Hydrate offset field in metadata entries");
    println!("  4. Encode tiled rootfs blob + metadata table");
    println!();

    if let Err(e) = std::fs::create_dir_all(scratch_dir) {
        eprintln!("Failed to create scratch dir {}: {}", scratch_dir, e);
        std::process::exit(1);
    }

    let mut hydrator = RootfsHydrator::new(disk_image, output_base, scratch_dir, config, tile_config);

    match hydrator.compile() {
        Ok(()) => {
            println!("\nSUCCESS: Rootfs offsets hydrated and encoded");
        }
        Err(e) => {
            eprintln!("\nFAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}