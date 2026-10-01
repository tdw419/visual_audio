use pxc1::{Encoder, Section};
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::io::Read;
use std::path::PathBuf;

fn print_usage(program: &str) {
    eprintln!("PXC1 Encoder - Create Pixel Container Format v1 containers");
    eprintln!();
    eprintln!("Usage: {} <output_dir> <section_name> <file_path> [section_name file_path ...]", program);
    eprintln!();
    eprintln!("Examples:");
    eprintln!("  {} container rootfs ubuntu.raw gguf tinyllama.gguf", program);
    eprintln!("  {} container initramfs initramfs.gz", program);
    eprintln!();
    eprintln!("Output: <output_dir>/ containing:");
    eprintln!("  - header.json (metadata)");
    eprintln!("  - frame_00000.png (header frame)");
    eprintln!("  - frame_00001.png, frame_00002.png, ... (data frames)");
}

fn sha256_file(path: &PathBuf) -> Result<String, Box<dyn std::error::Error>> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];

    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }

    Ok(hex::encode(hasher.finalize()))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    if args.len() < 4 || args.len() % 2 != 0 {
        print_usage(&args[0]);
        std::process::exit(1);
    }

    let output_dir = PathBuf::from(&args[1]);
    fs::create_dir_all(&output_dir)?;

    eprintln!("=== PXC1 Encoder ===");
    eprintln!("Output directory: {}", output_dir.display());

    // Parse section definitions
    let mut sections = Vec::new();
    let mut next_frame = 1; // Frame 0 is reserved for header

    let mut i = 2;
    while i < args.len() {
        let name = &args[i];
        let file_path = PathBuf::from(&args[i + 1]);

        if !file_path.exists() {
            eprintln!("❌ File not found: {}", file_path.display());
            std::process::exit(1);
        }

        let byte_length = fs::metadata(&file_path)?.len() as usize;
        let sha256 = sha256_file(&file_path)?;

        eprintln!("Section '{}': {} bytes, SHA-256 {}", name, byte_length, sha256);

        sections.push(Section {
            name: name.clone(),
            start_frame: next_frame,
            byte_length,
            sha256,
            ..Default::default()
        });

        // Calculate how many frames this section needs
        let frames_needed = (byte_length + pxc1::BYTES_PER_FRAME - 1) / pxc1::BYTES_PER_FRAME;
        next_frame += frames_needed;

        i += 2;
    }

    // Create encoder and header
    let encoder = Encoder::new(&output_dir);
    eprintln!();
    eprintln!("[1] Creating header...");
    let header = encoder.create(sections)?;
    eprintln!("✓ Header created ({} total frames)", header.total_frames);

    // Write each section
    eprintln!();
    eprintln!("[2] Writing sections...");
    i = 2;
    while i < args.len() {
        let name = &args[i];
        let file_path = PathBuf::from(&args[i + 1]);

        eprint!("  Writing '{}'... ", name);

        let file = fs::File::open(&file_path)?;
        encoder.write_section_streaming(name, file)?;

        eprintln!("✓");

        i += 2;
    }

    eprintln!();
    eprintln!("=== Encoding Complete ===");
    eprintln!("Location: {}", output_dir.display());
    eprintln!("Total frames: {}", header.total_frames);
    eprintln!("Total size: ~{} MB", header.total_frames * pxc1::BYTES_PER_FRAME / 1_048_576);
    eprintln!();
    eprintln!("To verify:");
    eprintln!("  pxc1-verify {}", output_dir.display());

    Ok(())
}