import os
with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

code = code.replace(
    'let Ok(mut block_io) = boot::open_protocol_exclusive::<BlockIO>(*handle) else {',
    'let Ok(mut block_io) = boot::open_protocol_exclusive::<BlockIO>(*handle) else {\n            uefi::println!("Failed to open BlockIO exclusively for a handle.");'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
