import sys

content = open("systems/geos_pixel/src/decoder/pixel_decoder.rs").read()

idx = content.find("pub fn decode_pdb_table")
if idx != -1:
    content = content[:idx-4] + "}\n"
    open("systems/geos_pixel/src/decoder/pixel_decoder.rs", "w").write(content)
