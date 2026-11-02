import re

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

# Replace CMDLINE string
data = re.sub(
    r'const CMDLINE: &\[u8\] = b"[^"]*";',
    r'const CMDLINE: &[u8] = b"console=hvc0 earlycon=hvc0 loglevel=7 debug\\0";',
    data
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
