import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

# Add std::io traits
imports = "use std::io::{Read, Write, Seek, SeekFrom, Error, ErrorKind};\nuse std::net::TcpListener;\nuse nbd::server::{transmission, handshake, Export};"
content = content.replace("use std::sync::{Arc, Mutex};", "use std::sync::{Arc, Mutex};\n" + imports)

# Add NbdBackend struct
backend_code = """
pub struct NbdBackend {
    server: Arc<SpatialBlockServer>,
    cursor: u64,
}

impl NbdBackend {
    pub fn new(server: Arc<SpatialBlockServer>) -> Self {
        Self { server, cursor: 0 }
    }
}

impl Read for NbdBackend {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let size = self.server.size();
        if self.cursor >= size {
            return Ok(0);
        }
        let max_len = (size - self.cursor) as usize;
        let read_len = buf.len().min(max_len);
        
        match self.server.read(self.cursor, read_len) {
            Ok(data) => {
                buf[..data.len()].copy_from_slice(&data);
                self.cursor += data.len() as u64;
                Ok(data.len())
            }
            Err(e) => Err(Error::new(ErrorKind::Other, e.to_string())),
        }
    }
}

impl Write for NbdBackend {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        match self.server.write(self.cursor, buf) {
            Ok(_) => {
                self.cursor += buf.len() as u64;
                Ok(buf.len())
            }
            Err(e) => Err(Error::new(ErrorKind::Other, e.to_string())),
        }
    }

    fn flush(&mut self) -> std::io::Result<()> {
        match self.server.flush_dirty_tiles() {
            Ok(_) => Ok(()),
            Err(e) => Err(Error::new(ErrorKind::Other, e.to_string())),
        }
    }
}

impl Seek for NbdBackend {
    fn seek(&mut self, pos: SeekFrom) -> std::io::Result<u64> {
        let size = self.server.size() as i64;
        let new_pos = match pos {
            SeekFrom::Start(p) => p as i64,
            SeekFrom::End(p) => size + p,
            SeekFrom::Current(p) => self.cursor as i64 + p,
        };
        
        if new_pos < 0 {
            return Err(Error::new(ErrorKind::InvalidInput, "Seek before start"));
        }
        
        self.cursor = new_pos as u64;
        Ok(self.cursor)
    }
}
"""
content = content.replace("fn main() -> Result<(), Box<dyn std::error::Error>> {", backend_code + "\nfn main() -> Result<(), Box<dyn std::error::Error>> {")

# Replace main body
main_replacement = """
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

    let listener = TcpListener::bind(socket_path)?;
    info!("Listening for NBD connections on {}", socket_path);
    
    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                info!("Accepted NBD connection");
                
                let backend = NbdBackend::new(Arc::clone(&server_arc));
                
                let export = Export {
                    size: export_size,
                    readonly: false,
                    ..Default::default()
                };
                
                if let Err(e) = handshake(&mut stream, &export) {
                    error!("NBD handshake failed: {}", e);
                    continue;
                }
                
                if let Err(e) = transmission(&mut stream, backend) {
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
"""

content = re.sub(r'    let _socket_path = &args\[2\];.*Ok\(\)\)\n\}', main_replacement + "\n}", content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
