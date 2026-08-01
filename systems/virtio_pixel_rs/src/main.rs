use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use anyhow::{anyhow, Result};
use env_logger::Env;
use log::info;

use virtio_pixel_rs::{SpatialMkvExtractor, backend::VirtioPixelServer};

const DEFAULT_SOCKET_PATH: &str = "/tmp/virtio-pixel-rs.sock";
const DEFAULT_MKV_PATH: &str = "visual_audio.mkv";

fn main() -> Result<()> {
    env_logger::Builder::from_env(Env::default().default_filter_or("info")).init();

    info!("VirtIO Pixel vhost-user-blk backend - Rust implementation");
    info!("============================================================");

    // Parse command line args: mkv_path [socket_path]
    let args: Vec<String> = std::env::args().collect();

    let mkv_path = if args.len() >= 2 {
        PathBuf::from(&args[1])
    } else {
        PathBuf::from(DEFAULT_MKV_PATH)
    };

    let socket_path = if args.len() >= 3 {
        PathBuf::from(&args[2])
    } else {
        PathBuf::from(DEFAULT_SOCKET_PATH)
    };

    if !mkv_path.exists() {
        eprintln!("ERROR: MKV not found: {}", mkv_path.display());
        eprintln!("Usage: {} <mkv_path> [socket_path]", args[0]);
        return Err(anyhow!("MKV file not found: {}", mkv_path.display()));
    }

    info!("Loading spatial extractor from: {}", mkv_path.display());
    info!("Socket path: {}", socket_path.display());

    let entry_name = mkv_path.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("disk.pixel");

    let extractor = SpatialMkvExtractor::new(&mkv_path, entry_name)?;

    info!("Starting vhost-user backend, waiting for QEMU connection...");

    let extractor = Arc::new(Mutex::new(extractor));

    let mut server = VirtioPixelServer::new(extractor, socket_path);

    server.run()
}