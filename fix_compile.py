import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

# fix get_tile_path
fix_path = """    fn decode_tile(&self, coord: TileCoord) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let filename = format!("rootfs.{}.{}.pdb.png", coord.tile_x, coord.tile_y);
        let tile_path = self.base_path.join(&filename);
        log::info!("Decoding tile: {}", tile_path.display());

        let mut decoder = geos_pixel::pdb::decoder::PdbDecoder::load_png(&tile_path).map_err(|e| format!("{:?}", e))?;
        let table_data = decoder.decode_table("rootfs").map_err(|e| format!("{:?}", e))?;

        Ok(table_data)
    }"""

content = re.sub(r'    fn decode_tile\(&self, coord: TileCoord\) -> Result<Vec<u8>, Box<dyn std::error::Error>> \{.*?Ok\(table_data\)\n    \}', fix_path, content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
