import os
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

acpi_shutdown = """#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x06() {
    core::arch::naked_asm!(
        "mov ax, 0x2000",
        "mov dx, 0x604",
        "out dx, ax",
        "2: cli; hlt; jmp 2b"
    );
}"""

import re
code = re.sub(r'#\[cfg\(target_arch = "x86_64"\)\]\n#\[unsafe\(naked\)\]\npub unsafe extern "C" fn isr_vector_0x06\(\) \{.*?jmp 1b"\n    \);\n\}', acpi_shutdown, code, flags=re.DOTALL)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)

with open("boot_images/src/x86_hello.S", "w") as f:
    f.write("""
.intel_syntax noprefix
.global _start

.section .text
_start:
    lea rbx, [rip + msg]
.loop:
    movzx rdi, byte ptr [rbx]
    test rdi, rdi
    jz .done
    mov rax, 1
    int 0x80
    inc rbx
    jmp .loop

.done:
    ud2

msg:
    .asciz "\\n\\n*** HELLO FROM THE SPOKEN KERNEL (x86_64) ***\\nBooted via a signed visual-audio boot manifest.\\n\\n"
""")
