// geos_pixel_nbd: Network Block Device server for PDB-tiled spatial storage
//
// Architecture:
// 1. Read path: LRU cache of decoded tiles (Vec<u8>), sector → tile mapping
// 2. Write path: Dirty tile tracking + periodic flush to PNG
// 3. Durability: NO durability guarantee (disposable test rootfs)
//    - Clean shutdown: flush dirty tiles
//    - Unclean crash: accept stale PDB tiles
//
// NBD Protocol Implementation:
// Raw TCP handshake implementation supporting modern NBD_OPT_GO negotiation

use byteorder::{BigEndian, ReadBytesExt, WriteBytesExt};
use log::{error, info, trace};
use std::collections::HashSet;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

// NBD Protocol Constants (https://github.com/NetworkBlockDevice/nbd/blob/master/doc/proto.md)
const NBD_MAGIC: u64 = 0x4e42444d41474943; // "NBDMAGIC"
const IHAVEOPT: u64 = 0x49484156454f5054; // "IHAVEOPT"
const NBD_OPT_MAGIC: u64 = 0x49484156454F5054;
const NBD_REP_MAGIC: u64 = 0x3e889045565a9;

const NBD_OPT_EXPORT_NAME: u32 = 1;
const NBD_OPT_ABORT: u32 = 2;
const NBD_OPT_GO: u32 = 7;

const NBD_REP_ACK: u32 = 1;
const NBD_REP_INFO: u32 = 3;
const NBD_REP_ERR_UNSUP: u32 = 1 | (1 << 31);

const NBD_INFO_EXPORT: u16 = 0;

const NBD_FLAG_HAS_FLAGS: u16 = 1 << 0;
const NBD_FLAG_SEND_FLUSH: u16 = 1 << 2;

const NBD_CMD_READ: u16 = 0;
const NBD_CMD_WRITE: u16 = 1;
const NBD_CMD_DISC: u16 = 2;
const NBD_CMD_FLUSH: u16 = 3;
const NBD_CMD_TRIM: u16 = 4;
const NBD_CMD_CACHE: u16 = 5;
const NBD_CMD_WRITE_ZEROES: u16 = 6;
const NBD_CMD_BLOCK_STATUS: u16 = 7;
const NBD_CMD_RESIZE: u16 = 8;
// Tile coordinate (x, y) in the grid
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Deserialize, serde::Serialize)]
pub struct TileCoord {
    pub tile_x: u32,
    pub tile_y: u32,
}

// Tile metadata from tiles.json
#[derive(Debug, Clone, serde::Deserialize)]
pub struct TileMetadata {
    pub coord: TileCoord,
    pub file_path: String,
    pub byte_offset: u64,
    pub byte_count: u64,
}

// Full TiledPdbHeader from tiles.json
#[derive(Debug, Clone, serde::Deserialize)]
pub struct TiledPdbHeader {
    pub magic: Vec<u8>,
    pub version: u32,
    pub table_count: u32,
    pub tile_config: TileConfig,
    pub tables: Vec<serde_json::Value>,
    pub tiles: std::collections::HashMap<String, Vec<TileMetadata>>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct TileConfig {
    pub tile_size: u32,
    pub logical_width: u32,
    pub logical_height: u32,
    pub tiles_per_row: u32,
    pub tiles_per_col: u32,
    pub total_tiles: u32,
}

// Spatial block server with LRU cache
pub struct SpatialBlockServer {
    tiles_dir: PathBuf,
    header: TiledPdbHeader,
    cache: Arc<Mutex<lru::LruCache<TileCoord, Vec<u8>>>>,
    dirty_tiles: Arc<Mutex<HashSet<TileCoord>>>,
    tile_size_bytes: usize,
    sector_size: u64,
}

impl SpatialBlockServer {
    pub fn new<P: AsRef<Path>>(tiles_dir: P) -> Result<Self, Box<dyn std::error::Error>> {
        let tiles_dir = tiles_dir.as_ref().to_path_buf();
        let header_path = tiles_dir.join("tiles.json");

        let header_content = std::fs::read_to_string(&header_path)?;
        let header: TiledPdbHeader = serde_json::from_str(&header_content)?;

        let tile_size_bytes =
            header.tile_config.tile_size as usize * (header.tile_config.tile_size as usize - 128) * 3;

        let cache_size = std::num::NonZeroUsize::new(20).unwrap();
        let cache = Arc::new(Mutex::new(lru::LruCache::new(cache_size)));

        let dirty_tiles = Arc::new(Mutex::new(HashSet::new()));

        info!(
            "Loaded {} tiles from {}",
            header.tiles["rootfs"].len(),
            tiles_dir.display()
        );
        info!("Tile size: {} bytes", tile_size_bytes);

        Ok(Self {
            tiles_dir,
            header,
            cache,
            dirty_tiles,
            tile_size_bytes,
            sector_size: 512,
        })
    }

