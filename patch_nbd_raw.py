import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

fix_str = """        let decoder = geos_pixel::pdb::decoder::PdbDecoder::load_png(&tile_path).map_err(|e| format!("{:?}", e))?;
        let bbox = geos_pixel::pdb::BoundingBox { x_min: 0, x_max: 4095, y_min: 128, y_max: 4095 };
        let table_data = decoder.decode_raw_tile(bbox, self.tile_size_bytes).map_err(|e| format!("{:?}", e))?;"""

content = re.sub(r'        let mut decoder = geos_pixel::pdb::decoder::PdbDecoder::load_png.*?let table_data = decoder\.decode_first_table\(\)\.map_err\(\|e\| format\!\("\{:\?\}", e\)\)\?;', fix_str, content, flags=re.DOTALL)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
