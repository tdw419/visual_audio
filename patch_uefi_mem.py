import os

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

import re

new_code = """
            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            let paddr = seg.p_paddr as usize;
            unsafe {
                let _ = uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::Address(paddr),
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                );
            }
            
            unsafe {
"""

code = code.replace("unsafe {", new_code, 1) # Only replace the first one inside the loop? Wait.
# Let's be more precise:
code = code.replace(
    "            unsafe {\n                let dst = seg.p_paddr as *mut u8;",
    """            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            unsafe {
                let _ = uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::Address(seg.p_paddr as usize),
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                );
                let dst = seg.p_paddr as *mut u8;"""
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