    fn map_sector_to_tile(&self, sector: u64) -> Option<(TileCoord, usize)> {
        let byte_offset = sector * self.sector_size;

        if let Some(tiles) = self.header.tiles.get("rootfs") {
            for tile_meta in tiles {
                if byte_offset >= tile_meta.byte_offset
                    && byte_offset < tile_meta.byte_offset + tile_meta.byte_count
                {
                    let in_tile_offset = (byte_offset - tile_meta.byte_offset) as usize;
                    return Some((tile_meta.coord, in_tile_offset));
                }
            }
        }
        None
    }

    fn decode_tile(&self, coord: TileCoord) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let filename = format!("rootfs.{}.{}.pdb.png", coord.tile_x, coord.tile_y);
        let tile_path = self.tiles_dir.join(&filename);
        log::info!("Decoding tile: {}", tile_path.display());
        match geos_pixel::pdb::decoder::PdbDecoder::load_png(&tile_path) {
            Ok(decoder) => {
                let bbox = geos_pixel::pdb::BoundingBox { x_min: 0, x_max: 4095, y_min: 128, y_max: 4095 };
                match decoder.decode_raw_tile(bbox, self.tile_size_bytes) {
                    Ok(data) => Ok(data),
                    Err(e) => {
                        log::error!("Failed to decode {}: {:?}", tile_path.display(), e);
                        Ok(vec![0u8; self.tile_size_bytes])
                    }
                }
            }
            Err(e) => {
                log::error!("Failed to load {}: {:?}", tile_path.display(), e);
                Ok(vec![0u8; self.tile_size_bytes])
            }
        }
    }

    fn get_tile(&self, coord: TileCoord) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let mut cache = self.cache.lock().unwrap();

        if let Some(bytes) = cache.get(&coord) {
            return Ok(bytes.clone());
        }

        drop(cache);
        let bytes = self.decode_tile(coord)?;

        let mut cache = self.cache.lock().unwrap();
        cache.put(coord, bytes.clone());

