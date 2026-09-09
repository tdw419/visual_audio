import os

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

import re

# Find the allocation block and replace it
alloc_block = """
            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            let paddr = seg.p_paddr as usize;
            unsafe {
                let res = uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::Address(seg.p_paddr),
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                );
            }
"""

new_alloc_block = """
            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            let allocated_addr = unsafe {
                uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::AnyPages,
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                ).expect("Failed to allocate memory for ELF segment")
            };
            uefi::println!("Allocated {} pages at {:#x} (requested {:#x})", num_pages, allocated_addr, seg.p_paddr);
"""

code = code.replace(alloc_block, new_alloc_block)
code = code.replace("let dst = seg.p_paddr as *mut u8;", "let dst = allocated_addr as *mut u8;")

# We need to adjust entry point!
# But wait, entry point is handled outside the loop.
# Let's adjust it globally. Or just pass allocated_addr to handoff!
code = code.replace("x86_64_handoff(header.e_entry, stack_ptr)", "x86_64_handoff(allocated_addr + (header.e_entry - seg.p_paddr), stack_ptr)")

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
