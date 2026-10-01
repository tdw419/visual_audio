import re

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

data = data.replace(
    'const CMDLINE: &[u8] = b"console=hvc0 earlycon=hvc0 loglevel=7 debug\\0";',
    'const CMDLINE: &[u8] = b"console=ttyS0,115200 earlyprintk=serial,ttyS0,115200 earlycon=uart8250,io,0x3f8 loglevel=7 debug\\0";'
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
