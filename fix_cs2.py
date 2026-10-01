import os
import re

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "r") as f:
    code = f.read()

code = re.sub(r'let cs: u16;\s*unsafe \{ core::arch::asm!\("mov \{:x\}, cs", out\(reg\) cs\) \};', 'let cs = 0x38;', code)

with open("systems/virtio_pixel_rs_v3_shared/src/ecall.rs", "w") as f:
    f.write(code)
