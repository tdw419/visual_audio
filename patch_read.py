import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

read_code = """    pub fn read(&self, offset: u64, length: usize) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
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
    }"""

content = re.sub(r'pub fn read\(&self, offset: u64, length: usize\).*?Ok\(result\[result_start\.\.result_end\]\.to_vec\(\)\)\n    \}', read_code, content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
