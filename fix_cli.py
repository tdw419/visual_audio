import os
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

code = code.replace(
    '            core::arch::asm!(\n                "lidt [{}]",\n                in(reg) &IDTR,\n            );',
    '            core::arch::asm!(\n                "cli",\n                "lidt [{}]",\n                in(reg) &IDTR,\n            );'
)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
