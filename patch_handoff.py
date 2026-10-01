import os

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

import re

# In the loop, save the offset
new_alloc = """
            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            let allocated_addr = unsafe {
                uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::AnyPages,
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                ).expect("Failed to allocate memory for ELF segment")
            };
            uefi::println!("Allocated {} pages at {:#x} (requested {:#x})", num_pages, allocated_addr, seg.p_paddr);
            entry_offset = allocated_addr as u64 - seg.p_paddr;
            let dst = allocated_addr as *mut u8;
"""

# Let's write the whole file properly
