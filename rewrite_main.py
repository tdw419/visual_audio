import re
with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

# I will just write a whole new main loop!
code = re.sub(r'let mut runtime_entry = header\.e_entry;\n', '', code)

# We want to declare `let mut runtime_entry = header.e_entry;` before the loop.
code = code.replace(
    '        uefi::println!(\n            "Found {} PT_LOAD segment(s), entry = {:#x}",\n            segments.len(),\n            header.e_entry\n        );',
    '        uefi::println!(\n            "Found {} PT_LOAD segment(s), entry = {:#x}",\n            segments.len(),\n            header.e_entry\n        );\n        let mut runtime_entry = header.e_entry;'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
