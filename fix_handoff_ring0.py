import os
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

# Restore the Ring 0 handoff
ring0_handoff = """
#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "sysv64" fn x86_64_handoff(_entry_point: u64, _stack_ptr: u64) -> ! {
    core::arch::naked_asm!(
        "mov rsp, rsi",
        "jmp rdi",
    );
}
"""
import re
code = re.sub(r'#\[cfg\(target_arch = "x86_64"\)\]\n#\[repr\(C, packed\)\].*?options\(noreturn\)\n    \);\n}', ring0_handoff, code, flags=re.DOTALL)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    ecall = f.read()
ecall = ecall.replace('cs = 0x08; // Use our new GDT Ring 0 Code selector', 'core::arch::asm!("mov {0:x}, cs", out(reg) cs);')
with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(ecall)
