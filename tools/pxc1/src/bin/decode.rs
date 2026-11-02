use pxc1::Decoder;
use std::env;
use std::fs;
use std::path::PathBuf;

fn print_usage(program: &str) {
    eprintln!("PXC1 Decoder - Extract sections from PXC1 containers");
    eprintln!();
    eprintln!("Usage: {} <container_dir> <section_name> [output_file]", program);
    eprintln!();
    eprintln!("Examples:");
    eprintln!("  {} container gguf extracted.gguf", program);
    eprintln!("  {} container rootfs /dev/sda", program);
    eprintln!();
    eprintln!("If output_file is omitted, data is printed to stdout (binary).");
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.len() < 3 {
        print_usage(&args[0]);
        std::process::exit(1);
    }

    let container_dir = PathBuf::from(&args[1]);
    let section_name = &args[2];
    let output_file = args.get(3).map(PathBuf::from);

    eprintln!("=== PXC1 Decoder ===");
    eprintln!("Container: {}", container_dir.display());
    eprintln!("Section: {}", section_name);

    // Open decoder
    eprintln!("[1] Loading container...");
    let mut decoder = Decoder::open(&container_dir)?;

    // Verify header
    let header = decoder.header();
    eprintln!("✓ Format: {}", header.format);
    eprintln!("✓ Frame size: {}x{}", header.frame_size, header.frame_size);
    eprintln!("✓ Total frames: {}", header.total_frames);
    eprintln!("✓ Sections: {}", header.sections.len());

    // Find section
    eprintln!();
    eprintln!("[2] Reading section '{}'...", section_name);
    let data = decoder.read_section(section_name)?;

    eprintln!("✓ Extracted {} bytes", data.len());

    // Write output
    eprintln!();
    if let Some(output_path) = output_file {
        eprintln!("[3] Writing to {}...", output_path.display());
        fs::write(&output_path, data)?;
        eprintln!("✓ Done");
    } else {
        eprintln!("[3] Writing to stdout...");
        use std::io::{self, Write};
        let stdout = io::stdout();
        let mut handle = stdout.lock();
        handle.write_all(&data)?;
    }

    eprintln!();
    eprintln!("=== Decoding Complete ===");

    Ok(())
}