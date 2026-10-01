import os
import re

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

code = code.replace(
    '        uefi::println!("ELF64 entry: {:#x}, e_machine: {:#x}", header.e_entry, header.e_machine);',
    '        uefi::println!("ELF64 entry: {:#x}, e_machine: {:#x}", header.e_entry, header.e_machine);\n        let mut runtime_entry = header.e_entry;'
)

# Note: The code currently in the file MIGHT have my previous patch, or it might not. Let's just blindly replace it if it exists.
code = re.sub(r'let num_pages = \(\(seg\.p_memsz \+ 4095\) / 4096\) as usize;.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?let dst = allocated_addr as \*mut u8;',
              r'let dst = seg.p_paddr as *mut u8;', code, flags=re.DOTALL)
              
# And remove previous let mut runtime_entry
code = re.sub(r'let mut runtime_entry.*?\n', '', code)
code = re.sub(r'runtime_entry = allocated_addr \+ \(header\.e_entry - seg\.p_paddr\);\n', '', code)

# Let's just download the raw commit's file if needed!
