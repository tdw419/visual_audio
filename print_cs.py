import os
import re

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

# Replace hardcoded 0x38 with reading CS and printing it!
# But ecall.rs doesn't have uefi::println. We can print it by writing to COM1 manually, or return it!
# Let's just restore the mov cs reading.
code = code.replace(
    'let cs = 0x38;',
    'let cs: u16;\n        unsafe { core::arch::asm!("mov {:x}, cs", out(reg) cs) };'
)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    uefi_code = f.read()

uefi_code = uefi_code.replace(
    '    virtio_pixel_rs_v3_shared::ecall::setup_trap_table();',
    '    virtio_pixel_rs_v3_shared::ecall::setup_trap_table();\n    let cs: u16;\n    unsafe { core::arch::asm!("mov {:x}, cs", out(reg) cs) };\n    uefi::println!("CS is {:#x}", cs);'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(uefi_code)
