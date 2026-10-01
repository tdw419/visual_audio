with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

data = data.replace(
    "handover_entry(image_handle, system_table, boot_params as *mut _);",
    "handover_entry(core::ptr::null_mut(), system_table, boot_params as *mut _);"
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
