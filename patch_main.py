with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

import re

# We want to replace the current main() with the new one
new_main = """
fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();

    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: {} <tiles_dir> <socket_path> [flush_interval_seconds]", args[0]);
        std::process::exit(1);
    }

    let tiles_dir = &args[1];
    let socket_path = &args[2];
    
    info!("Starting geos_pixel_nbd server");
    info!("Tiles dir: {}", tiles_dir);
    
    let server = SpatialBlockServer::new(tiles_dir)?;
    let server_arc = Arc::new(server);
    let export_size = server_arc.size();
    
    info!("Export size: {} bytes ({} GB)", export_size, export_size / (1024 * 1024 * 1024));
    
    // Start flush thread
    let flush_server = Arc::clone(&server_arc);
    let flush_interval = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(30);
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(std::time::Duration::from_secs(flush_interval));
            if let Err(e) = flush_server.flush_dirty_tiles() {
                error!("Periodic flush failed: {}", e);
            }
        }
    });

    let listener = std::net::TcpListener::bind(socket_path)?;
    info!("Listening for NBD connections on {}", socket_path);
    
    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                info!("Accepted NBD connection");
                
                let backend = NbdBackend::new(Arc::clone(&server_arc));
                
                let export = nbd::server::Export {
                    size: export_size,
                    readonly: false,
                    ..Default::default()
                };
                
                if let Err(e) = nbd::server::handshake(&mut stream, &export) {
                    error!("NBD handshake failed: {}", e);
                    continue;
                }
                
                if let Err(e) = nbd::server::transmission(&mut stream, backend) {
                    error!("NBD transmission error: {}", e);
                }
                
                info!("NBD client disconnected. Flushing tiles.");
                let _ = server_arc.flush_dirty_tiles();
            }
            Err(e) => {
                error!("Connection failed: {}", e);
            }
        }
    }
    
    Ok(())
}
"""

content = re.sub(r'fn main\(\) -> Result<\(\), Box<dyn std::error::Error>> \{.*$', new_main, content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
