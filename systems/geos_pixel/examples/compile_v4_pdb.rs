// compile_v4_pdb.rs - V4 Blob-Table PDB Compiler
//
// Takes binary files (bootloader, kernel, initramfs) and compiles them into
// spatial PDB format using blob-table semantics (row_length=3).
//
// Usage:
//   cargo run --example compile_v4_pdb -- <name> <file_path> <output.pdb.png> [width]
//
// Example:
//   cargo run --example compile_v4_pdb -- hello ../boot_images/hello.img /tmp/hello.pdb.png 2048

use geos_pixel::pdb::{
    BoundingBox, PdbConfig, PdbEncoder, PdbError, PdbHeader, PdbResult, TableMetadata, HEADER_SIZE,
};
use std::fs;
use std::path::PathBuf;

#[derive(Debug)]
struct BlobTable {
    name: String,
    data: Vec<u8>,
}

struct V4Compiler {
    tables: Vec<BlobTable>,
    output_path: PathBuf,
    config: PdbConfig,
}

impl V4Compiler {
    fn new(table_inputs: Vec<(String, String)>, output_path: &str, config: PdbConfig) -> PdbResult<Self> {
        let mut tables = Vec::new();
        
        for (table_name, file_path) in table_inputs {
            let data = fs::read(&file_path)
                .map_err(|e| PdbError::IoError(format!("Failed to read {}: {}", file_path, e)))?;
            
            tables.push(BlobTable {
                name: table_name,
                data,
            });
        }

        Ok(Self {
            tables,
            output_path: PathBuf::from(output_path),
            config,
        })
    }

    fn compile(&self) -> PdbResult<()> {
        let mut header = PdbHeader::new();
        let mut current_y = HEADER_SIZE as u32;

        for table in &self.tables {
            // Blob-table semantics: store exact byte count
            // We set row_length = 1 so expected_bytes = row_count exactly
            // This allows exact truncation after decoding the padded Hilbert stream
            let byte_count = table.data.len();
            let row_length: u32 = 1;
            let row_count: u32 = byte_count as u32;

            // Calculate bounding box height needed
            // We need pixels for ceil(byte_count / 3) triplets
            let triplets_needed = (byte_count + 2) / 3;
            let height_needed = if triplets_needed == 0 {
                1
            } else {
                (triplets_needed as f64 / self.config.width as f64).ceil() as u32
            };

            let y_min = current_y;
            let y_max = y_min + height_needed - 1;

            if y_max >= self.config.height as u32 {
                return Err(PdbError::EncodingFailed);
            }

            let bbox = BoundingBox {
                x_min: 0,
                y_min,
                x_max: (self.config.width - 1) as u32,
                y_max,
            };

            header.add_table(TableMetadata::new(&table.name, bbox, row_count, row_length))?;

            current_y = y_max + 1;
        }

        // Create encoder and encode header
        let mut encoder = PdbEncoder::new(self.config.clone(), header.clone());
        encoder.encode_header()?;

        // Encode each table
        for (idx, table) in self.tables.iter().enumerate() {
            encoder.encode_table(idx, &table.data)?;

            // Compute and print VCC hash
            let bbox = header.tables[idx].bbox;
            let mut vcc = geos_pixel::pdb::VccIntegrity::new();
            let hash = vcc.compute_table_hash(encoder.canvas(), &table.name, &bbox)?;
            let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();
            println!("Table '{}': {} bytes -> {} rows (3B/row)", table.name, table.data.len(), header.tables[idx].row_count);
            println!("  Bounding box: ({}, {}) to ({}, {})", bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max);
            println!("  VCC Hash: {}", hex_hash);
        }

        // Save PDB frame
        encoder.save_png(&self.output_path)?;
        println!("Wrote: {}", self.output_path.display());

        Ok(())
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 5 || (args.len() - 3) % 2 != 0 {
        eprintln!("Usage: compile_v4_pdb <output.pdb.png> <width> <name1> <file1> [name2 file2 ...]");
        eprintln!("");
        eprintln!("Example:");
        eprintln!("  cargo run --example compile_v4_pdb -- /tmp/multi.pdb.png 2048 bootloader boot.img kernel vmlinuz");
        eprintln!("");
        eprintln!("Arguments:");
        eprintln!("  output.pdb.png Output PDB PNG file");
        eprintln!("  width          Frame width (must be power of 2)");
        eprintln!("  nameN          Table N name (max 15 chars)");
        eprintln!("  fileN          Path to binary file for Table N");
        std::process::exit(1);
    }

    let output_path = &args[1];
    let width = args[2].parse::<usize>().expect("Width must be a number");
    
    let mut table_inputs = Vec::new();
    for i in (3..args.len()).step_by(2) {
        table_inputs.push((args[i].clone(), args[i+1].clone()));
    }

    let config = match PdbConfig::new(width, width) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("V4 PDB Blob-Table Compiler (Multi-Table)");
    println!("========================================");
    println!("Output: {}", output_path);
    println!("Frame size: {}x{}", width, width);
    println!("Tables to encode: {}", table_inputs.len());
    for (name, path) in &table_inputs {
        println!("  - {}: {}", name, path);
    }
    println!("");

    let compiler = match V4Compiler::new(table_inputs, output_path, config) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to create compiler: {:?}", e);
            std::process::exit(1);
        }
    };

    match compiler.compile() {
        Ok(()) => {
            println!("");
            println!("SUCCESS: Blob table compiled successfully");
        }
        Err(e) => {
            eprintln!("FAILED: {:?}", e);
            std::process::exit(1);
        }
    }
}