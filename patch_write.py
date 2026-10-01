import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

write_code = """    pub fn write(&self, offset: u64, data: &[u8]) -> Result<(), Box<dyn std::error::Error>> {
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
    }"""

content = re.sub(r'pub fn write\(&self, offset: u64, data: &\[u8\]\).*?Ok\(\(\)\)\n    \}', write_code, content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
