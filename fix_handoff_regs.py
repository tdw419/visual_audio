import os
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

# Replace rcx/rdx with rdi/rsi
code = code.replace(
    '        "test rdx, rdx",\n        "jz 1f",\n        "mov rsp, rdx",\n        "1:",\n        "jmp rcx",',
    '        "test rsi, rsi",\n        "jz 1f",\n        "mov rsp, rsi",\n        "1:",\n        "jmp rdi",'
)

# Wait, if there's a loop I added earlier
code = code.replace(
    '        "test rdx, rdx",\n        "jz 1f",\n        "mov rsp, rdx",\n        "1:",\n        "2:",\n        "jmp 2b",\n        "jmp rcx",',
    '        "test rsi, rsi",\n        "jz 1f",\n        "mov rsp, rsi",\n        "1:",\n        "jmp rdi",'
)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)

