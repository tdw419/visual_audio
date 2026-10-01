import os
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

ring0_handoff = """
#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "efiapi" fn x86_64_handoff(_entry_point: u64, _stack_ptr: u64) -> ! {
    core::arch::naked_asm!(
        "mov rsp, rdx",
        "jmp rcx",
    );
}
"""
import re
code = re.sub(r'#\[cfg\(target_arch = "x86_64"\)\]\n#\[unsafe\(naked\)\].*?\n}', ring0_handoff, code, flags=re.DOTALL)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)
