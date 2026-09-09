import os
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    ecall = f.read()

ecall = ecall.replace('core::arch::asm!("mov {0:x}, cs", out(reg) cs);', 'cs = 0x08; // Use our new GDT Ring 0 Code selector, not UEFI\'s')

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(ecall)