        Ok(bytes)
    }

        pub fn read(&self, offset: u64, length: usize) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let start_sector = offset / self.sector_size;
        let end_sector = (offset + length as u64 + self.sector_size - 1) / self.sector_size;

        let mut result = Vec::with_capacity(length);
        
        let mut current_tile_coord = None;
        let mut current_tile_bytes = Vec::new();

        for sector in start_sector..end_sector {
            if let Some((coord, in_tile_offset)) = self.map_sector_to_tile(sector) {
                if current_tile_coord != Some(coord) {
                    current_tile_bytes = self.get_tile(coord)?;
                    current_tile_coord = Some(coord);
                }

                let sector_start = in_tile_offset;
                let sector_end = (in_tile_offset + 512).min(current_tile_bytes.len());

                if sector_start < current_tile_bytes.len() {
                    result.extend_from_slice(&current_tile_bytes[sector_start..sector_end]);
                }

                while result.len() % 512 != 0
                    && result.len() < (sector - start_sector + 1) as usize * 512
                {
                    result.push(0);
                }
            } else {
                result.resize(result.len() + 512, 0);
            }
        }

        let result_start = (offset % self.sector_size) as usize;
        let result_end = result_start + length.min(result.len() - result_start);
        Ok(result[result_start..result_end].to_vec())
    }

        pub fn write(&self, offset: u64, data: &[u8]) -> Result<(), Box<dyn std::error::Error>> {
        let start_sector = offset / self.sector_size;
        let data_sectors = (data.len() + 511) / 512;

        let mut current_tile_coord = None;
        let mut current_tile_bytes = Vec::new();
        let mut cache = self.cache.lock().unwrap();

        for i in 0..data_sectors {
            let sector = start_sector + i as u64;
            if let Some((coord, in_tile_offset)) = self.map_sector_to_tile(sector) {
                if current_tile_coord != Some(coord) {
                    if let Some(c) = current_tile_coord {
                        cache.put(c, current_tile_bytes);
                        self.dirty_tiles.lock().unwrap().insert(c);
                    }
                    if let Some(bytes) = cache.get(&coord) {
                        current_tile_bytes = bytes.clone();
                    } else {
                        drop(cache);
                        current_tile_bytes = self.decode_tile(coord)?;
                        cache = self.cache.lock().unwrap();
                    }
                    current_tile_coord = Some(coord);
                }

                let data_start = i * 512;
                let data_end = ((i + 1) * 512).min(data.len());
                let tile_start = in_tile_offset;
                let tile_end = (in_tile_offset + (data_end - data_start)).min(current_tile_bytes.len());

                if tile_start < current_tile_bytes.len() {
                    current_tile_bytes[tile_start..tile_end].copy_from_slice(&data[data_start..data_end]);
                }
            }
        }
        
        if let Some(c) = current_tile_coord {
            cache.put(c, current_tile_bytes);
            self.dirty_tiles.lock().unwrap().insert(c);
        }

        Ok(())
    }

    pub fn flush_dirty_tiles(&self) -> Result<(), Box<dyn std::error::Error>> {
        let mut dirty = self.dirty_tiles.lock().unwrap();

        if dirty.is_empty() {
            return Ok(());
        }

        info!("Flushing {} dirty tiles to disk...", dirty.len());

        for coord in dirty.drain() {
            let cache = self.cache.lock().unwrap();

            if let Some(tile_bytes) = cache.peek(&coord) {
                let tile_meta = self.header.tiles["rootfs"]
                    .iter()
                    .find(|t| t.coord == coord)
                    .ok_or("Tile not found in metadata")?;

                // Strip directory prefix for flush path
                let file_name = tile_meta
                    .file_path
                    .split('/')
                    .last()
                    .unwrap_or(&tile_meta.file_path);
                let tile_path = self.tiles_dir.join(file_name);
                let width = self.header.tile_config.tile_size as u32;
                let height = self.header.tile_config.tile_size as u32;

                let mut png_data: Vec<u8> = Vec::with_capacity(tile_bytes.len());
                for chunk in tile_bytes.chunks(3) {
                    png_data.extend_from_slice(chunk);
                    if chunk.len() < 3 {
                        png_data.extend(vec![0; 3 - chunk.len()]);
                    }
                }

                let file = std::fs::File::create(&tile_path)?;
                let mut encoder = png::Encoder::new(file, width, height);
                encoder.set_color(png::ColorType::Rgb);
                encoder.set_depth(png::BitDepth::Eight);
                let mut writer = encoder.write_header()?;
                writer.write_image_data(&png_data)?;

                info!("Flushed tile: {}", tile_path.display());
            }
        }

        info!("Flush complete");
        Ok(())
    }

    pub fn size(&self) -> u64 {
        if let Some(tiles) = self.header.tiles.get("rootfs") {
            if let Some(last_tile) = tiles.last() {
                return last_tile.byte_offset + last_tile.byte_count;
            }
        }
        0
    }
}

