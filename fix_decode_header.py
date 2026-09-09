import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

fix_str = """        let mut decoder = geos_pixel::pdb::decoder::PdbDecoder::load_png(&tile_path).map_err(|e| format!("{:?}", e))?;
        decoder.decode_header().map_err(|e| format!("{:?}", e))?;
        let table_data = decoder.decode_first_table().map_err(|e| format!("{:?}", e))?;"""

content = re.sub(r'        let mut decoder = geos_pixel::pdb::decoder::PdbDecoder::load_png\(&tile_path\)\.map_err\(\|e\| format\!\("\{:\?\}", e\)\)\?;\n        let table_data = decoder\.decode_first_table\(\)\.map_err\(\|e\| format\!\("\{:\?\}", e\)\)\?;', fix_str, content)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
