import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

decode_tile_new = """    fn decode_tile(&self, coord: TileCoord) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let tile_path = self.get_tile_path(coord)?;
        log::info!("Decoding tile: {}", tile_path.display());

        let mut decoder = geos_pixel::pdb::decoder::PdbDecoder::new(tile_path.to_str().unwrap()).map_err(|e| format!("{:?}", e))?;
        let table_data = decoder.decode_table("rootfs").map_err(|e| format!("{:?}", e))?;

        Ok(table_data)
    }"""

content = re.sub(r'    fn decode_tile\(&self, coord: TileCoord\) -> Result<Vec<u8>, Box<dyn std::error::Error>> \{.*?Ok\(bytes\)\n    \}', decode_tile_new, content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
