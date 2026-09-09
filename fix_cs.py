import os
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

code = code.replace(
    'let cs = 0x18; // Our new GDT Ring 0 Code selector is 0x08. Wait...',
    'let cs: u16;\n        unsafe { core::arch::asm!("mov {:x}, cs", out(reg) cs) };'
)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
