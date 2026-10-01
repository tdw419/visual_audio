import os
import re

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

old_handler = """    core::arch::naked_asm!(
        "push rax",
        "push rcx",
        "push rdx",
        "push rsi",
        "push rdi",
        "push r8",
        "push r9",
        "push r10",
        "push r11",

        // rdi already contains the char from the payload!
        // We will call a sysv64 rust function
        "call handle_syscall_x86",

        "pop r11",
        "pop r10",
        "pop r9",
        "pop r8",
        "pop rdi",
        "pop rsi",
        "pop rdx",
        "pop rcx",
        "pop rax",
        "iretq"
    );"""

new_handler = """    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov ax, di",
        "out dx, al",
        "iretq"
    );"""

code = code.replace(old_handler, new_handler)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
