// pdb_gpu_query.rs - GPU-Accelerated PDB Query CLI
//
// Usage:
//   cargo run --example pdb_gpu_query --features "gpu" -- <pdb.png> <table_name> <pattern_hex>
//
// Example:
//   cargo run --example pdb_gpu_query --features "gpu" -- test.pdb.png users 616c696365

#[cfg(feature = "gpu")]
use geos_pixel_v5::pdb::{GpuQueryConfig, GpuQueryEngine, PdbDecoder, QueryResult};
#[cfg(feature = "gpu")]
use std::time::Instant;

#[cfg(feature = "gpu")]
fn parse_hex_pattern(hex_str: &str) -> Result<Vec<u8>, String> {
    let hex_str = hex_str.trim_start_matches("0x");
    if hex_str.len() % 2 != 0 {
        return Err("Hex string must have even length".to_string());
    }

    let mut bytes = Vec::new();
    for i in (0..hex_str.len()).step_by(2) {
        let byte_str = &hex_str[i..i + 2];
        let byte = u8::from_str_radix(byte_str, 16)
            .map_err(|e| format!("Invalid hex at position {}: {}", i, e))?;
        bytes.push(byte);
    }
    Ok(bytes)
}

#[cfg(feature = "gpu")]
fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 4 {
        eprintln!("Usage: pdb_gpu_query <pdb.png> <table_name> <pattern_hex>");
        eprintln!("\nExamples:");
        eprintln!("  pdb_gpu_query test.pdb.png users 616c696365");  // Search for 'alice' in hex
        eprintln!("  pdb_gpu_query test.pdb.png sessions 746f6b");   // Search for 'tok' in hex");
        eprintln!("\nNote: This requires the 'gpu' feature: cargo run --example pdb_gpu_query --features 'gpu'");
        std::process::exit(1);
    }

    let pdb_path = &args[1];
    let table_name = &args[2];
    let pattern_hex = &args[3];

    println!("=== GPU-Accelerated PDB Query ===");
    println!("PDB file: {}", pdb_path);
    println!("Table: {}", table_name);
    println!("Pattern (hex): {}", pattern_hex);

    // Parse hex pattern
    let pattern = match parse_hex_pattern(pattern_hex) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("Error parsing pattern: {}", e);
            std::process::exit(1);
        }
    };
    println!("Pattern bytes: {:?}", pattern);

    // Load PDB frame
    println!("\nLoading PDB frame...");
    let mut decoder = match PdbDecoder::load_png(pdb_path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("Failed to load PDB: {:?}", e);
            std::process::exit(1);
        }
    };

    // Decode header
    let header = match decoder.decode_header().map(|h| h.clone()) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("Failed to decode header: {:?}", e);
            std::process::exit(1);
        }
    };

    println!("PDB version: {}", header.version);
    println!("Tables: {}", header.table_count);
    for table in &header.tables {
        let name = std::str::from_utf8(&table.name)
            .unwrap_or("")
            .trim_end_matches('\0');
        println!("  - {}: {} rows, {} bytes/row", name, table.row_count, table.row_length);
    }

    // Find table metadata
    let table_metadata = header
        .tables
        .iter()
        .find(|t| {
            let name = std::str::from_utf8(&t.name)
                .unwrap_or("")
                .trim_end_matches('\0');
            name == table_name
        })
        .ok_or_else(|| format!("Table '{}' not found", table_name));

    let table_metadata = match table_metadata {
        Ok(m) => m,
        Err(e) => {
            eprintln!("Error: {}", e);
            std::process::exit(1);
        }
    };

    println!("\nTarget table:");
    println!("  Bounding box: ({}, {}) to ({}, {})",
        table_metadata.bbox.x_min,
        table_metadata.bbox.y_min,
        table_metadata.bbox.x_max,
        table_metadata.bbox.y_max);
    println!("  Row count: {}", table_metadata.row_count);
    println!("  Row length: {} bytes", table_metadata.row_length);

    // Initialize GPU engine
    println!("\nInitializing GPU query engine...");
    let gpu_start = Instant::now();
    let engine = match GpuQueryEngine::new() {
        Ok(e) => e,
        Err(e) => {
            eprintln!("Failed to initialize GPU: {:?}", e);
            eprintln!("Note: GPU queries require a compatible GPU and proper drivers");
            std::process::exit(1);
        }
    };
    println!("GPU initialized in {:?}", gpu_start.elapsed());

    // Load PDB as texture
    println!("\nLoading PDB as GPU texture...");
    let texture_start = Instant::now();

    // Convert RgbaImage to wgpu::Texture using our new helper
    let texture = engine.create_texture_from_image(decoder.canvas());
    println!("Texture loaded in {:?}", texture_start.elapsed());

    // Execute GPU query
    println!("\nExecuting GPU pattern scan...");
    let query_start = Instant::now();

    let config = GpuQueryConfig::default();
    let result = engine.scan_table_for_pattern(&texture, &table_metadata.bbox, &pattern, &config);

    match result {
        Ok(res) => {
            println!("Query time: {:?}", query_start.elapsed());
            println!("Workgroups dispatched: {}", res.workgroups_dispatched);
            println!("Matches found: {}", res.matches.len());
            
            for (i, match_dist) in res.matches.iter().take(10).enumerate() {
                let global_idx = match_dist / 3;
                let channel = match_dist % 3;
                
                // Convert global_idx to chunk_index by counting valid Hilbert points
                let bbox_width = table_metadata.bbox.x_max - table_metadata.bbox.x_min + 1;
                let bbox_height = table_metadata.bbox.y_max - table_metadata.bbox.y_min + 1;
                let grid_size = bbox_width.max(bbox_height).next_power_of_two();
                
                let mut chunk_index = 0;
                for h in 0..global_idx {
                    let (x, y) = geos_pixel_v5::hilbert::HilbertCurve::d2xy(grid_size as usize, h as usize);
                    let abs_x = table_metadata.bbox.x_min + x as u32;
                    let abs_y = table_metadata.bbox.y_min + y as u32;
                    if abs_x <= table_metadata.bbox.x_max && abs_y <= table_metadata.bbox.y_max {
                        chunk_index += 1;
                    }
                }
                
                let linear_byte_offset = chunk_index * 3 + channel;
                let row_index = linear_byte_offset / table_metadata.row_length;
                let col_offset = linear_byte_offset % table_metadata.row_length;
                
                println!("  Match {}: Spatial offset {} -> Row {}, Byte offset {} (Linear byte {})", 
                         i + 1, match_dist, row_index, col_offset, linear_byte_offset);
            }
            if res.matches.len() > 10 {
                println!("  ... and {} more", res.matches.len() - 10);
            }
        }
        Err(e) => {
            eprintln!("Query failed: {:?}", e);
            std::process::exit(1);
        }
    }

    println!("\n=== GPU Query Complete ===");
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("Error: GPU feature not enabled");
    eprintln!("Run with: cargo run --example pdb_gpu_query --features 'gpu' -- <args>");
    std::process::exit(1);
}