// NBD Fixed-Newstyle Handshake
fn nbd_handshake<S: std::io::Read + std::io::Write>(
    stream: &mut S,
    export_size: u64,
    flags: u16,
) -> Result<(), Box<dyn std::error::Error>> {
    log::info!("Starting raw NBD handshake");

    stream.write_u64::<byteorder::BigEndian>(NBD_MAGIC)?;
    stream.write_u64::<byteorder::BigEndian>(IHAVEOPT)?;

    let handshake_flags: u16 = (1 << 0) | (1 << 1); // FIXED_NEWSTYLE | NO_ZEROES
    stream.write_u16::<byteorder::BigEndian>(handshake_flags)?;

    let client_flags = stream.read_u32::<byteorder::BigEndian>()?;
    log::info!("Client flags: 0x{:x}", client_flags);
    
    let no_zeroes = (client_flags & (1 << 1)) != 0;

    loop {
        let magic = stream.read_u64::<byteorder::BigEndian>()?;
        if magic != 0x49484156454F5054 {
            return Err(format!("Invalid option magic: 0x{:x}", magic).into());
        }

        let opt = stream.read_u32::<byteorder::BigEndian>()?;
        let opt_len = stream.read_u32::<byteorder::BigEndian>()?;

        log::info!("Received NBD_OPT_{} (length {})", opt, opt_len);

        match opt {
            7 => { // NBD_OPT_GO
                let mut name_buf = vec![0u8; opt_len as usize];
                stream.read_exact(&mut name_buf)?;
                let name = String::from_utf8_lossy(&name_buf).trim_end_matches('\0').to_string();
                log::info!("Client requested export via GO: '{}'", name);

                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(3)?; // NBD_REP_INFO
                stream.write_u32::<byteorder::BigEndian>(12)?; 
                stream.write_u16::<byteorder::BigEndian>(0)?; // NBD_INFO_EXPORT
                stream.write_u64::<byteorder::BigEndian>(export_size)?;
                stream.write_u16::<byteorder::BigEndian>(flags)?;

                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(1)?; // NBD_REP_ACK
                stream.write_u32::<byteorder::BigEndian>(0)?; 

                log::info!("Sent NBD_OPT_GO ACK with export size {}", export_size);
                break;
            }
            1 => { // NBD_OPT_EXPORT_NAME
                let mut export_name = vec![0u8; opt_len as usize];
                stream.read_exact(&mut export_name)?;
                log::info!("Client sent NBD_OPT_EXPORT_NAME (legacy): '{}'", String::from_utf8_lossy(&export_name));

                stream.write_u64::<byteorder::BigEndian>(export_size)?;
                stream.write_u16::<byteorder::BigEndian>(flags)?;
                
                if !no_zeroes {
                    stream.write_all(&[0u8; 124])?;
                }
                
                log::info!("Sent NBD_OPT_EXPORT_NAME response with export size {}", export_size);
                break;
            }
            2 => { // NBD_OPT_ABORT
                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(1)?; // NBD_REP_ACK
                stream.write_u32::<byteorder::BigEndian>(0)?;
                return Err("Client aborted connection".into());
            }
            _ => {
                if opt_len > 0 {
                    let mut discard = vec![0u8; opt_len as usize];
                    stream.read_exact(&mut discard)?;
                }
                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(1 | (1 << 31))?; // NBD_REP_ERR_UNSUP
                stream.write_u32::<byteorder::BigEndian>(0)?;
                log::info!("Rejected unsupported option NBD_OPT_{}", opt);
            }
        }
    }

    log::info!("NBD handshake complete");
    Ok(())
}

