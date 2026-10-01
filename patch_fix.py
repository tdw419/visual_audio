import os

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

# I will just define runtime_entry at the top of the unsafe block
code = code.replace(
    'let mut state = CpuState::default();',
    'let mut runtime_entry = header.e_entry;\n        let mut state = CpuState::default();'
)

# And inside the alloc block:
code = code.replace(
    'uefi::println!("Allocated {} pages at {:#x} (requested {:#x})", num_pages, allocated_addr.as_ptr() as u64, seg.p_paddr);',
    'uefi::println!("Allocated {} pages at {:#x} (requested {:#x})", num_pages, allocated_addr.as_ptr() as u64, seg.p_paddr);\n            runtime_entry = (allocated_addr.as_ptr() as u64) + (header.e_entry - seg.p_paddr);'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
