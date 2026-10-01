import os
import re
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

# Replace isr_vector_0x80 with one that prints 'A' unconditionally, THEN prints the character
new_0x80 = """#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x80() {
    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov al, 0x41", // 'A'
        "out dx, al",
        "mov ax, di",
        "out dx, al",
        "iretq"
    );
}"""

code = re.sub(r'#\[cfg\(target_arch = "x86_64"\)\]\n#\[unsafe\(naked\)\]\npub unsafe extern "C" fn isr_vector_0x80\(\) \{.*?iretq"\n    \);\n\}', new_0x80, code, flags=re.DOTALL)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)

