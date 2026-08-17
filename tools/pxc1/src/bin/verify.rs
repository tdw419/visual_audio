use pxc1::Decoder;
use std::env;
use std::path::PathBuf;

fn print_usage(program: &str) {
    eprintln!("PXC1 Verify - Check SHA-256 hashes of all sections");
    eprintln!();
    eprintln!("Usage: {} <container_dir>", program);
    eprintln!();
    eprintln!("Example:");
    eprintln!("  {} container", program);
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

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