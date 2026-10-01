use pxc1::{Decoder, Encoder};
use std::env;
use std::path::PathBuf;

fn print_usage(program: &str) {
    eprintln!("PXC1 Verify - Check SHA-256 hashes of all sections");
    eprintln!();
    eprintln!("Usage: {} <container_dir>", program);
    eprintln!("       {} --backfill-frame-hashes <container_dir> [section_name ...]", program);
    eprintln!();
    eprintln!("Example:");
    eprintln!("  {} container", program);
    eprintln!("  {} --backfill-frame-hashes container rootfs", program);
    eprintln!();
    eprintln!("--backfill-frame-hashes accelerates a container written before spec §6a");
    eprintln!("existed (see docs/PIXEL_CONTAINER_SPEC_V1.md): one full read per named");
    eprintln!("section (same cost as a normal verify) to populate frame_hashes, after");
    eprintln!("which future single-frame patches (COW journal compaction) no longer");
    eprintln!("need one. Omit section names to backfill every section in the container.");
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.len() >= 2 && args[1] == "--backfill-frame-hashes" {
        if args.len() < 3 {
            print_usage(&args[0]);
            std::process::exit(1);
        }
        let container_dir = PathBuf::from(&args[2]);
        let decoder = Decoder::open(&container_dir)?;
        let section_names: Vec<String> = if args.len() > 3 {
            args[3..].to_vec()
        } else {
            decoder.header().sections.iter().map(|s| s.name.clone()).collect()
        };
        drop(decoder);

        let encoder = Encoder::new(&container_dir);
        for name in &section_names {
            eprint!("Backfilling '{}'... ", name);
            match encoder.refresh_section_hash(name) {
                Ok(hash) => eprintln!("done, sha256 {}", &hash[..16]),
                Err(e) => {
                    eprintln!("FAILED: {}", e);
                    std::process::exit(1);
                }
            }
        }
        eprintln!("=== Backfill complete: {} section(s) accelerated ===", section_names.len());
        return Ok(());
    }

    if args.len() < 2 {
        print_usage(&args[0]);
        std::process::exit(1);
    }

    let container_dir = PathBuf::from(&args[1]);

    eprintln!("=== PXC1 Verify ===");
    eprintln!("Container: {}", container_dir.display());

    // Open decoder
    eprintln!("[1] Loading container...");
    let mut decoder = Decoder::open(&container_dir)?;

    let header = decoder.header();
    eprintln!("✓ Format: {}", header.format);
    eprintln!("✓ Frame size: {}x{}", header.frame_size, header.frame_size);
    eprintln!("✓ Bytes per frame: {}", header.bytes_per_frame);
    eprintln!("✓ Total frames: {}", header.total_frames);
    eprintln!("✓ Sections: {}", header.sections.len());

    let sections = header.sections.clone();

    // Verify each section
    eprintln!();
    eprintln!("[2] Verifying section hashes...");
    let mut all_ok = true;

    for section in &sections {
        eprint!("  '{}': {} bytes... ", section.name, section.byte_length);

        match decoder.read_section(&section.name) {
            Ok(_) => {
                eprintln!("✓ SHA-256: {}", &section.sha256[..16]);
            }
            Err(e) => {
                eprintln!("❌ {}", e);
                all_ok = false;
            }
        }
    }

    eprintln!();
    if all_ok {
        eprintln!("=== All Verifications Passed ===");
        Ok(())
    } else {
        eprintln!("=== VERIFICATION FAILED ===");
        std::process::exit(1);
    }
}