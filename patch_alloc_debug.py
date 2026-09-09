import os

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

code = code.replace(
    'let _ = uefi::boot::allocate_pages(',
    'let res = uefi::boot::allocate_pages('
)

code = code.replace(
    ');\n                let dst',
    ');\n                uefi::println!("AllocatePages result: {:?}", res);\n                let dst'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
