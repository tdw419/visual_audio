with open("systems/virtio_pixel_rs_v3/src/bootloader_uefi.rs", "r") as f:
    content = f.read()

# Fix the broken lines
content = content.replace("Read {} bytes from disk.\", payload.len());", "Read {} bytes from disk.\", image.len());")
content = content.replace("let payload = if payload.len() >= 8 &&", "let payload = if image.len() >= 8 &&")

with open("systems/virtio_pixel_rs_v3/src/bootloader_uefi.rs", "w") as f:
    f.write(content)
