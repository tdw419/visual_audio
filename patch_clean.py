import os
import re

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

# Make sure we start from a clean state!
code = re.sub(r'let mut runtime_entry.*?\n', '', code)

code = code.replace(
    '        uefi::println!("ELF64 entry: {:#x}, e_machine: {:#x}", header.e_entry, header.e_machine);',
    '        uefi::println!("ELF64 entry: {:#x}, e_machine: {:#x}", header.e_entry, header.e_machine);\n        let mut runtime_entry = header.e_entry;'
)

alloc_str = """
            unsafe {
                let dst = seg.p_paddr as *mut u8;"""

new_alloc_str = """
            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            let allocated_addr = unsafe {
                uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::AnyPages,
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                ).expect("Failed to allocate memory for ELF segment")
            };
            uefi::println!("Allocated {} pages at {:#x} (requested {:#x})", num_pages, allocated_addr.as_ptr() as u64, seg.p_paddr);
            runtime_entry = (allocated_addr.as_ptr() as u64) + (header.e_entry - seg.p_paddr);
            unsafe {
                let dst = allocated_addr.as_ptr();"""

code = code.replace(alloc_str, new_alloc_str)

code = code.replace(
    'uefi::println!("Handing off to entry {:#x}...", header.e_entry);',
    'uefi::println!("Handing off to entry {:#x} (runtime: {:#x})...", header.e_entry, runtime_entry);'
)

code = code.replace(
    'handoff_to_kernel(header.e_entry, &state);',
    'handoff_to_kernel(runtime_entry, &state);'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
