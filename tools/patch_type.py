with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

data = data.replace(
    "boot_params.hdr_mut().type_of_loader = 0xFF;",
    "boot_params.hdr_mut().type_of_loader = 0x21;\n        boot_params.hdr_mut().ext_loader_type = 0;"
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
