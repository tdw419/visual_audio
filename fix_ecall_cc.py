import os
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

code = code.replace('extern "C" fn ecall_trap_handler', 'extern "sysv64" fn ecall_trap_handler')
code = code.replace('extern "C" fn ud_trap_handler', 'extern "sysv64" fn ud_trap_handler')

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
