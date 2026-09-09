import re
with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

content = content.replace("|_name| Ok(export)", "|name| { info!(\"Requested export: '{}'\", name); Ok(export) }")
with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
