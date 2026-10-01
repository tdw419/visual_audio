/// Inspect file_metadata table structure
use geos_pixel::PdbDecoder;

fn main() {
    let file_metadata_path = "/home/jericho/pdb_hydration_scratch/out/file_metadata.pdb.png";
    let mut decoder = PdbDecoder::load_png(file_metadata_path).unwrap();
    decoder.decode_header().unwrap();
    
    let metadata_blob = decoder.decode_table("file_metadata").unwrap();
    
    println!("File metadata blob: {} bytes", metadata_blob.len());
    println!("First 100 bytes: {:02X?}", &metadata_blob[..100]);
    
    // Try to find patterns
    // Entry structure appears to be: path (variable?), metadata...
    // Let's look for the string "/etc/passwd"
    
    if let Some(pos) = metadata_blob.windows(b"/etc/passwd".len())
        .position(|w| w == b"/etc/passwd") {
        println!("\nFound '/etc/passwd' at position {}", pos);
        
        // Show context around it
        let context_start = pos.saturating_sub(50);
        let context_end = (pos + 100).min(metadata_blob.len());
        println!("Context ({}..{}):", context_start, context_end);
        
        let mut i = context_start;
        while i < context_end {
            let chunk_len = 32.min(context_end - i);
            println!("  {:04X}: {:02X?}", i, &metadata_blob[i..i+chunk_len]);
            i += chunk_len;
        }
    } else {
        println!("'/etc/passwd' not found in metadata blob");
    }
    
    // Try to parse as null-terminated paths with 8-byte offset/size
    println!("\nTrying to parse as null-terminated paths...");
    let mut offset = 0;
    let mut entry_count = 0;
    
    while offset < metadata_blob.len().min(10000) {  // Limit to first 10KB for inspection
        // Find next null
        let null_pos = metadata_blob[offset..].iter()
            .position(|&b| b == 0);
        
        if let Some(null_rel) = null_pos {
            let path_bytes = &metadata_blob[offset..offset+null_rel];
            if let Ok(path) = std::str::from_utf8(path_bytes) {
                if path.len() > 0 && !path.chars().any(|c| !c.is_ascii() || c.is_control()) {
                    // Likely a valid path
                    let next_data = offset + null_rel + 1;
                    
                    if next_data + 16 <= metadata_blob.len() {
                        let offset_bytes = &metadata_blob[next_data..next_data+8];
                        let size_bytes = &metadata_blob[next_data+8..next_data+16];
                        
                        let file_offset = u64::from_le_bytes(offset_bytes.try_into().unwrap());
                        let file_size = u64::from_le_bytes(size_bytes.try_into().unwrap());
                        
                        println!("  [{}] '{}' @ {} ({} bytes)", entry_count, path, file_offset, file_size);
                        
                        if path == "/etc/passwd" {
                            println!("    ^^^ FOUND! File offset={}, size={}", file_offset, file_size);
                        }
                        
                        entry_count += 1;
                        offset = next_data + 16;
                        continue;
                    }
                }
            }
        }
        
        offset += 1;
    }
    
    println!("\nTotal valid entries found in first 10KB: {}", entry_count);
}