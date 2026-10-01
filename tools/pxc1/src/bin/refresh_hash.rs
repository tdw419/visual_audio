//! One-off repair tool: recompute a PXC1 section's SHA-256 from its
//! current on-disk frames and update header.json, without needing a
//! running backend (whose own load path would refuse to start on a
//! hash mismatch in the first place).
use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!("Usage: {} <container_dir> <section_name>", args[0]);
        return ExitCode::FAILURE;
    }
    let encoder = pxc1::Encoder::new(&args[1]);
    match encoder.refresh_section_hash(&args[2]) {
        Ok(hash) => {
            println!("✓ Section '{}' sha256 refreshed to {}", args[2], hash);
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("✗ refresh_section_hash failed: {e}");
            ExitCode::FAILURE
        }
    }
}
