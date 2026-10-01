import os
import re

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

# Add a print to see the first 5 bytes of msg
# runtime_entry is allocated_addr + 0x24. msg is at allocated_addr + 0x44.
code = code.replace(
    'uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);',
    'uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);\n    let msg_ptr = (allocated_addr + 0x44) as *const u8;\n    unsafe { uefi::println!("Bytes: {:02x} {:02x} {:02x} {:02x} {:02x}", *msg_ptr, *msg_ptr.add(1), *msg_ptr.add(2), *msg_ptr.add(3), *msg_ptr.add(4)); }'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)

