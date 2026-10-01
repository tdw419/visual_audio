with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

data = data.replace(
    'type EfiHandoverEntry = unsafe extern "efiapi" fn(',
    'type EfiHandoverEntry = unsafe extern "C" fn('
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
