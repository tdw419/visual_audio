with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

data = data.replace(
    "let handover_offset = { header.handover_offset } as u64;",
    "let handover_offset = { header.handover_offset } as u64 + 0x200;"
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
