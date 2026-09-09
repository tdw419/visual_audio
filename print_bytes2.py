import os
import re

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

# Fix scope issue
code = code.replace(
    'uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);\n    let msg_ptr = (allocated_addr + 0x44) as *const u8;\n    unsafe { uefi::println!("Bytes: {:02x} {:02x} {:02x} {:02x} {:02x}", *msg_ptr, *msg_ptr.add(1), *msg_ptr.add(2), *msg_ptr.add(3), *msg_ptr.add(4)); }',
    'uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);\n    let msg_ptr = (runtime_entry + 0x20) as *const u8;\n    unsafe { uefi::println!("Bytes: {:02x} {:02x} {:02x} {:02x} {:02x}", *msg_ptr, *msg_ptr.add(1), *msg_ptr.add(2), *msg_ptr.add(3), *msg_ptr.add(4)); }'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)

