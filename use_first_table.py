import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

content = content.replace('decoder.decode_table("rootfs")', 'decoder.decode_first_table()')

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
