import os
import re

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

# Change to extern "efiapi" and use rcx/rdx
code = code.replace(
    'pub unsafe extern "sysv64" fn x86_64_handoff(entry: u64, state_ptr: *const CpuState) -> ! {',
    'pub unsafe extern "efiapi" fn x86_64_handoff(entry: u64, state_ptr: *const CpuState) -> ! {'
)

code = code.replace(
    '        "test rsi, rsi",\n        "jz 1f",\n        "mov rsp, rsi",\n        "1:",\n        "jmp rdi",',
    '        "test rdx, rdx",\n        "jz 1f",\n        "mov rsp, rdx",\n        "1:",\n        "jmp rcx",'
)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)

