import os
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

old_ud2 = """#[cfg(target_arch = "x86_64")]
pub extern "sysv64" fn isr_vector_0x06(_rdi: u64, _rsi: u64, _rdx: u64, _rcx: u64, _r8: u64, _r9: u64) {
    // #UD (Invalid Opcode) handler — used as clean exit
    unsafe {
        // Print 'X' to COM1 to show we caught it
        core::arch::asm!(
            "out dx, al",
            in("dx") 0x3F8_u16,
            in("al") b'X',
        );

        // QEMU ACPI shutdown port
        core::arch::asm!(
            "mov ax, 0x2000",
            "out dx, ax",
            in("dx") 0x604_u16,
        );

        loop {}
    }
}"""

new_ud2 = """#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x06() {
    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov al, 0x58", // 'X'
        "out dx, al",
        "2:",
        "cli",
        "hlt",
        "jmp 2b"
    );
}"""

code = code.replace(old_ud2, new_ud2)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
