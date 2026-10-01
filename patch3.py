import re
with open("systems/virtio_pixel_rs_v3/src/bootloader_uefi.rs", "r") as f:
    content = f.read()

content = content.replace("let mut uefi_block_device = UefiBlockDevice::new(&mut block_io);", "let bs_size = block_io.media().block_size() as u64;\n                let mut uefi_block_device = UefiBlockDevice::new(&mut block_io);")
content = content.replace("block_io.media().block_size() as u64", "bs_size")

with open("systems/virtio_pixel_rs_v3/src/bootloader_uefi.rs", "w") as f:
    f.write(content)
