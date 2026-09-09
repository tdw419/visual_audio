import os
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

code = code.replace(
    '        "mov rsp, rdx",\n        "jmp rcx",',
    '        "test rdx, rdx",\n        "jz 1f",\n        "mov rsp, rdx",\n        "1:",\n        "jmp rcx",'
)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)
