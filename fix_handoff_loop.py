import os
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

code = code.replace(
    '        "jmp rcx",',
    '        "2:",\n        "jmp 2b",\n        "jmp rcx",'
)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)
