import os
import re

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

# Replace isr_vector_0x80
old_handler = """#[cfg(target_arch = "x86_64")]
pub extern "sysv64" fn isr_vector_0x80(rdi: u64, _rsi: u64, _rdx: u64, _rcx: u64, _r8: u64, _r9: u64) {
    // Print the character in RDI to COM1
    let b = (rdi & 0xFF) as u8;
    unsafe {
        core::arch::asm!(
            "out dx, al",
            in("dx") 0x3F8_u16, // COM1
            in("al") b,
        );
    }
}"""

new_handler = """#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x80() {
    core::arch::naked_asm!(
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
    );
}

#[cfg(target_arch = "x86_64")]
#[no_mangle]
pub extern "sysv64" fn handle_syscall_x86(rdi: u64) {
    let b = (rdi & 0xFF) as u8;
    unsafe {
        core::arch::asm!(
            "out dx, al",
            in("dx") 0x3F8_u16,
            in("al") b,
        );
    }
}"""

code = code.replace(old_handler, new_handler)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
