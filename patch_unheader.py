import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

read_fix = """                let sector_start = in_tile_offset;
                let sector_end = (in_tile_offset + 512).min(current_tile_bytes.len());"""
content = re.sub(r'                let tile_header_offset = 128 \* 4096 \* 3;\n                let sector_start = in_tile_offset \+ tile_header_offset;\n                let sector_end = \(in_tile_offset \+ tile_header_offset \+ 512\)\.min\(current_tile_bytes\.len\(\)\);', read_fix, content)

write_fix = """                let tile_start = in_tile_offset;
                let tile_end = (in_tile_offset + (data_end - data_start)).min(current_tile_bytes.len());"""
content = re.sub(r'                let tile_header_offset = 128 \* 4096 \* 3;\n                let tile_start = in_tile_offset \+ tile_header_offset;\n                let tile_end = \(in_tile_offset \+ tile_header_offset \+ \(data_end - data_start\)\)\.min\(current_tile_bytes\.len\(\)\);', write_fix, content)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