// NBD Transmission Phase
fn nbd_transmission<S: Read + Write>(
    stream: &mut S,
    server: &SpatialBlockServer,
) -> Result<(), Box<dyn std::error::Error>> {
    info!("Starting NBD transmission phase");

    loop {
        // Read request header (magic: u32, type: u16, handle: u8[8], from: u64, len: u32)
        let magic = stream.read_u32::<BigEndian>()?;

        // Magic can be either 0x25609513 (request) or 0x6041b937 (structured reply opts)
        if magic == 0x6041b937 {
            // Structured reply negotiation - we don't support this
            info!("Structured reply negotiation requested (unsupported)");
            let opts = stream.read_u32::<BigEndian>()?;
            info!("Structured reply opts: 0x{:x}", opts);
            continue;
        }


        if magic != 0x25609513 {
            return Err(format!("Invalid request magic: 0x{:x}", magic).into());
        }

        let cmd_flags = stream.read_u16::<BigEndian>()?;
        let cmd = stream.read_u16::<BigEndian>()?;
        let mut handle = [0u8; 8];
        stream.read_exact(&mut handle)?;
        let offset = stream.read_u64::<BigEndian>()?;
        let length = stream.read_u32::<BigEndian>()?;

        trace!(
            "Request: cmd={}, flags={}, handle={:?}, offset={}, len={}",
            cmd,
            cmd_flags,
            handle,
            offset,
            length
        );


        match cmd {
            NBD_CMD_READ => {
                let data = server.read(offset, length as usize)?;
                stream.write_u32::<BigEndian>(0x67446698)?; // Simple reply magic
                stream.write_u32::<BigEndian>(0)?; // Error code (0 = no error)
                stream.write_all(&handle)?;
                stream.write_all(&data)?;
            }
            NBD_CMD_WRITE => {
                let mut data = vec![0u8; length as usize];
                stream.read_exact(&mut data)?;
                server.write(offset, &data)?;
                stream.write_u32::<BigEndian>(0x67446698)?;
                stream.write_u32::<BigEndian>(0)?;
                stream.write_all(&handle)?;
            }
            NBD_CMD_FLUSH => {
                // Flush dirty tiles to disk
                match server.flush_dirty_tiles() {
                    Ok(_) => {
                        stream.write_u32::<BigEndian>(0x67446698)?;
                        stream.write_u32::<BigEndian>(0)?;
                        stream.write_all(&handle)?;
                    }
                    Err(e) => {
                        error!("Flush failed: {}", e);
                        stream.write_u32::<BigEndian>(0x67446698)?;
                        stream.write_u32::<BigEndian>(1)?; // EIO
                        stream.write_all(&handle)?;
                    }
                }
            }
            NBD_CMD_DISC => {
                info!("Client requested disconnect");
                return Ok(());
            }
            NBD_CMD_TRIM | NBD_CMD_CACHE | NBD_CMD_WRITE_ZEROES | NBD_CMD_BLOCK_STATUS
            | NBD_CMD_RESIZE => {
                // Return unsupported error
                stream.write_u32::<BigEndian>(0x67446698)?;
                stream.write_u32::<BigEndian>(1)?; // EIO (unsupported operation)
                stream.write_all(&handle)?;
                info!("Ignored unsupported command NBD_CMD_{}", cmd);
            }
            _ => {
                error!("Unknown command: {}", cmd);
                stream.write_u32::<BigEndian>(0x67446698)?;
                stream.write_u32::<BigEndian>(1)?;
                stream.write_all(&handle)?;
            }
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();

    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "Usage: {} <tiles_dir> <socket_path> [flush_interval_seconds]",
            args[0]
        );
        std::process::exit(1);
    }

    let tiles_dir = &args[1];
    let socket_path = &args[2];

    info!("Starting geos_pixel_nbd server");
    info!("Tiles dir: {}", tiles_dir);

    let server = SpatialBlockServer::new(tiles_dir)?;
    let server_arc = Arc::new(server);
    let export_size = server_arc.size();

    info!(
        "Export size: {} bytes ({} GB)",
        export_size,
        export_size / (1024 * 1024 * 1024)
    );

    let flush_server = Arc::clone(&server_arc);
    let flush_interval = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(30);
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(flush_interval));
        if let Err(e) = flush_server.flush_dirty_tiles() {
            error!("Periodic flush failed: {}", e);
        }
    });

    // Set up SIGTERM handler for clean shutdown
    let flush_handler = Arc::clone(&server_arc);
    ctrlc::set_handler(move || {
        info!("Received shutdown signal. Flushing dirty tiles...");
        if let Err(e) = flush_handler.flush_dirty_tiles() {
            error!("Shutdown flush failed: {}", e);
        }
        std::process::exit(0);
    })
    .expect("Error setting Ctrl-C handler");

    let listener = TcpListener::bind(socket_path)?;
    info!("Listening for NBD connections on {}", socket_path);

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                info!("Accepted NBD connection");

                // Export flags: we support FLUSH but not READ_ONLY
                let flags = NBD_FLAG_HAS_FLAGS | NBD_FLAG_SEND_FLUSH;
                let server_arc = Arc::clone(&server_arc);

                // Handle each client in its own thread so a stalled/hung client
                // cannot block the accept loop and starve other clients (e.g. QEMU).
                std::thread::spawn(move || {
                    let mut stream = stream;
                    // Perform handshake
                    match nbd_handshake(&mut stream, export_size, flags) {
                        Ok(_) => {
                            info!("Handshake successful, entering transmission phase");

                            // Handle transmission phase
                            match nbd_transmission(&mut stream, &server_arc) {
                                Ok(_) => {
                                    info!("Transmission phase completed normally");
                                }
                                Err(e) => {
                                    error!("Transmission phase error: {}", e);
                                }
                            }

                            info!("Client disconnected. Flushing dirty tiles.");
                            if let Err(e) = server_arc.flush_dirty_tiles() {
                                error!("Post-disconnect flush failed: {}", e);
                            }
                        }
                        Err(e) => {
                            error!("NBD handshake failed: {}", e);
                        }
                    }
                });
            }
            Err(e) => {
                error!("Connection failed: {}", e);
            }
        }
    }

    Ok(())
}