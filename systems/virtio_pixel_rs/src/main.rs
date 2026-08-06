use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::io::Write;

use anyhow::{anyhow, Result};
use env_logger::Env;
use log::{info, error};

use virtio_pixel_rs::{SpatialMkvExtractor, backend::VirtioPixelServer};

const DEFAULT_SOCKET_PATH: &str = "/tmp/virtio-pixel-rs.sock";
const DEFAULT_MKV_PATH: &str = "visual_audio.mkv";

#[tokio::main]
async fn main() -> Result<()> {
    env_logger::Builder::from_env(Env::default().default_filter_or("info")).init();

    info!("VirtIO Pixel vhost-user-blk backend - Rust implementation");
    info!("============================================================");

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
        return Err(anyhow!("MKV file not found: {}", mkv_path.display()));
    }

    let entry_name = mkv_path.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("disk.pixel");

    let extractor = SpatialMkvExtractor::new(&mkv_path, entry_name)?;
    let extractor = Arc::new(Mutex::new(extractor));

    // Start HTTP daemon for VCC validation
    let vcc_extractor = Arc::clone(&extractor);
    tokio::spawn(async move {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:8769").await.unwrap();
        info!("VCC HTTP Daemon listening on 127.0.0.1:8769");
        loop {
            if let Ok((mut stream, _)) = listener.accept().await {
                let mut buf = [0; 1024];
                use tokio::io::AsyncReadExt;
                if let Ok(n) = stream.read(&mut buf).await {
                    let request = String::from_utf8_lossy(&buf[..n]);
                    if request.starts_with("GET /peek") {
                        // Extract addr and size
                        let mut addr = 0usize;
                        let mut size = 16usize;
                        
                        if let Some(query) = request.split(' ').nth(1) {
                            if let Some(idx) = query.find('?') {
                                let qs = &query[idx+1..];
                                for pair in qs.split('&') {
                                    let mut kv = pair.split('=');
                                    if let (Some(k), Some(v)) = (kv.next(), kv.next()) {
                                        if k == "addr" {
                                            if v.starts_with("0x") {
                                                addr = usize::from_str_radix(&v[2..], 16).unwrap_or(0);
                                            } else {
                                                addr = v.parse().unwrap_or(0);
                                            }
                                        } else if k == "size" {
                                            size = v.parse().unwrap_or(16);
                                        }
                                    }
                                }
                            }
                        }
                        
                        let bytes_to_read = size * 4;
                        let mut result_bytes = Vec::new();
                        
                        {
                            let mut ext = vcc_extractor.lock().unwrap();
                            if let Ok(data) = ext.extract_bytes(addr, bytes_to_read) {
                                result_bytes = data;
                            }
                        }
                        
                        // Pad if necessary
                        result_bytes.resize(bytes_to_read, 0);
                        
                        let mut hex_resp = String::new();
                        for chunk in result_bytes.chunks(4) {
                            let mut w = [0u8; 4];
                            w[..chunk.len()].copy_from_slice(chunk);
                            let val = u32::from_le_bytes(w);
                            hex_resp.push_str(&format!("{:08X} ", val));
                        }
                        
                        let response = format!(
                            "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {}\r\n\r\n{}",
                            hex_resp.len(),
                            hex_resp
                        );
                        
                        use tokio::io::AsyncWriteExt;
                        let _ = stream.write_all(response.as_bytes()).await;
                    }
                }
            }
        }
    });

    info!("Starting vhost-user backend, waiting for QEMU connection...");
    let mut server = VirtioPixelServer::new(extractor, socket_path);

    // Using unblock to run synchronous server.run() in a background thread since we're in tokio::main
    tokio::task::spawn_blocking(move || {
        server.run()
    }).await??;
    
    Ok(())
}
