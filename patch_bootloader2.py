import os

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

code = code.replace('allocated_addr,', 'allocated_addr.as_ptr() as u64,')
code = code.replace('allocated_addr +', '(allocated_addr.as_ptr() as u64) +')
code = code.replace('allocated_addr as *mut u8', 'allocated_addr.as_ptr()')

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
