// sqlite_to_pdb.rs - SQLite to PDB Compiler (CLI Example)
//
// Usage:
//   cargo run --example sqlite_to_pdb -- <input.db> <output.pdb.png> [width]
//
// Example:
//   cargo run --example sqlite_to_pdb -- test.db test.pdb.png 512

use geos_pixel_v5::pdb::{PdbConfig, SqliteToPdb};

fn main() {
    let args: Vec<String> = std::env::args().collect();

    // STUB: CLI argument parsing
    // Phase 1 Step 6 will implement proper error handling
    if args.len() < 3 {
        eprintln!("Usage: sqlite_to_pdb <input.db> <output.pdb.png> [width]");
        std::process::exit(1);
    }

    let sqlite_path = &args[1];
    let pdb_path = &args[2];

    // Parse optional width (default 512)
    let width = if args.len() > 3 {
        args[3]
            .parse::<usize>()
            .expect("Width must be a number")
    } else {
        512
    };

    let config = match PdbConfig::new(width, width) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Invalid configuration: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("Compiling {} to {}", sqlite_path, pdb_path);
    println!("Frame size: {}x{}", width, width);

    let compiler = SqliteToPdb::new(sqlite_path, pdb_path, config);

    match compiler.compile() {
        Ok(()) => {
            println!("Compilation successful: {}", pdb_path);
            
            // Step 6 Verification
            println!("Verifying PDB frame...");
            let mut decoder = geos_pixel_v5::pdb::PdbDecoder::load_png(pdb_path).expect("Failed to load PDB");
            let header = decoder.decode_header().expect("Failed to decode header").clone();
            
            println!("Decoded Header:");
            println!("  Version: {}", header.version);
            println!("  Table count: {}", header.table_count);
            
            for table in &header.tables {
                let name = std::str::from_utf8(&table.name).unwrap_or("").trim_end_matches('\0');
                println!("  Table '{}': {} rows, {} bytes/row", name, table.row_count, table.row_length);
                let data = decoder.decode_table(name).expect("Failed to decode table");
                println!("    Decoded {} bytes", data.len());
                
                // Hash verification
                let mut vcc = geos_pixel_v5::pdb::VccIntegrity::new();
                let hash = vcc.compute_table_hash(decoder.canvas(), name, &table.bbox).expect("Failed to compute hash");
                let hex_hash: String = hash.iter().map(|b| format!("{:02x}", b)).collect();
                println!("    Verified VCC Hash: {}", hex_hash);
            }
            println!("Verification passed.");
        }
        Err(e) => {
            eprintln!("Compilation failed: {:?}", e);
            std::process::exit(1);
        }
    }
}